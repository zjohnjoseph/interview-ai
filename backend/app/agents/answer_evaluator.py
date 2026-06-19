from __future__ import annotations

import logging
from typing import Any

from app.agents.state import InterviewState
from app.agents.utils import call_llm_async
from app.models.schemas import EvaluationResponse
from app.services.llm_prompts import ANSWER_EVALUATION_PROMPT
from app.services.llm_service import LLMResponseParseError, LLMValidationError

logger = logging.getLogger(__name__)

_FALLBACK_EVALUATION: dict[str, Any] = {
    "score": 5.0,
    "accuracy": 5.0,
    "completeness": 5.0,
    "clarity": 5.0,
    "feedback": "Evaluation could not be completed reliably. Please review manually.",
}


async def evaluate_answer(state: InterviewState) -> dict[str, Any]:
    question = state.get("current_question") or {}
    prompt = ANSWER_EVALUATION_PROMPT.format(
        job_description=state.get("job_description", ""),
        role_level=state.get("role_level", "mid"),
        question_text=question.get("question_text", ""),
        reference_answer=question.get("reference_answer", ""),
        candidate_answer=state.get("current_answer", "") or "",
    )

    # First attempt + one retry on guardrail failure (a new sampling may parse cleanly).
    for attempt in (1, 2):
        try:
            result = await call_llm_async(prompt, response_model=EvaluationResponse)
            return {
                "current_evaluation": {
                    "score": result["score"],
                    "accuracy": result["accuracy"],
                    "completeness": result["completeness"],
                    "clarity": result["clarity"],
                    "feedback": result["feedback"],
                }
            }
        except (LLMValidationError, LLMResponseParseError) as exc:
            logger.warning("Answer evaluation guardrail failed (attempt %d): %s", attempt, exc)
        except Exception as exc:
            logger.error("Answer evaluation failed: %s", exc)
            break

    logger.error("Answer evaluation falling back to neutral scores")
    return {"current_evaluation": dict(_FALLBACK_EVALUATION)}
