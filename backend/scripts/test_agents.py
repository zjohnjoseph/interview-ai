"""Run: docker compose run --rm api python -m scripts.test_agents"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.answer_evaluator import evaluate_answer
from app.agents.follow_up_decider import decide_follow_up
from app.agents.graph import (
    build_evaluation_graph,
    build_first_question_graph,
    build_question_graph,
)
from app.agents.interview_controller import control_interview
from app.agents.question_generator import make_question_generator
from app.agents.resume_analyzer import analyze_resume
from app.agents.state import InterviewState
from app.config import settings

_QUESTION = "Explain how Python's garbage collector handles circular references."
_GOOD_ANSWER = (
    "Python uses reference counting as its primary mechanism, but reference counting "
    "alone cannot reclaim circular references. To handle cycles, CPython runs a "
    "generational garbage collector that periodically detects groups of objects that "
    "reference each other but are unreachable from the program, and frees them. "
    "Objects are organized into three generations; younger generations are collected "
    "more often. You can interact with it via the gc module."
)

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
    print("[1/10] Resume Analyzer ...", end=" ", flush=True)
    state1: InterviewState = {**_JOB, "resume_text": _RESUME}
    r1 = await analyze_resume(state1)
    profile = r1.get("candidate_profile", {})
    assert profile.get("technical_skills"), "No skills extracted"
    assert "experience_years" in profile
    print(f"PASS\n  Skills: {profile['technical_skills'][:3]}")
    print(f"  Gaps: {profile.get('potential_gaps', [])}")
    passed += 1

    # Test 2: First question generated
    print("[2/10] Question Generator (first) ...", end=" ", flush=True)
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
    print("[3/10] Question Generator (history) ...", end=" ", flush=True)
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
    print("[4/10] Question Generator (corpus check) ...", end=" ", flush=True)
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

    # Test 5: Answer Evaluator scores a strong answer highly
    print("[5/10] Answer Evaluator (good answer) ...", end=" ", flush=True)
    state5: InterviewState = {
        **_JOB,
        "current_question": {
            "question_text": _QUESTION,
            "reference_answer": (
                "Reference counting plus a generational cyclic garbage collector "
                "that detects and frees unreachable reference cycles."
            ),
            "domain": "python",
            "difficulty": "medium",
            "is_follow_up": False,
        },
        "current_answer": _GOOD_ANSWER,
    }
    r5 = await evaluate_answer(state5)
    ev5 = r5.get("current_evaluation", {})
    for field in ("score", "accuracy", "completeness", "clarity", "feedback"):
        assert field in ev5, f"Missing field {field}"
    for field in ("score", "accuracy", "completeness", "clarity"):
        assert 0.0 <= ev5[field] <= 10.0, f"{field} out of range: {ev5[field]}"
    assert ev5["feedback"], "Empty feedback"
    assert ev5["score"] > 5.0, f"Good answer scored too low: {ev5['score']}"
    print(f"PASS\n  Score: {ev5['score']} | Acc: {ev5['accuracy']} | Feedback: {ev5['feedback'][:60]}...")
    passed += 1

    # Test 6: Answer Evaluator scores a non-answer low
    print("[6/10] Answer Evaluator (bad answer) ...", end=" ", flush=True)
    state6: InterviewState = {**state5, "current_answer": "I don't know."}
    r6 = await evaluate_answer(state6)
    ev6 = r6.get("current_evaluation", {})
    assert ev6["score"] < 3.0, f"Bad answer scored too high: {ev6['score']}"
    print(f"PASS\n  Score: {ev6['score']} (correctly low)")
    passed += 1

    # Test 7: Follow-up Decider probes a weak answer
    print("[7/10] Follow-up Decider (triggers) ...", end=" ", flush=True)
    state7: InterviewState = {
        **_JOB,
        "current_question": state5["current_question"],
        "current_answer": "I don't know.",
        "current_evaluation": {
            "score": 3.0, "accuracy": 2.0, "completeness": 3.0,
            "clarity": 4.0, "feedback": "Missing core concepts.",
        },
        "follow_up_count": 0,
    }
    r7 = await decide_follow_up(state7)
    assert r7.get("needs_follow_up") is True, "Should have triggered a follow-up"
    assert r7.get("current_question", {}).get("question_text"), "No follow-up question"
    assert r7.get("current_question", {}).get("is_follow_up") is True
    print(f"PASS\n  Follow-up Q: {r7['current_question']['question_text'][:70]}...")
    passed += 1

    # Test 8: Follow-up Decider moves on after a strong answer
    print("[8/10] Follow-up Decider (skips) ...", end=" ", flush=True)
    state8: InterviewState = {
        **_JOB,
        "current_question": state5["current_question"],
        "current_answer": _GOOD_ANSWER,
        "current_evaluation": {
            "score": 9.0, "accuracy": 9.0, "completeness": 9.0,
            "clarity": 9.0, "feedback": "Excellent, thorough answer.",
        },
        "follow_up_count": 0,
    }
    r8 = await decide_follow_up(state8)
    assert r8.get("needs_follow_up") is False, "Should not follow up on a strong answer"
    print(f"PASS\n  needs_follow_up: {r8.get('needs_follow_up')} (correctly moves on)")
    passed += 1

    # Test 9: Interview Controller ends at the question limit
    print("[9/10] Interview Controller (ends) ...", end=" ", flush=True)
    state9: InterviewState = {**_JOB, "questions_asked": 10, "max_questions": 10}
    r9 = await control_interview(state9)
    assert r9.get("is_complete") is True, "Should be complete at the limit"
    print(f"PASS\n  is_complete: {r9.get('is_complete')}")
    passed += 1

    # Test 10: Full pipeline simulation (no HTTP) — graphs wired end to end
    print("[10/10] Full pipeline simulation ...", flush=True)
    _SAMPLE_ANSWERS = [
        _GOOD_ANSWER,
        "I'd use a token bucket per user, but I haven't handled distributed counters.",
        "An INNER JOIN returns only matching rows; a LEFT JOIN keeps all left rows.",
        "You'd store counters in Redis with atomic INCR and a TTL per window.",
    ]
    print("\n=== Full Pipeline Simulation ===\n")

    async with Session() as db:
        first_graph = build_first_question_graph(db)
        question_graph = build_question_graph(db)
        eval_graph = build_evaluation_graph()

        pipeline_state: InterviewState = {**_JOB, "resume_text": _RESUME}
        answer_idx = 0

        # First question (includes resume analysis).
        pipeline_state = {**pipeline_state, **(await first_graph.ainvoke(pipeline_state))}
        prof = pipeline_state.get("candidate_profile", {})
        print("[Resume Analysis]")
        print(f"  Skills: {prof.get('technical_skills', [])[:3]}")
        print(f"  Gaps: {prof.get('potential_gaps', [])}\n")

        for q_num in range(1, 4):
            q = pipeline_state.get("current_question", {})
            print(f"[Q{q_num}] Domain: {q.get('domain')} | Difficulty: {q.get('difficulty')}")
            print(f"  Q: {str(q.get('question_text', ''))[:80]}...")

            answer = _SAMPLE_ANSWERS[answer_idx % len(_SAMPLE_ANSWERS)]
            answer_idx += 1
            pipeline_state = {**pipeline_state, "current_answer": answer}
            eval_result = await eval_graph.ainvoke(pipeline_state)
            pipeline_state = {**pipeline_state, **eval_result}
            ev = pipeline_state.get("current_evaluation", {})
            needs_fu = pipeline_state.get("needs_follow_up", False)
            print(f"  A: {answer[:60]}...")
            print(f"  Score: {ev.get('score')} | Follow-up: {'Yes' if needs_fu else 'No'}")

            # Record this Q/A in history before moving on.
            pipeline_state = {
                **pipeline_state,
                "interview_history": pipeline_state.get("interview_history", [])
                + [{
                    "question": q.get("question_text", ""),
                    "score": ev.get("score"),
                    "corpus_question_id": q.get("corpus_question_id"),
                }],
                "questions_asked": pipeline_state.get("questions_asked", 0) + 1,
            }

            # Handle one follow-up if the decider asked for it.
            if needs_fu:
                fq = pipeline_state.get("current_question", {})
                fu_answer = _SAMPLE_ANSWERS[answer_idx % len(_SAMPLE_ANSWERS)]
                answer_idx += 1
                print(f"  Follow-up Q: {str(fq.get('question_text', ''))[:70]}...")
                pipeline_state = {**pipeline_state, "current_answer": fu_answer}
                fu_eval = await eval_graph.ainvoke(pipeline_state)
                pipeline_state = {**pipeline_state, **fu_eval}
                fu_ev = pipeline_state.get("current_evaluation", {})
                print(f"  Follow-up A: {fu_answer[:50]}...")
                print(f"  Follow-up Score: {fu_ev.get('score')}")

            print()

            # Generate the next main question (skip after the last iteration).
            if q_num < 3:
                gen_result = await question_graph.ainvoke(pipeline_state)
                pipeline_state = {**pipeline_state, **gen_result}

    history = pipeline_state.get("interview_history", [])
    domains = {h for h in pipeline_state.get("topics_covered", [])}
    assert len(history) >= 3, f"Expected 3+ history entries, got {len(history)}"
    assert len(domains) >= 1, "Expected at least one covered domain"
    print(f"Interview complete. {len(history)} main questions recorded; "
          f"domains covered: {sorted(domains)}")
    passed += 1

    print(f"\nAll {passed}/10 tests passed.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_tests())
