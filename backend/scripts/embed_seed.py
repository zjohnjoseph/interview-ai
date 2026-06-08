"""
Embed all seed questions that lack embeddings using Jina and store in pgvector.

Usage:
    docker compose run --rm api python -m scripts.embed_seed

Idempotent: skips questions that already have an embedding.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models.database_models import Question
from app.services.embedding_service import EmbeddingError, embedding_service


async def main() -> None:
    # Read session — closed before the Jina API call to avoid holding a transaction open
    async with async_session() as session:
        result = await session.execute(
            select(Question).where(Question.embedding.is_(None))
        )
        questions = list(result.scalars().all())

    if not questions:
        print("All questions already have embeddings. Nothing to do.")
        return

    print(f"Embedding {len(questions)} questions via Jina...")
    texts = [q.text for q in questions]

    try:
        vectors, tokens = await embedding_service.embed_batch(texts, task="retrieval.passage")
    except EmbeddingError as exc:
        print(f"Embedding failed: {exc}")
        raise SystemExit(1) from exc

    # Write session — re-fetch to get ORM instances attached to this session
    async with async_session() as session:
        result = await session.execute(
            select(Question).where(Question.id.in_([q.id for q in questions]))
        )
        db_questions = {q.id: q for q in result.scalars().all()}

        for question, vector in zip(questions, vectors):
            db_q = db_questions.get(question.id)
            if db_q is not None:
                db_q.embedding = vector

        await session.commit()

    print(f"Done. Embedded {len(questions)} questions ({tokens:,} tokens used).")
    print(f"Total tokens this session: {embedding_service.total_tokens:,}")


if __name__ == "__main__":
    asyncio.run(main())
