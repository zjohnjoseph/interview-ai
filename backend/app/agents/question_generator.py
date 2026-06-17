from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import InterviewState
from app.agents.utils import call_llm_async
from app.services.llm_prompts import QUESTION_GENERATION_PROMPT
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)


def make_question_generator(
    db: AsyncSession,
) -> Any:
    async def generate_question(state: InterviewState) -> dict[str, Any]:
        required = state.get("required_skills", "")
        covered = set(state.get("topics_covered", []))
        history = state.get("interview_history", [])

        uncovered = [t.strip() for t in required.split(",") if t.strip().lower() not in covered]
        rag_query = " ".join(uncovered) if uncovered else required

        exclude_ids: list[uuid.UUID] = []
        for h in history:
            cid = h.get("corpus_question_id")
            if cid:
                try:
                    exclude_ids.append(uuid.UUID(cid))
                except ValueError:
                    pass

        corpus_results = await rag_service.hybrid_search(
            query=rag_query,
            db=db,
            limit=5,
            exclude_ids=exclude_ids or None,
        )

        similar_questions = (
            "\n".join(
                f"{i + 1}. [ID: {r['question_id']}] {r['text']}"
                for i, r in enumerate(corpus_results)
            )
            if corpus_results
            else "No similar questions found in the corpus."
        )

        history_summary = (
            json.dumps(
                [{"question": h.get("question", ""), "score": h.get("score")} for h in history],
                indent=2,
            )
            if history
            else "[]"
        )

        prompt = QUESTION_GENERATION_PROMPT.format(
            job_description=state.get("job_description", ""),
            required_skills=required,
            role_level=state.get("role_level", "mid"),
            candidate_profile=json.dumps(state.get("candidate_profile", {}), indent=2),
            interview_history=history_summary,
            similar_questions=similar_questions,
        )

        result = await call_llm_async(prompt)

        corpus_id: str | None = result.get("corpus_question_id")
        valid_ids = {r["question_id"] for r in corpus_results}
        if corpus_id and corpus_id not in valid_ids:
            logger.warning("LLM returned unknown corpus_question_id %s — clearing", corpus_id)
            corpus_id = None

        domain: str = result.get("domain", "")
        question: dict[str, Any] = {
            "question_text": result.get("question_text", ""),
            "reference_answer": result.get("reference_answer", ""),
            "corpus_question_id": corpus_id,
            "domain": domain,
            "difficulty": result.get("difficulty", "medium"),
            "is_follow_up": False,
        }
        return {
            "current_question": question,
            "topics_covered": [domain] if domain else [],
        }

    return generate_question
