from httpx import AsyncClient


async def test_health_endpoint_enhanced(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    for key in ("status", "database", "redis", "groq_circuit", "gemini_circuit"):
        assert key in data
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert data["database"] == "connected"  # DB is up in the test environment
