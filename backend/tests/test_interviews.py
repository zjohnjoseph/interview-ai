from httpx import AsyncClient

_INTERVIEW = {
    "title": "Python Fundamentals Interview",
    "topics": ["python", "oop"],
    "difficulty": "mid",
}

_QUESTION = {
    "text": "Explain Python's GIL and its impact on multi-threaded programs in detail.",
    "domain": "python",
    "difficulty": "medium",
    "reference_answer": "A comprehensive explanation of the Global Interpreter Lock.",
}


async def _make_question(client: AsyncClient, headers: dict[str, str]) -> str:
    r = await client.post("/api/questions", json=_QUESTION, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


async def test_create_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "draft"
    assert data["title"] == _INTERVIEW["title"]
    assert data["difficulty"] == "mid"


async def test_list_interviews_only_own(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)

    r = await client.post(
        "/api/auth/signup",
        json={"email": "userb@example.com", "name": "User B", "password": "strongpass123"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}
    await client.post(
        "/api/interviews",
        json={**_INTERVIEW, "title": "User B Interview"},
        headers=headers_b,
    )

    r = await client.get("/api/interviews", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["title"] == _INTERVIEW["title"]


async def test_get_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.get(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == interview_id


async def test_update_interview(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.patch(
        f"/api/interviews/{interview_id}",
        json={"title": "Updated Interview Title"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Updated Interview Title"
    assert data["difficulty"] == "mid"  # unchanged


async def test_delete_interview_soft(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.delete(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 204

    r = await client.get(f"/api/interviews/{interview_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


async def test_publish_without_questions(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 400


async def test_publish_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    qid = await _make_question(client, auth_headers)
    await client.post(
        f"/api/interviews/{interview_id}/questions",
        json={"questions": [{"question_id": qid, "order": 1}]},
        headers=auth_headers,
    )

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert len(data["token"]) > 10


async def test_update_active_interview_blocked(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    qid = await _make_question(client, auth_headers)
    await client.post(
        f"/api/interviews/{interview_id}/questions",
        json={"questions": [{"question_id": qid, "order": 1}]},
        headers=auth_headers,
    )
    await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)

    r = await client.patch(
        f"/api/interviews/{interview_id}",
        json={"title": "Cannot Change This"},
        headers=auth_headers,
    )
    assert r.status_code == 400


async def test_other_user_gets_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    r = await client.post("/api/interviews", json=_INTERVIEW, headers=auth_headers)
    interview_id = r.json()["id"]

    r = await client.post(
        "/api/auth/signup",
        json={"email": "intruder@example.com", "name": "Intruder", "password": "strongpass123"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get(f"/api/interviews/{interview_id}", headers=headers_b)
    assert r.status_code == 404
