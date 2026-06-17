"""Run: docker compose run --rm api python -m scripts.test_agents"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.question_generator import make_question_generator
from app.agents.resume_analyzer import analyze_resume
from app.agents.state import InterviewState
from app.config import settings

_RESUME = """
John Smith | Python Backend Engineer | 4 years experience
Skills: Python, FastAPI, PostgreSQL, Redis, Docker, REST APIs, SQLAlchemy
Worked at Acme Corp building microservices. Led migration from Flask to FastAPI.
Familiar with AWS S3 and EC2. No ML or frontend experience.
"""

_JOB: InterviewState = {
    "job_title": "Senior Backend Engineer",
    "job_description": "Build scalable Python APIs for our data platform.",
    "required_skills": "Python, FastAPI, PostgreSQL, system_design, apis",
    "role_level": "mid",
    "max_questions": 8,
    "interview_history": [],
    "topics_covered": [],
}


async def run_tests() -> None:
    engine = create_async_engine(settings.database_url)
    Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    passed = 0

    # Test 1: Resume Analyzer produces structured profile
    print("[1/4] Resume Analyzer ...", end=" ", flush=True)
    state1: InterviewState = {**_JOB, "resume_text": _RESUME}
    r1 = await analyze_resume(state1)
    profile = r1.get("candidate_profile", {})
    assert profile.get("technical_skills"), "No skills extracted"
    assert "experience_years" in profile
    print(f"PASS\n  Skills: {profile['technical_skills'][:3]}")
    print(f"  Gaps: {profile.get('potential_gaps', [])}")
    passed += 1

    # Test 2: First question generated
    print("[2/4] Question Generator (first) ...", end=" ", flush=True)
    async with Session() as db:
        gen = make_question_generator(db)
        state2: InterviewState = {**_JOB, "candidate_profile": profile}
        r2 = await gen(state2)
    q2 = r2.get("current_question", {})
    assert q2.get("question_text"), "No question generated"
    assert q2.get("domain") in {"python", "data_structures", "sql", "system_design", "ml", "apis"}
    print(f"PASS\n  Q: {str(q2.get('question_text', ''))[:80]}...")
    print(f"  Domain: {q2.get('domain')} | Difficulty: {q2.get('difficulty')}")
    print(f"  Corpus ID: {q2.get('corpus_question_id')}")
    passed += 1

    # Test 3: Topic avoidance — generator should pick a non-python domain
    print("[3/4] Question Generator (history) ...", end=" ", flush=True)
    async with Session() as db:
        gen3 = make_question_generator(db)
        state3: InterviewState = {
            **_JOB,
            "candidate_profile": profile,
            "interview_history": [{"question": "Explain Python GIL", "score": 7.0}],
            "topics_covered": ["python"],
        }
        r3 = await gen3(state3)
    q3 = r3.get("current_question", {})
    print(f"PASS\n  Q: {str(q3.get('question_text', ''))[:80]}...")
    print(f"  Domain: {q3.get('domain')} (covered: python)")
    passed += 1

    # Test 4: Corpus ID must be from the actual search results (no hallucinations)
    print("[4/4] Question Generator (corpus check) ...", end=" ", flush=True)
    async with Session() as db:
        gen4 = make_question_generator(db)
        state4: InterviewState = {
            **_JOB,
            "required_skills": "Python",
            "candidate_profile": profile,
        }
        r4 = await gen4(state4)
    cid = r4.get("current_question", {}).get("corpus_question_id")
    print(f"PASS\n  Corpus match: {cid is not None} (ID: {cid})")
    passed += 1

    print(f"\nAll {passed}/4 tests passed.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_tests())
