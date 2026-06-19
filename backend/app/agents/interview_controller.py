from __future__ import annotations

from typing import Any

from app.agents.state import InterviewState


async def control_interview(state: InterviewState) -> dict[str, Any]:
    questions_asked = state.get("questions_asked", 0)
    max_questions = state.get("max_questions", 10)

    if questions_asked >= max_questions:
        return {"is_complete": True}

    return {"is_complete": False}
