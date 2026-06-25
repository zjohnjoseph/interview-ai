"""
Resumable synthetic interview-question generator (OpenRouter-backed).

Generates questions across a domain x difficulty x role-level grid, with exact-text
deduplication, quality filtering, and progress tracking. Calls OpenRouter directly
(provider="openrouter") so live-interview provider quotas stay untouched.

Usage:
    docker compose run --rm api python -m scripts.generate_questions

Resumable: re-running skips batches already recorded in scripts/generation_progress.json.
Ctrl+C saves progress before exiting so the next run continues where it stopped.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict

from sqlalchemy import select

from app.database import async_session
from app.models.database_models import Question
from app.services.llm_prompts import SYNTHETIC_QUESTION_GENERATION_PROMPT
from app.services.llm_service import llm_service

# ── Generation grid ──────────────────────────────────────────────────────────
DOMAINS = ["python", "data_structures", "sql", "system_design", "ml", "apis"]
DIFFICULTIES = ["easy", "medium", "hard"]
ROLE_LEVELS = ["junior", "mid", "senior"]

# ── Sources ──────────────────────────────────────────────────────────────────
# Three generators, tried in order. When one hits its daily limit the run rotates
# to the next, so a single run drains all three free budgets. `model=None` uses the
# provider's default (Groq → settings.groq_model = llama-3.3-70b-versatile).
class Source(TypedDict):
    name: str
    provider: Literal["groq", "openrouter"]
    model: str | None


SOURCES: list[Source] = [
    {"name": "gpt-oss", "provider": "openrouter", "model": "openai/gpt-oss-120b:free"},
    {"name": "groq", "provider": "groq", "model": None},
    {
        "name": "nemotron",
        "provider": "openrouter",
        "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    },
]

# 15 Q&A pairs ≈ ~3,000 tokens/batch.
BATCHES_PER_COMBO = 3
QUESTIONS_PER_BATCH = 15
SLEEP_SECONDS = 20          # between successful batches
MAX_OUTPUT_TOKENS = 8000    # also keeps Groq requests under its 12K tokens/min cap
# Backoff when a batch fails (usually a transient per-minute rate/token limit).
FAILURE_BACKOFF_SECONDS = 30
MAX_BATCH_RETRIES = 2       # retries per batch before counting it a failure
# After this many failed batches in a row on one source, rotate to the next source.
# When the last source is exhausted too, stop.
SOURCE_SWITCH_AFTER = 3

# ── Quality filtering ────────────────────────────────────────────────────────
_MIN_TEXT_CHARS = 20
_MIN_ANSWER_CHARS = 50
_VALID_DOMAINS = set(DOMAINS)
_VALID_DIFFICULTIES = set(DIFFICULTIES)
_INTERROGATIVES = ("how", "what", "why", "when", "which", "explain", "describe", "design")

_PROGRESS_PATH = Path(__file__).resolve().parent / "generation_progress.json"
_SYSTEM_PROMPT = (
    "You are a senior technical interviewer building a question bank. "
    "Return structured JSON only."
)


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace, for exact-text dedup."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _load_progress() -> dict[str, Any]:
    if _PROGRESS_PATH.exists():
        with _PROGRESS_PATH.open(encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data
    return {
        "total_generated": 0,
        "total_inserted": 0,
        "total_duplicates": 0,
        "batches_completed": [],
        "last_run": None,
    }


def _save_progress(progress: dict[str, Any]) -> None:
    progress["last_run"] = datetime.now(timezone.utc).isoformat()
    with _PROGRESS_PATH.open("w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def _completed_keys(progress: dict[str, Any]) -> set[tuple[str, str, str, int]]:
    return {
        (b["domain"], b["difficulty"], b["role_level"], b["batch"])
        for b in progress["batches_completed"]
    }


def _is_valid(q: dict[str, Any]) -> tuple[bool, str]:
    text = str(q.get("text", "")).strip()
    answer = str(q.get("reference_answer", "")).strip()
    domain = str(q.get("domain", "")).strip()
    difficulty = str(q.get("difficulty", "")).strip()

    if len(text) < _MIN_TEXT_CHARS:
        return False, f"text too short ({len(text)} chars)"
    if len(answer) < _MIN_ANSWER_CHARS:
        return False, f"reference_answer too short ({len(answer)} chars)"
    if domain not in _VALID_DOMAINS:
        return False, f"invalid domain '{domain}'"
    if difficulty not in _VALID_DIFFICULTIES:
        return False, f"invalid difficulty '{difficulty}'"
    lowered = text.lower()
    if "?" not in text and not lowered.startswith(_INTERROGATIVES):
        return False, "not phrased as a question"
    return True, ""


async def _load_corpus_texts() -> set[str]:
    """Normalized text of every existing question, for cross-corpus dedup."""
    async with async_session() as session:
        result = await session.execute(select(Question.text))
        return {_normalize(t) for t in result.scalars().all()}


async def _load_existing_topics(domain: str) -> str:
    """Short topic summaries (truncated question text) for the prompt, per domain."""
    async with async_session() as session:
        result = await session.execute(
            select(Question.text).where(Question.domain == domain)
        )
        texts = list(result.scalars().all())
    if not texts:
        return "(none yet)"
    return "\n".join(f"- {t[:80]}" for t in texts[:40])


async def main() -> None:
    progress = _load_progress()
    done = _completed_keys(progress)
    corpus_texts = await _load_corpus_texts()
    seen_this_run: set[str] = set()

    # Domain innermost so each step cycles all 6 domains — a partial run stays balanced.
    combos = [(d, diff, role) for diff in DIFFICULTIES for role in ROLE_LEVELS for d in DOMAINS]
    total_batches = len(combos) * BATCHES_PER_COMBO

    print(f"Loading progress... {progress['total_generated']} questions generated so far.")
    print(
        f"Starting generation: {len(combos)} combinations x {BATCHES_PER_COMBO} batches "
        f"= {total_batches} batches.\n"
    )

    session_generated = session_inserted = session_duplicates = 0
    start_time = time.monotonic()
    idx = 0
    source_idx = 0
    consecutive_failed_batches = 0
    aborted = False
    print(f"Sources (in order): {', '.join(s['name'] for s in SOURCES)}")
    print(f"Active source: {SOURCES[0]['name']}\n")

    # Round-robin by batch so every domain fills evenly even if the run is interrupted.
    topics_cache: dict[str, str] = {}
    try:
        for batch in range(1, BATCHES_PER_COMBO + 1):
            if aborted:
                break
            for domain, difficulty, role_level in combos:
                if aborted:
                    break
                idx += 1
                key = (domain, difficulty, role_level, batch)
                if key in done:
                    continue

                if domain not in topics_cache:
                    topics_cache[domain] = await _load_existing_topics(domain)
                existing_topics = topics_cache[domain]

                prompt = SYNTHETIC_QUESTION_GENERATION_PROMPT.format(
                    domain=domain,
                    difficulty=difficulty,
                    role_level=role_level,
                    num_questions=QUESTIONS_PER_BATCH,
                    existing_topics=existing_topics,
                )

                # Try the active source, retrying with backoff for transient limits.
                source = SOURCES[source_idx]
                questions: list[dict[str, Any]] | None = None
                for attempt in range(1, MAX_BATCH_RETRIES + 1):
                    try:
                        result = llm_service.call_llm(
                            prompt,
                            _SYSTEM_PROMPT,
                            provider=source["provider"],
                            model=source["model"],
                            max_tokens=MAX_OUTPUT_TOKENS,
                        )
                        questions = result.get("questions", [])
                        break
                    except Exception as exc:  # noqa: BLE001 — back off and retry/skip
                        print(
                            f"[{idx}/{total_batches}] {domain}/{difficulty}/{role_level} "
                            f"(batch {batch}) [{source['name']}] ... FAILED "
                            f"(attempt {attempt}): {exc}"
                        )
                        if attempt < MAX_BATCH_RETRIES:
                            time.sleep(FAILURE_BACKOFF_SECONDS)

                if questions is None:
                    # Batch failed all retries. Count it; rotate sources after a streak.
                    consecutive_failed_batches += 1
                    if consecutive_failed_batches >= SOURCE_SWITCH_AFTER:
                        if source_idx + 1 < len(SOURCES):
                            source_idx += 1
                            consecutive_failed_batches = 0
                            print(
                                f"\n>>> '{source['name']}' looks exhausted — switching to "
                                f"'{SOURCES[source_idx]['name']}'.\n"
                            )
                        else:
                            print(
                                "\nAll sources exhausted. Stopping; re-run later to resume."
                            )
                            aborted = True
                            break
                    continue

                consecutive_failed_batches = 0

                generated = inserted = duplicates = 0
                to_insert: list[dict[str, str]] = []
                for q in questions:
                    generated += 1
                    ok, reason = _is_valid(q)
                    if not ok:
                        print(f"    rejected: {reason} — {str(q.get('text', ''))[:60]!r}")
                        continue
                    norm = _normalize(str(q["text"]))
                    if norm in corpus_texts or norm in seen_this_run:
                        duplicates += 1
                        continue
                    seen_this_run.add(norm)
                    to_insert.append({
                        "text": str(q["text"]).strip(),
                        "domain": domain,
                        "difficulty": difficulty,
                        "reference_answer": str(q["reference_answer"]).strip(),
                    })

                if to_insert:
                    async with async_session() as session:
                        for fields in to_insert:
                            session.add(Question(**fields))
                        await session.commit()
                    inserted = len(to_insert)
                    for fields in to_insert:
                        corpus_texts.add(_normalize(fields["text"]))

                progress["total_generated"] += generated
                progress["total_inserted"] += inserted
                progress["total_duplicates"] += duplicates
                progress["batches_completed"].append({
                    "domain": domain,
                    "difficulty": difficulty,
                    "role_level": role_level,
                    "batch": batch,
                    "count": inserted,
                })
                _save_progress(progress)

                session_generated += generated
                session_inserted += inserted
                session_duplicates += duplicates

                print(
                    f"[{idx}/{total_batches}] {domain}/{difficulty}/{role_level} "
                    f"(batch {batch}) [{source['name']}] ... {generated} generated, "
                    f"{inserted} inserted, {duplicates} duplicates"
                )
                time.sleep(SLEEP_SECONDS)
    except KeyboardInterrupt:
        print("\nInterrupted — saving progress before exit.")
        _save_progress(progress)

    elapsed = time.monotonic() - start_time
    print("\n--- Session summary ---")
    print(f"Questions generated: {session_generated}")
    print(f"Questions inserted:  {session_inserted}")
    print(f"Duplicates skipped:  {session_duplicates}")
    print(f"Time elapsed:        {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m")
    print(f"Corpus total inserted (all runs): {progress['total_inserted']}")
    print("Progress saved. Run again to continue.")


if __name__ == "__main__":
    asyncio.run(main())
