import asyncio
from typing import Any

import pytest

from app.services.redis_service import redis_service


async def test_redis_cache_hit() -> None:
    await redis_service.set_cached("interviewai:test:hit", {"a": 1, "b": "x"})
    assert await redis_service.get_cached("interviewai:test:hit") == {"a": 1, "b": "x"}


async def test_redis_cache_miss() -> None:
    assert await redis_service.get_cached("interviewai:test:missing") is None


async def test_redis_cache_expiry() -> None:
    await redis_service.set_cached("interviewai:test:exp", {"a": 1}, ttl_seconds=1)
    await asyncio.sleep(2)
    assert await redis_service.get_cached("interviewai:test:exp") is None


async def test_redis_graceful_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    """If Redis raises on every call, the wrapper degrades to miss/no-op."""

    class Boom:
        async def get(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("redis down")

        async def set(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("redis down")

        async def ping(self, *a: Any, **k: Any) -> None:
            raise RuntimeError("redis down")

    monkeypatch.setattr(redis_service, "_client", Boom())

    assert await redis_service.get_cached("interviewai:test:x") is None
    await redis_service.set_cached("interviewai:test:x", {"a": 1})  # must not raise
    assert await redis_service.is_healthy() is False
