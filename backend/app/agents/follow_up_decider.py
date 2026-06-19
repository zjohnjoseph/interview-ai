from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.state import InterviewState
from app.agents.utils import call_llm_async
from app.services.llm_prompts import FOLLOW_UP_DECISION_PROMPT

logger = logging.getLogger(__name__)

_MAX_FOLLOW_UPS = 2


async def decide_follow_up(state: InterviewState) -> dict[str, Any]:
    follow_up_count = state.get("follow_up_count", 0)

    # Hard depth cap — never probe more than _MAX_FOLLOW_UPS times on one main question.
    if follow_up_count >= _MAX_FOLLOW_UPS:
        return {"needs_follow_up": False, "follow_up_count": 0}

    question = state.get("current_question") or {}
    evaluation = state.get("current_evaluation") or {}

    prompt = FOLLOW_UP_DECISION_PROMPT.format(
        role_level=state.get("role_level", "mid"),
        question_text=question.get("question_text", ""),
        candidate_answer=state.get("current_answer", "") or "",
        evaluation=json.dumps(evaluation, indent=2),
    )

    try:
        result = await call_llm_async(prompt)
    except Exception as exc:
        # On any failure, keep the interview moving rather than blocking on a probe.
        logger.error("Follow-up decision failed, moving on: %s", exc)
        return {"needs_follow_up": False, "follow_up_count": 0}

    follow_up_question = result.get("follow_up_question")
    if result.get("needs_follow_up") and follow_up_question:
        return {
            "current_question": {
                "question_text": follow_up_question,
                "reference_answer": "",
                "corpus_question_id": None,
                "domain": question.get("domain", ""),
                "difficulty": question.get("difficulty", "medium"),
                "is_follow_up": True,
            },
            "needs_follow_up": True,
            "follow_up_count": follow_up_count + 1,
        }

    return {"needs_follow_up": False, "follow_up_count": 0}
