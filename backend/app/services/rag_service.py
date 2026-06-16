from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database_models import Question
from app.services.bm25_service import bm25_service
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

    async def hybrid_search(
        self,
        query: str,
        db: AsyncSession,
        domain: str | None = None,
        difficulty: str | None = None,
        limit: int = 5,
        exclude_ids: list[uuid.UUID] | None = None,
    ) -> list[dict[str, Any]]:
        # Step 1 — parallel retrieval from vector and BM25
        vector_results, bm25_results = await asyncio.gather(
            self.search_similar_questions(query, db, domain, difficulty, limit * 2, exclude_ids),
            bm25_service.keyword_search(query, db, domain, difficulty, limit * 2, exclude_ids),
        )

        # Step 2 — merge and deduplicate by question_id
        merged: dict[str, dict[str, Any]] = {}
        for r in vector_results:
            merged[r["question_id"]] = {
                **r,
                "source": "vector",
                "relevance_score": r["similarity_score"],
            }
        for r in bm25_results:
            qid = r["question_id"]
            if qid in merged:
                merged[qid]["source"] = "both"
                merged[qid]["bm25_score"] = r["bm25_score"]
            else:
                merged[qid] = {
                    **r,
                    "source": "bm25",
                    "relevance_score": r["bm25_score"],
                }

        candidates = list(merged.values())
        if not candidates:
            return []

        # Step 3 — rerank with Jina cross-encoder (fallback to score merge on error)
        texts = [c["text"] for c in candidates]
        try:
            rerank_results = await embedding_service.rerank(query, texts, top_n=limit)
            for item in rerank_results:
                candidates[item["index"]]["relevance_score"] = round(
                    item["relevance_score"], 4
                )
            candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
        except Exception:
            logger.warning("Reranker unavailable, falling back to score merge")
            max_vec = max(
                (c.get("similarity_score", 0.0) for c in candidates), default=1.0
            ) or 1.0
            for c in candidates:
                vec_s = c.get("similarity_score", 0.0) / max_vec
                bm25_s = c.get("bm25_score", 0.0)
                if c["source"] == "both":
                    c["relevance_score"] = round((vec_s + bm25_s) / 2, 4)
                elif c["source"] == "vector":
                    c["relevance_score"] = round(vec_s, 4)
                else:
                    c["relevance_score"] = round(bm25_s, 4)
            candidates.sort(key=lambda c: c["relevance_score"], reverse=True)

        # Step 4 — return only the public fields
        keep = {
            "question_id",
            "text",
            "domain",
            "difficulty",
            "reference_answer",
            "relevance_score",
            "source",
        }
        return [
            {k: v for k, v in c.items() if k in keep}
            for c in candidates[:limit]
        ]


rag_service = RAGService()
