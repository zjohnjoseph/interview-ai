import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_session, get_current_user
from app.database import get_db
from app.models.database_models import (
    CandidateSession,
    Interview,
    InterviewQuestion,
    Question,
    Response,
    User,
)
from app.models.schemas import (
    AnswerResponse,
    AnswerSubmit,
    EvaluationResponse,
    NextQuestionResponse,
    QuestionResponse,
    ResponseDetail,
    SessionProgressResponse,
    SessionResultResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


async def _get_next_iq(
    session: CandidateSession, db: AsyncSession
) -> tuple[InterviewQuestion | None, int]:
    iqs = list(
        (
            await db.execute(
                select(InterviewQuestion)
                .where(InterviewQuestion.interview_id == session.interview_id)
                .order_by(InterviewQuestion.order)
            )
        ).scalars().all()
    )
    answered_ids = set(
        (
            await db.execute(
                select(Response.question_id).where(Response.session_id == session.id)
            )
        ).scalars().all()
    )
    remaining = [iq for iq in iqs if iq.question_id not in answered_ids]
    return (remaining[0] if remaining else None, len(remaining))


@router.get("/{token}/next", response_model=NextQuestionResponse)
async def get_next_question(
    token: str,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> NextQuestionResponse:
    if session.status == "pending":
        raise HTTPException(status_code=400, detail="Session not started — join first")
    if session.status == "completed":
        return NextQuestionResponse(completed=True, question=None, questions_remaining=0)

    next_iq, remaining = await _get_next_iq(session, db)
    if next_iq is None:
        return NextQuestionResponse(completed=True, question=None, questions_remaining=0)

    question = (
        await db.execute(select(Question).where(Question.id == next_iq.question_id))
    ).scalar_one()

    return NextQuestionResponse(
        completed=False,
        question=QuestionResponse.model_validate(question),
        questions_remaining=remaining,
    )


@router.post("/{token}/answers", response_model=AnswerResponse)
async def submit_answer(
    token: str,
    body: AnswerSubmit,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> AnswerResponse:
    if session.status == "pending":
        raise HTTPException(status_code=400, detail="Session not started — join first")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Interview already completed")

    next_iq, remaining = await _get_next_iq(session, db)
    if next_iq is None:
        raise HTTPException(status_code=400, detail="No more questions to answer")

    is_last = remaining == 1
    question = (
        await db.execute(select(Question).where(Question.id == next_iq.question_id))
    ).scalar_one()

    placeholder = EvaluationResponse(
        score=0.0,
        accuracy=0.0,
        completeness=0.0,
        clarity=0.0,
        feedback="Evaluation pending — LLM integration in Phase 2",
    )
    response = Response(
        session_id=session.id,
        question_id=question.id,
        answer_text=body.answer_text,
        score=placeholder.score,
        accuracy=placeholder.accuracy,
        completeness=placeholder.completeness,
        clarity=placeholder.clarity,
        feedback=placeholder.feedback,
    )
    db.add(response)

    if is_last:
        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)

    await db.flush()

    return AnswerResponse(
        response_id=response.id,
        question_text=question.text,
        evaluation=placeholder,
        is_last_question=is_last,
    )


@router.get("/{token}/progress", response_model=SessionProgressResponse)
async def get_progress(
    token: str,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> SessionProgressResponse:
    total = (
        await db.execute(
            select(func.count()).where(
                InterviewQuestion.interview_id == session.interview_id
            )
        )
    ).scalar_one()

    scores = list(
        (
            await db.execute(
                select(Response.score).where(Response.session_id == session.id)
            )
        ).scalars().all()
    )
    non_null = [s for s in scores if s is not None]
    current_score = sum(non_null) / len(non_null) if non_null else None

    return SessionProgressResponse(
        total_questions=total,
        answered_questions=len(scores),
        current_score=current_score,
    )


@router.get("/{session_id}/results", response_model=SessionResultResponse)
async def get_results(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResultResponse:
    session = (
        await db.execute(
            select(CandidateSession).where(CandidateSession.id == session_id)
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    interview = (
        await db.execute(
            select(Interview).where(
                Interview.id == session.interview_id,
                Interview.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Session not found")

    responses = list(
        (
            await db.execute(
                select(Response)
                .where(Response.session_id == session.id)
                .options(selectinload(Response.question))
            )
        ).scalars().all()
    )

    total = (
        await db.execute(
            select(func.count()).where(
                InterviewQuestion.interview_id == session.interview_id
            )
        )
    ).scalar_one()

    details = [
        ResponseDetail.model_validate({
            "id": r.id,
            "question_text": r.question.text,
            "answer_text": r.answer_text,
            "score": r.score,
            "accuracy": r.accuracy,
            "completeness": r.completeness,
            "clarity": r.clarity,
            "feedback": r.feedback,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at,
        })
        for r in responses
    ]

    non_null_scores = [r.score for r in responses if r.score is not None]
    overall = sum(non_null_scores) / len(non_null_scores) if non_null_scores else 0.0

    return SessionResultResponse(
        session_id=session.id,
        candidate_name=session.candidate_name,
        candidate_email=session.candidate_email,
        overall_score=overall,
        total_questions=total,
        answered_questions=len(responses),
        responses=details,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )
