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
    title: str = Field(min_length=3, max_length=200)
    topics: list[str] = Field(min_length=1)
    difficulty: Literal["junior", "mid", "senior"]


class InterviewUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    topics: list[str] | None = None
    difficulty: Literal["junior", "mid", "senior"] | None = None


class InterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    topics: list[str]
    difficulty: str
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
    """
    Single answer + evaluation for results view.
    question_text comes from a JOIN — not a column on responses.
    Service must pass it explicitly via model_validate({...}).
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_text: str
    answer_text: str
    score: float | None
    accuracy: float | None
    completeness: float | None
    clarity: float | None
    feedback: str | None
    latency_ms: int | None
    created_at: datetime


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
