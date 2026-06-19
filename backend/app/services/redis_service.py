from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "interviewai:"


class RedisService:
    """Thin async wrapper around Redis with graceful degradation.

    Redis is a performance optimization, never a hard dependency. Every
    operation is wrapped so that if Redis is down the caller sees a cache
    miss / no-op rather than an exception — the interview flow continues.
    """

    def __init__(self) -> None:
        self._client = aioredis.from_url(settings.redis_url, decode_responses=True)

    # --- key builders -----------------------------------------------------
    @staticmethod
    def eval_key(question_hash: str) -> str:
        return f"{_PREFIX}eval:{question_hash}"

    @staticmethod
    def state_key(session_id: str) -> str:
        return f"{_PREFIX}state:{session_id}"

    @staticmethod
    def daily_tokens_key(date: str) -> str:
        return f"{_PREFIX}tokens:{date}"

    @staticmethod
    def session_tokens_key(session_id: str) -> str:
        return f"{_PREFIX}tokens:session:{session_id}"

    # --- core operations --------------------------------------------------
    async def get_cached(self, key: str) -> dict[str, Any] | None:
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            value: dict[str, Any] = json.loads(raw)
            return value
        except Exception as exc:
            logger.warning("Redis get_cached failed for %s: %s", key, exc)
            return None

    async def set_cached(
        self, key: str, value: dict[str, Any], ttl_seconds: int = 300
    ) -> None:
        try:
            await self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:
            logger.warning("Redis set_cached failed for %s: %s", key, exc)

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.warning("Redis delete failed for %s: %s", key, exc)

    async def incr_by(self, key: str, amount: int, ttl_seconds: int) -> int:
        try:
            total = int(await self._client.incrby(key, amount))
            await self._client.expire(key, ttl_seconds)
            return total
        except Exception as exc:
            logger.warning("Redis incr_by failed for %s: %s", key, exc)
            return 0

    async def get_int(self, key: str) -> int:
        try:
            raw = await self._client.get(key)
            return int(raw) if raw is not None else 0
        except Exception as exc:
            logger.warning("Redis get_int failed for %s: %s", key, exc)
            return 0

    async def is_healthy(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception as exc:
            logger.warning("Redis health check failed: %s", exc)
            return False


redis_service = RedisService()
