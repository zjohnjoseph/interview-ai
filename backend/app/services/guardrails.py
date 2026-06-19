from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from app.agents.answer_evaluator import evaluate_answer
from app.agents.state import InterviewState
from app.config import settings
from app.services.redis_service import redis_service

logger = logging.getLogger(__name__)

_AMBIGUOUS_LOW = 4.0
_AMBIGUOUS_HIGH = 7.0
_INCONSISTENT_DELTA = 1.5
_VARIANCE_NOTE = (
    " [Note: This evaluation showed some scoring variance. Consider manual review.]"
)
_SCORE_FIELDS = ("score", "accuracy", "completeness", "clarity")

_TOKENS_TTL = 48 * 60 * 60  # daily/session counters expire after 48h

_INJECTION_MARKERS = (
    "ignore previous instructions",
    "you are now",
    "system prompt:",
)
_MAX_ANSWER_CHARS = 5000

BudgetMode = Literal["normal", "conserve", "exceeded"]


class TokenBudgetExceededError(Exception):
    """Daily token budget exceeded beyond the hard cap — refuse further LLM work."""


async def consistency_checked_evaluation(
    state: InterviewState, *, conserve: bool
) -> dict[str, Any]:
    """Evaluate the current answer, double-checking ambiguous main-question scores.

    Returns the ``current_evaluation`` dict (not the full graph result). Routing
    (follow-up/completion) is handled separately by ``build_routing_graph``.
    """
    first = (await evaluate_answer(state)).get("current_evaluation") or {}

    question = state.get("current_question") or {}
    is_follow_up = bool(question.get("is_follow_up", False))
    score1 = float(first.get("score", 0.0))

    if conserve or is_follow_up or not (_AMBIGUOUS_LOW <= score1 <= _AMBIGUOUS_HIGH):
        return first

    second = (await evaluate_answer(state)).get("current_evaluation") or {}
    score2 = float(second.get("score", score1))
    delta = abs(score1 - score2)

    averaged: dict[str, Any] = dict(first)
    for field in _SCORE_FIELDS:
        s_a = float(first.get(field, 0.0))
        s_b = float(second.get(field, 0.0))
        averaged[field] = round((s_a + s_b) / 2, 2)

    if delta > _INCONSISTENT_DELTA:
        averaged["feedback"] = str(first.get("feedback", "")) + _VARIANCE_NOTE
        logger.warning(
            "Self-consistency: scores diverged (%.1f vs %.1f, delta=%.1f) — flagged",
            score1, score2, delta,
        )
    else:
        logger.info(
            "Self-consistency: scores agreed (%.1f vs %.1f, delta=%.1f) — averaged",
            score1, score2, delta,
        )
    return averaged


async def record_tokens(session_id: str, tokens: int) -> None:
    """Add `tokens` to today's global counter and this session's counter."""
    if tokens <= 0:
        return
    await redis_service.incr_by(
        redis_service.daily_tokens_key(date.today().isoformat()), tokens, _TOKENS_TTL
    )
    await redis_service.incr_by(
        redis_service.session_tokens_key(session_id), tokens, _TOKENS_TTL
    )


async def check_token_budget(session_id: str) -> BudgetMode:
    """Classify current usage as normal / conserve / exceeded."""
    daily = await redis_service.get_int(
        redis_service.daily_tokens_key(date.today().isoformat())
    )
    session = await redis_service.get_int(redis_service.session_tokens_key(session_id))

    daily_budget = settings.daily_token_budget
    mode: BudgetMode
    if daily > daily_budget * 1.2:
        mode = "exceeded"
    elif daily >= daily_budget or session >= settings.session_token_budget:
        mode = "conserve"
    else:
        mode = "normal"

    logger.info(
        "Token budget check: daily=%d/%d session=%d/%d mode=%s",
        daily, daily_budget, session, settings.session_token_budget, mode,
    )
    return mode


def sanitize_answer(
    answer_text: str, session_id: str = ""
) -> tuple[str, list[str]]:
    """Strip/truncate the answer and flag (but never reject) injection attempts."""
    warnings: list[str] = []
    cleaned = answer_text.strip()

    if len(cleaned) > _MAX_ANSWER_CHARS:
        cleaned = cleaned[:_MAX_ANSWER_CHARS]
        warnings.append("Answer truncated to 5000 characters.")

    lowered = cleaned.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            warnings.append(f"Possible prompt injection detected: {marker!r}")
            logger.warning(
                "Possible prompt injection in answer (session=%s): %r", session_id, marker
            )

    return cleaned, warnings
