from __future__ import annotations

import logging
from typing import Any

from app.agents.state import InterviewState
from app.agents.utils import call_llm_async
from app.services.llm_prompts import RESUME_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)

_FALLBACK_PROFILE: dict[str, Any] = {
    "technical_skills": [],
    "experience_years": 0,
    "seniority_assessment": "unknown",
    "primary_languages": [],
    "strengths": [],
    "potential_gaps": [],
    "experience_summary": "Resume analysis unavailable",
}


async def analyze_resume(state: InterviewState) -> dict[str, Any]:
    resume_text = state.get("resume_text", "")
    prompt = RESUME_ANALYSIS_PROMPT.format(resume_text=resume_text)
    try:
        result = await call_llm_async(prompt)
        logger.info(
            "Resume analysis complete",
            extra={"skills_found": len(result.get("technical_skills", []))},
        )
        return {"candidate_profile": result}
    except Exception as exc:
        logger.error("Resume analysis failed: %s", exc)
        return {"candidate_profile": _FALLBACK_PROFILE, "error": str(exc)}
