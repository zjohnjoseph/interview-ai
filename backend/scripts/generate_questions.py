"""
Resumable synthetic interview-question generator (Gemini-backed).

Generates questions across a domain x difficulty x role-level grid, with exact-text
deduplication, quality filtering, and progress tracking. Reserves the Groq quota for
live interviews by calling Gemini directly (provider="gemini").

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
from typing import Any, Literal

from sqlalchemy import select

from app.database import async_session
from app.models.database_models import Question
from app.services.llm_prompts import SYNTHETIC_QUESTION_GENERATION_PROMPT
from app.services.llm_service import llm_service

# ── Generation grid ──────────────────────────────────────────────────────────
DOMAINS = ["python", "data_structures", "sql", "system_design", "ml", "apis"]
DIFFICULTIES = ["easy", "medium", "hard"]
ROLE_LEVELS = ["junior", "mid", "senior"]

# Groq-first: its limit is tokens/day (~100K), not requests, so it sustains bulk
# generation far better than Gemini's ~20 requests/day. "auto" falls back to Gemini
# when Groq is exhausted, combining both daily budgets.
PROVIDER: Literal["auto", "groq", "gemini"] = "auto"
# 15 Q&A pairs ≈ 3,150 tokens/batch → ~100K TPD / 3,150 ≈ ~30 batches ≈ ~450/day.
BATCHES_PER_COMBO = 3
QUESTIONS_PER_BATCH = 15
SLEEP_SECONDS = 25          # ~3,150 tokens/batch; ~2.4/min stays under Groq's 12K TPM
# Keep max_tokens + input under Groq's 12K TPM (16K triggers a 413 "request too large").
MAX_OUTPUT_TOKENS = 8000
# Backoff when a batch fails (usually a per-minute rate/token limit that resets shortly).
FAILURE_BACKOFF_SECONDS = 60
MAX_BATCH_RETRIES = 3       # retry the same batch this many times before skipping it
# Stop only after a long failure streak — rides out transient per-minute Groq limits
# instead of aborting the whole run when Gemini (fallback) is also exhausted.
MAX_CONSECUTIVE_FAILURES = 24

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
    consecutive_failures = 0
    aborted = False

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

                # Retry the same batch with backoff — failures are usually a
                # per-minute rate/token limit that resets within a minute.
                questions: list[dict[str, Any]] | None = None
                for attempt in range(1, MAX_BATCH_RETRIES + 1):
                    try:
                        result = llm_service.call_llm(
                            prompt,
                            _SYSTEM_PROMPT,
                            provider=PROVIDER,
                            max_tokens=MAX_OUTPUT_TOKENS,
                        )
                        questions = result.get("questions", [])
                        consecutive_failures = 0
                        break
                    except Exception as exc:  # noqa: BLE001 — back off and retry/skip
                        consecutive_failures += 1
                        print(
                            f"[{idx}/{total_batches}] {domain}/{difficulty}/{role_level} "
                            f"(batch {batch}) ... FAILED "
                            f"(attempt {attempt}, {consecutive_failures} in a row): {exc}"
                        )
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            print(
                                f"\n{MAX_CONSECUTIVE_FAILURES} consecutive failures — "
                                "quota likely exhausted. Stopping; re-run later to resume."
                            )
                            aborted = True
                            break
                        if attempt < MAX_BATCH_RETRIES:
                            time.sleep(FAILURE_BACKOFF_SECONDS)

                if aborted:
                    break
                if questions is None:    # batch exhausted retries — leave it for next run
                    time.sleep(FAILURE_BACKOFF_SECONDS)
                    continue

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
                    f"(batch {batch}) ... {generated} generated, {inserted} inserted, "
                    f"{duplicates} duplicates"
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
