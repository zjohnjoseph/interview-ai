from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import Question
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class RAGService:
    SIMILARITY_THRESHOLD: float = 0.5

    async def search_similar_questions(
        self,
        query: str,
        db: AsyncSession,
        domain: str | None = None,
        difficulty: str | None = None,
        limit: int = 5,
        exclude_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        query_vec = await embedding_service.embed_text(query, task="retrieval.query")

        stmt = (
            select(
                Question.id,
                Question.text,
                Question.domain,
                Question.difficulty,
                Question.reference_answer,
                Question.embedding.cosine_distance(query_vec).label("distance"),
            )
            .where(Question.embedding.is_not(None))
            .order_by("distance")
            .limit(limit)
        )

        if domain is not None:
            stmt = stmt.where(Question.domain == domain)
        if difficulty is not None:
            stmt = stmt.where(Question.difficulty == difficulty)
        if exclude_ids:
            stmt = stmt.where(Question.id.not_in(exclude_ids))

        rows = (await db.execute(stmt)).all()

        results: list[dict[str, Any]] = []
        for row in rows:
            score = round(1.0 - float(row.distance), 4)
            if score >= self.SIMILARITY_THRESHOLD:
                results.append(
                    {
                        "question_id": str(row.id),
                        "text": row.text,
                        "domain": row.domain,
                        "difficulty": row.difficulty,
                        "reference_answer": row.reference_answer,
                        "similarity_score": score,
                    }
                )

        logger.info(
            "Semantic search completed",
            extra={
                "query_len": len(query),
                "results": len(results),
                "domain": domain,
                "difficulty": difficulty,
            },
        )
        return results


rag_service = RAGService()
