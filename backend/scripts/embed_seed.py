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

    # Chunk so a large corpus doesn't go out in one oversized Jina call.
    chunk_size = 500
    total = len(questions)
    print(f"Embedding {total} questions via Jina ({chunk_size}/chunk)...")

    embedded = 0
    for start in range(0, total, chunk_size):
        chunk = questions[start:start + chunk_size]
        texts = [q.text for q in chunk]

        try:
            vectors, tokens = await embedding_service.embed_batch(
                texts, task="retrieval.passage"
            )
        except EmbeddingError as exc:
            print(f"Embedding failed on chunk starting at {start}: {exc}")
            raise SystemExit(1) from exc

        # Write session — re-fetch to get ORM instances attached to this session
        async with async_session() as session:
            result = await session.execute(
                select(Question).where(Question.id.in_([q.id for q in chunk]))
            )
            db_questions = {q.id: q for q in result.scalars().all()}

            for question, vector in zip(chunk, vectors, strict=True):
                db_q = db_questions.get(question.id)
                if db_q is not None:
                    db_q.embedding = vector

            await session.commit()

        embedded += len(chunk)
        print(f"  chunk {start // chunk_size + 1}: embedded {embedded}/{total} "
              f"({tokens:,} tokens)")

    print(f"Done. Embedded {embedded} questions.")
    print(f"Total tokens this session: {embedding_service.total_tokens:,}")


if __name__ == "__main__":
    asyncio.run(main())
