import asyncio
import os
from collections.abc import AsyncGenerator

import asyncpg  # type: ignore[import]
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://interviewai:localdev123@localhost:5432/interviewai_test",
)
# Picked up by alembic/env.py when running migrations during setup
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL

_test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_size=5)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)

_TRUNCATE = text(
    "TRUNCATE responses, candidate_sessions, interview_questions, "
    "interviews, questions, users RESTART IDENTITY CASCADE"
)


def _make_test_pdf() -> bytes:
    """Create a minimal valid PDF using PyMuPDF for upload tests."""
    import fitz  # type: ignore[import]

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "Senior Python Developer\nSkills: Python, FastAPI, PostgreSQL, Redis"
    )
    return doc.tobytes()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database() -> None:
    """Create interviewai_test DB, enable pgvector, run Alembic migrations — once per session."""
    no_driver = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    admin_dsn = no_driver.rsplit("/", 1)[0] + "/postgres"
    test_dsn = no_driver

    async def _prepare() -> None:
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute("CREATE DATABASE interviewai_test")
        except asyncpg.exceptions.DuplicateDatabaseError:
            pass
        finally:
            await conn.close()

        conn = await asyncpg.connect(test_dsn)
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            await conn.close()

    asyncio.run(_prepare())

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def disable_rate_limiter() -> None:
    """Disable slowapi rate limiting so tests can call auth endpoints freely."""
    from app.routers.auth import limiter

    limiter.enabled = False


@pytest.fixture(autouse=True)
def mock_llm_and_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the agent pipeline offline and deterministic in CI.

    Replaces the real LLM call and the RAG hybrid search (which would hit the
    Jina embedding API) so endpoint tests run without API keys. Real LLM/RAG
    behaviour is covered locally by scripts/test_agents.py.
    """
    from typing import Any

    from app.services.llm_service import llm_service
    from app.services.rag_service import rag_service

    def fake_call_llm(
        prompt: str, system_prompt: str = "", response_model: Any = None
    ) -> dict[str, Any]:
        if "analyzing a candidate's resume" in prompt:
            return {
                "technical_skills": ["Python", "FastAPI", "PostgreSQL"],
                "experience_years": 5,
                "seniority_assessment": "senior",
                "primary_languages": ["Python"],
                "strengths": ["Backend APIs", "System design"],
                "potential_gaps": ["Frontend", "ML"],
                "experience_summary": "Experienced Python backend engineer.",
            }
        if "designing interview questions" in prompt:
            return {
                "question_text": "How would you design a rate limiter for a public API?",
                "domain": "system_design",
                "difficulty": "medium",
                "reference_answer": "Token bucket or sliding window with a shared store.",
                "corpus_question_id": None,
                "reasoning": "Covers system design, a required skill.",
            }
        if "evaluating a candidate's answer" in prompt:
            return {
                "score": 7.5,
                "accuracy": 8.0,
                "completeness": 7.0,
                "clarity": 7.5,
                "feedback": "Solid answer covering the key concepts.",
            }
        if "deciding whether to probe" in prompt:
            return {
                "needs_follow_up": False,
                "follow_up_question": None,
                "reasoning": "Answer was sufficiently complete.",
            }
        return {}

    async def fake_hybrid_search(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(llm_service, "call_llm", fake_call_llm)
    monkeypatch.setattr(rag_service, "hybrid_search", fake_hybrid_search)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Raw DB session for direct manipulation (e.g. setting expires_at to the past).
    Disposes the pool first so this test always gets fresh connections in its event loop
    (pytest-asyncio creates a new event loop per test by default; without dispose, the
    pool reuses connections from the previous loop and asyncpg raises InterfaceError).
    Teardown truncates all tables so the next test starts clean."""
    await _test_engine.dispose()  # clear stale connections from previous test's event loop

    async with _test_session_factory() as session:
        yield session

    async with _test_session_factory() as cleanup:
        await cleanup.execute(_TRUNCATE)
        await cleanup.commit()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with the FastAPI app and test DB wired up.
    Depends on db_session to ensure cleanup runs after the client closes."""
    from app.database import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with _test_session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=True
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Signs up a test user and returns Bearer auth headers."""
    r = await client.post(
        "/api/auth/signup",
        json={"email": "tester@example.com", "name": "Test User", "password": "strongpass123"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


_INTERVIEW_PAYLOAD = {
    "job_title": "Senior Python Developer",
    "job_description": (
        "We are building a high-scale distributed platform and need an experienced "
        "Python developer with strong backend and system design skills."
    ),
    "required_skills": "Python, FastAPI, PostgreSQL, Redis, system design",
    "role_level": "senior",
    "max_questions": 8,
}


@pytest_asyncio.fixture
async def sample_interview(client: AsyncClient, auth_headers: dict[str, str]) -> dict:
    """Interview + published + candidate session with uploaded resume.
    Returns {interview_id, session_id, token, auth_headers}."""
    r = await client.post("/api/interviews", json=_INTERVIEW_PAYLOAD, headers=auth_headers)
    assert r.status_code == 201
    interview_id = r.json()["id"]

    r = await client.post(f"/api/interviews/{interview_id}/publish", headers=auth_headers)
    assert r.status_code == 200

    pdf_bytes = _make_test_pdf()
    r = await client.post(
        f"/api/interviews/{interview_id}/candidates",
        data={"candidate_name": "Test Candidate", "candidate_email": "candidate@example.com"},
        files={"resume": ("resume.pdf", pdf_bytes, "application/pdf")},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()

    return {
        "interview_id": interview_id,
        "session_id": data["id"],
        "token": data["token"],
        "auth_headers": auth_headers,
    }
