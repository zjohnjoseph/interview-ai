from __future__ import annotations

import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.answer_evaluator import evaluate_answer
from app.agents.follow_up_decider import decide_follow_up
from app.agents.interview_controller import control_interview
from app.agents.question_generator import make_question_generator
from app.agents.resume_analyzer import analyze_resume
from app.agents.state import InterviewState
from app.models.database_models import CandidateSession, Interview, Response

logger = logging.getLogger(__name__)


def build_first_question_graph(db: AsyncSession) -> Any:
    """First turn of an interview: analyze the resume, then generate a question."""
    graph = StateGraph(InterviewState)
    graph.add_node("analyze_resume", analyze_resume)
    graph.add_node("generate_question", make_question_generator(db))
    graph.set_entry_point("analyze_resume")
    graph.add_edge("analyze_resume", "generate_question")
    graph.add_edge("generate_question", END)
    return graph.compile()


def build_question_graph(db: AsyncSession) -> Any:
    """Subsequent turns: generate the next main question from existing state."""
    graph = StateGraph(InterviewState)
    graph.add_node("generate_question", make_question_generator(db))
    graph.set_entry_point("generate_question")
    graph.add_edge("generate_question", END)
    return graph.compile()


def route_after_follow_up(state: InterviewState) -> str:
    """Conditional edge: probe deeper (pause) or hand off to the controller."""
    if state.get("needs_follow_up", False):
        return "follow_up"
    return "next_question"


def build_evaluation_graph() -> Any:
    """Score an answer, decide on a follow-up, then check whether to continue."""
    graph = StateGraph(InterviewState)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("decide_follow_up", decide_follow_up)
    graph.add_node("control_interview", control_interview)

    graph.set_entry_point("evaluate_answer")
    graph.add_edge("evaluate_answer", "decide_follow_up")
    graph.add_conditional_edges(
        "decide_follow_up",
        route_after_follow_up,
        {
            "follow_up": END,  # pause — return the follow-up to the candidate
            "next_question": "control_interview",
        },
    )
    graph.add_edge("control_interview", END)
    return graph.compile()


async def build_state_from_db(
    session: CandidateSession,
    interview: Interview,
    db: AsyncSession,
) -> InterviewState:
    """Reconstruct the full InterviewState from persisted records.

    State must survive between HTTP requests, so it is rebuilt from the
    interview, session, and response rows rather than held in memory.
    """
    responses = list(
        (
            await db.execute(
                select(Response)
                .where(Response.session_id == session.id)
                .order_by(Response.created_at)
            )
        )
        .scalars()
        .all()
    )

    candidate_profile: dict[str, Any] = {}
    if session.candidate_profile:
        try:
            candidate_profile = json.loads(session.candidate_profile)
        except (ValueError, TypeError) as exc:
            logger.warning("Could not parse stored candidate_profile: %s", exc)

    interview_history: list[dict[str, Any]] = []
    topics_covered: list[str] = []
    questions_asked = 0
    for r in responses:
        interview_history.append(
            {
                "question": r.question_text,
                "score": r.score,
                "corpus_question_id": str(r.question_id) if r.question_id else None,
            }
        )
        if r.domain and r.domain not in topics_covered:
            topics_covered.append(r.domain)
        if not r.is_follow_up:
            questions_asked += 1

    return {
        "job_title": interview.job_title,
        "job_description": interview.job_description,
        "required_skills": interview.required_skills,
        "role_level": interview.role_level,
        "max_questions": interview.max_questions,
        "resume_text": session.resume_text or "",
        "candidate_profile": candidate_profile,
        "interview_history": interview_history,
        "topics_covered": topics_covered,
        "questions_asked": questions_asked,
        "follow_up_count": 0,
    }
