from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CANDIDATE = {"candidate_name": "Alice Smith", "candidate_email": "alice@example.com"}
_STUB_TEXT = "Placeholder — LLM question generation coming in Phase 2"


async def test_join_session(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    r = await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)
    assert r.status_code == 200
    assert r.json()["status"] == "active"


async def test_join_already_active_session(
    client: AsyncClient, sample_interview: dict
) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)
    r = await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)
    assert r.status_code == 400


async def test_get_next_question(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    r = await client.get(f"/api/sessions/{token}/next")
    assert r.status_code == 200
    data = r.json()
    assert data["completed"] is False
    assert data["question"] is not None
    assert data["question"]["text"] == _STUB_TEXT
    assert "reference_answer" not in data["question"]
    assert data["questions_remaining"] == 8  # max_questions with no answers yet


async def test_submit_answer(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    r = await client.post(
        f"/api/sessions/{token}/answers",
        json={"answer_text": "This is my answer to the stub question."},
    )
    assert r.status_code == 200
    data = r.json()
    assert "response_id" in data
    assert "evaluation" in data
    assert data["is_last_question"] is False


async def test_full_interview_flow(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    for i in range(8):  # max_questions = 8
        r = await client.post(
            f"/api/sessions/{token}/answers",
            json={"answer_text": f"My answer to stub question {i + 1}."},
        )
        assert r.status_code == 200
        assert r.json()["is_last_question"] is (i == 7)

    r = await client.get(f"/api/sessions/{token}/next")
    assert r.status_code == 200
    assert r.json()["completed"] is True
    assert r.json()["question"] is None
    assert r.json()["questions_remaining"] == 0


async def test_answer_after_completion(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)
    for i in range(8):
        await client.post(
            f"/api/sessions/{token}/answers",
            json={"answer_text": f"Answer {i}."},
        )

    r = await client.post(
        f"/api/sessions/{token}/answers",
        json={"answer_text": "Extra answer after completion."},
    )
    assert r.status_code == 400


async def test_next_before_joining(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    r = await client.get(f"/api/sessions/{token}/next")
    assert r.status_code == 400


async def test_results_after_completion(
    client: AsyncClient, sample_interview: dict
) -> None:
    token = sample_interview["token"]
    session_id = sample_interview["session_id"]
    auth_headers = sample_interview["auth_headers"]

    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)
    for i in range(8):
        await client.post(
            f"/api/sessions/{token}/answers",
            json={"answer_text": f"Answer {i}."},
        )

    r = await client.get(f"/api/sessions/{session_id}/results", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["answered_questions"] == 8
    assert data["total_questions"] == 8
    assert len(data["responses"]) == 8
    for resp in data["responses"]:
        assert resp["question_text"] == _STUB_TEXT
        assert "is_follow_up" in resp
        assert resp["is_follow_up"] is False


async def test_results_ownership(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    session_id = sample_interview["session_id"]

    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    r = await client.post(
        "/api/auth/signup",
        json={"email": "userb_results@example.com", "name": "User B", "password": "strongpass123"},
    )
    headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get(f"/api/sessions/{session_id}/results", headers=headers_b)
    assert r.status_code == 404


async def test_list_sessions_for_interview(
    client: AsyncClient, sample_interview: dict
) -> None:
    interview_id = sample_interview["interview_id"]
    session_id = sample_interview["session_id"]
    auth_headers = sample_interview["auth_headers"]

    r = await client.get(f"/api/interviews/{interview_id}/sessions", headers=auth_headers)
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id


async def test_fake_token(client: AsyncClient) -> None:
    r = await client.get("/api/sessions/completelyfaketoken123456/next")
    assert r.status_code == 404


async def test_expired_token(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_interview: dict,
) -> None:
    token = sample_interview["token"]
    await db_session.execute(
        text(
            "UPDATE candidate_sessions SET expires_at = NOW() - INTERVAL '1 day' "
            "WHERE token = :t"
        ),
        {"t": token},
    )
    await db_session.commit()

    r = await client.get(f"/api/sessions/{token}/next")
    assert r.status_code == 410
