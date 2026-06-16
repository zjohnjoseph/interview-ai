from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Jina API call failed after retries."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class EmbeddingService:
    JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"
    JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"

    def __init__(self) -> None:
        self.total_tokens: int = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def _call_jina(
        self, texts: list[str], task: str
    ) -> tuple[list[list[float]], int]:
        payload: dict[str, Any] = {
            "model": settings.jina_embedding_model,
            "input": texts,
            "task": task,
            "dimensions": settings.embedding_dimension,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.JINA_EMBED_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.jina_api_key}"},
            )
            response.raise_for_status()
        data: dict[str, Any] = response.json()
        vectors: list[list[float]] = [
            item["embedding"]
            for item in sorted(data["data"], key=lambda x: x["index"])
        ]
        tokens: int = data["usage"]["total_tokens"]
        return vectors, tokens

    async def embed_text(
        self, text: str, task: str = "retrieval.passage"
    ) -> list[float]:
        try:
            vectors, tokens = await self._call_jina([text], task)
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"Jina API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        self.total_tokens += tokens
        logger.info(
            "Embedding call (single)",
            extra={"tokens": tokens, "task": task},
        )
        return vectors[0]

    async def embed_batch(
        self, texts: list[str], task: str = "retrieval.passage"
    ) -> tuple[list[list[float]], int]:
        if not texts:
            return [], 0
        start = time.monotonic()
        try:
            vectors, tokens = await self._call_jina(texts, task)
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                f"Jina API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        self.total_tokens += tokens
        latency_ms = round((time.monotonic() - start) * 1000)
        logger.info(
            "Embedding call (batch)",
            extra={"count": len(texts), "tokens": tokens, "latency_ms": latency_ms},
        )
        return vectors, tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def rerank(
        self, query: str, documents: list[str], top_n: int = 5
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": settings.jina_reranker_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.JINA_RERANK_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.jina_api_key}"},
            )
            response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [
            {"index": item["index"], "relevance_score": item["relevance_score"]}
            for item in data["results"]
        ]


embedding_service = EmbeddingService()
