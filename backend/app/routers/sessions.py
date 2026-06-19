import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_session, get_current_user
from app.database import get_db
from app.models.database_models import (
    CandidateSession,
    Interview,
    User,
)
from app.models.schemas import (
    AnswerResponse,
    AnswerSubmit,
    NextQuestionResponse,
    SessionProgressResponse,
    SessionResultResponse,
)
from app.services.interview_service import NoQuestionPendingError, interview_service
from app.services.llm_service import LLMProviderError

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


async def _load_interview(session: CandidateSession, db: AsyncSession) -> Interview:
    return (
        await db.execute(select(Interview).where(Interview.id == session.interview_id))
    ).scalar_one()


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

    interview = await _load_interview(session, db)
    try:
        return await interview_service.get_next_question(session, interview, db)
    except LLMProviderError:
        raise HTTPException(
            status_code=503,
            detail="Unable to generate question. Please try again in a moment.",
        ) from None


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

    interview = await _load_interview(session, db)
    try:
        return await interview_service.evaluate_and_record(
            session, interview, body.answer_text, db
        )
    except NoQuestionPendingError:
        raise HTTPException(
            status_code=400, detail="No question pending. Call /next first."
        ) from None


@router.get("/{token}/progress", response_model=SessionProgressResponse)
async def get_progress(
    token: str,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> SessionProgressResponse:
    interview = await _load_interview(session, db)
    return await interview_service.get_progress(session, interview, db)


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

    return await interview_service.get_results(session, interview, db)
