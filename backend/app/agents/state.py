from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class InterviewState(TypedDict, total=False):
    # Job context (set once at graph entry)
    job_title: str
    job_description: str
    required_skills: str
    role_level: str
    max_questions: int
    # Candidate inputs
    resume_text: str
    candidate_profile: dict[str, Any]
    # Conversation tracking — list fields use Annotated reducers for append semantics
    interview_history: Annotated[list[dict[str, Any]], operator.add]
    current_question: dict[str, Any] | None
    current_evaluation: dict[str, Any] | None
    current_answer: str | None  # set by endpoint before evaluation graph runs
    questions_asked: int
    follow_up_count: int
    needs_follow_up: bool  # output of decide_follow_up; read by router
    topics_covered: Annotated[list[str], operator.add]
    is_complete: bool
    error: str | None
