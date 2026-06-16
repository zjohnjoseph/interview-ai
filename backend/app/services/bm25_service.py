from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import Question


class BM25Service:
    async def keyword_search(
        self,
        query: str,
        db: AsyncSession,
        domain: str | None = None,
        difficulty: str | None = None,
        limit: int = 10,
        exclude_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        tsquery = func.plainto_tsquery("english", query)
        stmt = (
            select(
                Question.id,
                Question.text,
                Question.domain,
                Question.difficulty,
                Question.reference_answer,
                func.ts_rank(Question.search_vector, tsquery).label("rank"),
            )
            .where(Question.search_vector.op("@@")(tsquery))
            .order_by(func.ts_rank(Question.search_vector, tsquery).desc())
            .limit(limit)
        )
        if domain is not None:
            stmt = stmt.where(Question.domain == domain)
        if difficulty is not None:
            stmt = stmt.where(Question.difficulty == difficulty)
        if exclude_ids:
            stmt = stmt.where(Question.id.not_in(exclude_ids))

        rows = (await db.execute(stmt)).all()
        if not rows:
            return []

        max_rank = max(float(r.rank) for r in rows) or 1.0
        return [
            {
                "question_id": str(r.id),
                "text": r.text,
                "domain": r.domain,
                "difficulty": r.difficulty,
                "reference_answer": r.reference_answer,
                "bm25_score": round(float(r.rank) / max_rank, 4),
            }
            for r in rows
        ]


bm25_service = BM25Service()
