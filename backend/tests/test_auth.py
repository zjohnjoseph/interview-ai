from httpx import AsyncClient

_SIGNUP = {
    "email": "user@example.com",
    "name": "Example User",
    "password": "strongpass123",
}


async def test_signup_success(client: AsyncClient) -> None:
    r = await client.post("/api/auth/signup", json=_SIGNUP)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_success(client: AsyncClient) -> None:
    await client.post("/api/auth/signup", json=_SIGNUP)
    r = await client.post(
        "/api/auth/login",
        json={"email": _SIGNUP["email"], "password": _SIGNUP["password"]},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


async def test_me_with_valid_token(client: AsyncClient) -> None:
    r = await client.post("/api/auth/signup", json=_SIGNUP)
    token = r.json()["access_token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    data = me.json()
    assert data["email"] == _SIGNUP["email"]
    assert data["name"] == _SIGNUP["name"]
    assert data["role"] == "interviewer"


async def test_signup_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/auth/signup", json=_SIGNUP)
    r = await client.post("/api/auth/signup", json=_SIGNUP)
    assert r.status_code == 409


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/auth/signup", json=_SIGNUP)
    r = await client.post(
        "/api/auth/login",
        json={"email": _SIGNUP["email"], "password": "wrongpassword"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


async def test_login_nonexistent_email(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "irrelevant"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


async def test_me_without_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me")
    assert r.status_code == 403


async def test_me_with_invalid_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage123"})
    assert r.status_code == 401
