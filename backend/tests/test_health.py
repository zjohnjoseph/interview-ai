import pytest
from httpx import AsyncClient


async def test_health_endpoint_enhanced(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    for key in ("status", "database", "redis", "groq_circuit", "gemini_circuit"):
        assert key in data
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert data["database"] == "connected"  # DB is up in the test environment


async def test_health_degraded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis down → degraded (not unhealthy): the DB is still up, so the app works."""
    from app.services.redis_service import redis_service

    async def _down() -> bool:
        return False

    monkeypatch.setattr(redis_service, "is_healthy", _down)

    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["redis"] == "down"
    assert data["database"] == "connected"
