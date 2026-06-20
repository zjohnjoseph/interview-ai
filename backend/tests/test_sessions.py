from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CANDIDATE = {"candidate_name": "Alice Smith", "candidate_email": "alice@example.com"}


async def _next_then_answer(client: AsyncClient, token: str, answer: str):  # type: ignore[no-untyped-def]
    """Fetch the pending question, then submit an answer to it."""
    await client.get(f"/api/sessions/{token}/next")
    return await client.post(
        f"/api/sessions/{token}/answers", json={"answer_text": answer}
    )


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
    assert data["question"]["text"]  # dynamic AI-generated text — just non-empty
    assert data["question"]["domain"]
    assert data["question"]["difficulty"]
    assert "reference_answer" not in data["question"]
    assert data["questions_remaining"] == 8  # max_questions with no answers yet


async def test_next_is_cached(client: AsyncClient, sample_interview: dict) -> None:
    """Calling /next twice without answering returns the same question."""
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    first = (await client.get(f"/api/sessions/{token}/next")).json()
    second = (await client.get(f"/api/sessions/{token}/next")).json()
    assert first["question"]["text"] == second["question"]["text"]


async def test_submit_answer(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    r = await _next_then_answer(client, token, "This is my detailed answer.")
    assert r.status_code == 200
    data = r.json()
    assert "response_id" in data
    ev = data["evaluation"]
    for field in ("score", "accuracy", "completeness", "clarity", "feedback"):
        assert field in ev
    assert data["is_last_question"] is False


async def test_answer_without_pending_question(
    client: AsyncClient, sample_interview: dict
) -> None:
    """Submitting an answer before calling /next returns 400."""
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    r = await client.post(
        f"/api/sessions/{token}/answers", json={"answer_text": "Premature answer."}
    )
    assert r.status_code == 400


async def test_full_interview_flow(client: AsyncClient, sample_interview: dict) -> None:
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    for i in range(8):  # max_questions = 8
        r = await _next_then_answer(client, token, f"My answer number {i + 1}.")
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
        await _next_then_answer(client, token, f"Answer {i}.")

    r = await client.post(
        f"/api/sessions/{token}/answers",
        json={"answer_text": "Extra answer after completion."},
    )
    assert r.status_code == 400


async def test_progress_endpoint(client: AsyncClient, sample_interview: dict) -> None:
    """GET /{token}/progress reports answered count and a running score."""
    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    for i in range(2):
        await _next_then_answer(client, token, f"Answer {i}.")

    r = await client.get(f"/api/sessions/{token}/progress")
    assert r.status_code == 200
    data = r.json()
    assert data["answered_questions"] == 2
    assert data["total_questions"] == 8
    assert data["current_score"] is not None


async def test_follow_up_cap(
    client: AsyncClient, sample_interview: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A main question gets at most 2 follow-ups, then the interview moves on."""
    from app.services.llm_service import llm_service

    def always_follow_up(
        prompt: str, system_prompt: str = "", response_model: Any = None
    ) -> dict[str, Any]:
        if "designing interview questions" in prompt:
            return {
                "question_text": "Explain database indexing.",
                "domain": "sql",
                "difficulty": "medium",
                "reference_answer": "B-tree indexes speed lookups.",
                "corpus_question_id": None,
                "reasoning": "Covers a required skill.",
            }
        if "evaluating a candidate's answer" in prompt:
            return {
                "score": 1.0, "accuracy": 1.0, "completeness": 1.0,
                "clarity": 1.0, "feedback": "Incorrect.",
            }
        if "deciding whether to probe" in prompt:
            return {
                "needs_follow_up": True,
                "follow_up_question": "Can you go deeper?",
                "reasoning": "Answer was weak.",
            }
        return {}  # resume analysis unused (history non-empty path not hit first)

    monkeypatch.setattr(llm_service, "call_llm", always_follow_up)

    token = sample_interview["token"]
    await client.post(f"/api/sessions/{token}/join", json=_CANDIDATE)

    # Q1, FU1, FU2, then a new main question (Q2) — 4 recorded responses.
    for _ in range(4):
        r = await _next_then_answer(client, token, "I don't know.")
        assert r.status_code == 200

    session_id = sample_interview["session_id"]
    auth_headers = sample_interview["auth_headers"]
    r = await client.get(f"/api/sessions/{session_id}/results", headers=auth_headers)
    assert r.status_code == 200
    flags = [resp["is_follow_up"] for resp in r.json()["responses"]]
    # Main Q1 gets exactly 2 follow-ups, then a fresh main question — not a 3rd probe.
    assert flags[:4] == [False, True, True, False]


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
        await _next_then_answer(client, token, f"Answer {i}.")

    r = await client.get(f"/api/sessions/{session_id}/results", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["answered_questions"] == 8
    assert data["total_questions"] == 8
    assert len(data["responses"]) == 8
    assert data["overall_score"] is not None and data["overall_score"] > 0
    for resp in data["responses"]:
        assert resp["question_text"]
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
