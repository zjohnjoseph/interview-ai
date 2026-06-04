import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_session, get_current_user
from app.database import get_db
from app.models.database_models import (
    CandidateSession,
    Interview,
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

_STUB_QUESTION_TEXT = "Placeholder — LLM question generation coming in Phase 2"
_STUB_QUESTION_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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

    interview = (
        await db.execute(select(Interview).where(Interview.id == session.interview_id))
    ).scalar_one()
    answered = (
        await db.execute(select(func.count()).where(Response.session_id == session.id))
    ).scalar_one()
    remaining = interview.max_questions - answered

    if remaining <= 0:
        return NextQuestionResponse(completed=True, question=None, questions_remaining=0)

    return NextQuestionResponse(
        completed=False,
        question=QuestionResponse(
            id=_STUB_QUESTION_UUID,
            text=_STUB_QUESTION_TEXT,
            domain="python",
            difficulty="medium",
            created_at=datetime.now(timezone.utc),
        ),
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

    interview = (
        await db.execute(select(Interview).where(Interview.id == session.interview_id))
    ).scalar_one()
    answered = (
        await db.execute(select(func.count()).where(Response.session_id == session.id))
    ).scalar_one()

    if answered >= interview.max_questions:
        raise HTTPException(status_code=400, detail="No more questions to answer")

    is_last = (answered + 1) >= interview.max_questions

    placeholder = EvaluationResponse(
        score=0.0,
        accuracy=0.0,
        completeness=0.0,
        clarity=0.0,
        feedback="Evaluation pending — LLM integration in Phase 2",
    )
    response = Response(
        session_id=session.id,
        question_id=None,
        question_text=_STUB_QUESTION_TEXT,
        is_follow_up=False,
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
        question_text=_STUB_QUESTION_TEXT,
        evaluation=placeholder,
        is_last_question=is_last,
    )


@router.get("/{token}/progress", response_model=SessionProgressResponse)
async def get_progress(
    token: str,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> SessionProgressResponse:
    interview = (
        await db.execute(select(Interview).where(Interview.id == session.interview_id))
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
        total_questions=interview.max_questions,
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
            await db.execute(select(Response).where(Response.session_id == session.id))
        ).scalars().all()
    )

    details = [ResponseDetail.model_validate(r) for r in responses]

    non_null_scores = [r.score for r in responses if r.score is not None]
    overall = sum(non_null_scores) / len(non_null_scores) if non_null_scores else 0.0

    return SessionResultResponse(
        session_id=session.id,
        candidate_name=session.candidate_name,
        candidate_email=session.candidate_email,
        overall_score=overall,
        total_questions=interview.max_questions,
        answered_questions=len(responses),
        responses=details,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )
