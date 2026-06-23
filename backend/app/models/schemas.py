import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ─── 3.1 AUTH ────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: str
    created_at: datetime


# ─── 3.2 INTERVIEWS ──────────────────────────────────────────

class InterviewCreate(BaseModel):
    job_title: str = Field(min_length=3, max_length=200)
    job_description: str = Field(min_length=50)
    required_skills: str = Field(min_length=5)
    role_level: Literal["junior", "mid", "senior"]
    max_questions: int = Field(default=10, ge=3, le=15)


class InterviewUpdate(BaseModel):
    job_title: str | None = Field(default=None, min_length=3, max_length=200)
    job_description: str | None = Field(default=None, min_length=50)
    required_skills: str | None = Field(default=None, min_length=5)
    role_level: Literal["junior", "mid", "senior"] | None = None
    max_questions: int | None = Field(default=None, ge=3, le=15)


class InterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_title: str
    job_description: str
    required_skills: str
    role_level: str
    max_questions: int
    status: str
    created_at: datetime


# ─── 3.3 QUESTIONS ───────────────────────────────────────────

class QuestionCreate(BaseModel):
    text: str = Field(min_length=10)
    domain: Literal["python", "data_structures", "sql", "system_design", "ml", "apis"]
    difficulty: Literal["easy", "medium", "hard"]
    reference_answer: str = Field(min_length=20)


class QuestionResponse(BaseModel):
    """Candidate-facing — reference_answer intentionally excluded."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    domain: str
    difficulty: str
    created_at: datetime


class QuestionDetailResponse(BaseModel):
    """Interviewer-facing — includes reference_answer."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    domain: str
    difficulty: str
    reference_answer: str
    created_at: datetime


# ─── 3.4 SESSIONS ────────────────────────────────────────────

class SessionCreate(BaseModel):
    candidate_email: EmailStr | None = None


class SessionJoin(BaseModel):
    candidate_name: str = Field(min_length=2)
    candidate_email: EmailStr


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_id: uuid.UUID
    token: str
    candidate_name: str | None
    candidate_email: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime


class SessionProgressResponse(BaseModel):
    total_questions: int = Field(ge=0)
    answered_questions: int = Field(ge=0)
    current_score: float | None = None


# ─── 3.5 ANSWERS & EVALUATION ────────────────────────────────

class AnswerSubmit(BaseModel):
    answer_text: str = Field(min_length=1, max_length=5000)


class EvaluationResponse(BaseModel):
    """LLM output guardrail — validates before any DB write."""
    score: float = Field(ge=0.0, le=10.0)
    accuracy: float = Field(ge=0.0, le=10.0)
    completeness: float = Field(ge=0.0, le=10.0)
    clarity: float = Field(ge=0.0, le=10.0)
    feedback: str


class ResponseDetail(BaseModel):
    """Single answer + evaluation. question_text and is_follow_up are columns on responses."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_text: str
    is_follow_up: bool
    answer_text: str
    score: float | None
    accuracy: float | None
    completeness: float | None
    clarity: float | None
    feedback: str | None
    latency_ms: int | None
    created_at: datetime


# ─── 3.5a RAG SEARCH ─────────────────────────────────────────

class SearchResultResponse(BaseModel):
    question_id: str
    text: str
    domain: str
    difficulty: str
    reference_answer: str
    relevance_score: float
    source: str  # "vector", "bm25", or "both"


# ─── 3.5b CANDIDATE FLOW ─────────────────────────────────────

class NextQuestionResponse(BaseModel):
    completed: bool
    question: QuestionResponse | None
    questions_remaining: int


class AnswerResponse(BaseModel):
    response_id: uuid.UUID
    question_text: str
    evaluation: EvaluationResponse
    is_last_question: bool


# ─── 3.6 RESULTS ─────────────────────────────────────────────

class SessionResultResponse(BaseModel):
    """
    Full scorecard for a completed session.
    overall_score is computed by the service (average of response scores),
    not stored in the DB.
    """
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    candidate_name: str | None
    candidate_email: str | None
    overall_score: float | None
    total_questions: int
    answered_questions: int
    responses: list[ResponseDetail]
    started_at: datetime | None
    completed_at: datetime | None
