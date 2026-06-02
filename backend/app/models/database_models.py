import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# ─── 1. USERS ───────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="interviewer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


# ─── 2. QUESTIONS ────────────────────────────────────────────
class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_answer: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(768), nullable=True)  # Jina v3
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    interview_questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="question"
    )


# ─── 3. INTERVIEWS ──────────────────────────────────────────
class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="interviews")
    sessions: Mapped[list["CandidateSession"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    interview_questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.order",
    )


# ─── 4. INTERVIEW ↔ QUESTION (junction table) ───────────────
class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id"), primary_key=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    interview: Mapped["Interview"] = relationship(back_populates="interview_questions")
    question: Mapped["Question"] = relationship(back_populates="interview_questions")


# ─── 5. CANDIDATE SESSIONS ──────────────────────────────────
class CandidateSession(Base):
    __tablename__ = "candidate_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    candidate_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    candidate_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    interview: Mapped["Interview"] = relationship(
        back_populates="sessions"
    )
    responses: Mapped[list["Response"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


# ─── 6. RESPONSES (candidate answers + evaluation) ──────────
class Response(Base):
    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_sessions.id"), nullable=False
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    clarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    session: Mapped["CandidateSession"] = relationship(back_populates="responses")
    question: Mapped["Question"] = relationship()