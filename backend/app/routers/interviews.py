import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.database_models import (
    CandidateSession,
    Interview,
    InterviewQuestion,
    Question,
    User,
)
from app.models.schemas import (
    AttachQuestionsRequest,
    InterviewCreate,
    InterviewResponse,
    InterviewUpdate,
    SessionResponse,
)

router = APIRouter(prefix="/api/interviews", tags=["Interviews"])


async def _get_owned_interview(
    interview_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Interview:
    result = await db.execute(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.user_id == current_user.id,
        )
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.post("/", response_model=InterviewResponse, status_code=201)
async def create_interview(
    body: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    interview = Interview(
        user_id=current_user.id,
        title=body.title,
        topics=body.topics,
        difficulty=body.difficulty,
    )
    db.add(interview)
    await db.flush()
    return interview


@router.get("/", response_model=list[InterviewResponse])
async def list_interviews(
    status: str | None = None,
    difficulty: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Interview]:
    query = select(Interview).where(Interview.user_id == current_user.id)
    if status is not None:
        query = query.where(Interview.status == status)
    if difficulty is not None:
        query = query.where(Interview.difficulty == difficulty)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    return await _get_owned_interview(interview_id, current_user, db)


@router.patch("/{interview_id}", response_model=InterviewResponse)
async def update_interview(
    interview_id: uuid.UUID,
    body: InterviewUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "draft":
        raise HTTPException(status_code=400, detail="Cannot update a non-draft interview")
    if body.title is not None:
        interview.title = body.title
    if body.topics is not None:
        interview.topics = body.topics
    if body.difficulty is not None:
        interview.difficulty = body.difficulty
    return interview


@router.delete("/{interview_id}", status_code=204)
async def archive_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    interview = await _get_owned_interview(interview_id, current_user, db)
    interview.status = "archived"


@router.post("/{interview_id}/publish", response_model=SessionResponse)
async def publish_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateSession:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft interviews can be published")

    iq = (
        await db.execute(
            select(InterviewQuestion)
            .where(InterviewQuestion.interview_id == interview_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if iq is None:
        raise HTTPException(
            status_code=400,
            detail="Interview must have at least one question before publishing",
        )

    interview.status = "active"
    session = CandidateSession(
        interview_id=interview_id,
        token=secrets.token_urlsafe(48),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(session)
    await db.flush()
    return session


@router.post("/{interview_id}/questions", response_model=InterviewResponse)
async def attach_questions(
    interview_id: uuid.UUID,
    body: AttachQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "draft":
        raise HTTPException(
            status_code=400, detail="Cannot modify questions on a non-draft interview"
        )

    question_ids = [item.question_id for item in body.questions]
    found = set(
        (
            await db.execute(select(Question.id).where(Question.id.in_(question_ids)))
        ).scalars().all()
    )
    missing = [str(qid) for qid in question_ids if qid not in found]
    if missing:
        raise HTTPException(status_code=400, detail=f"Question IDs not found: {missing}")

    await db.execute(
        delete(InterviewQuestion).where(InterviewQuestion.interview_id == interview_id)
    )
    for item in body.questions:
        db.add(
            InterviewQuestion(
                interview_id=interview_id,
                question_id=item.question_id,
                order=item.order,
            )
        )
    await db.flush()
    return interview


@router.delete("/{interview_id}/questions/{question_id}", status_code=204)
async def remove_question(
    interview_id: uuid.UUID,
    question_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "draft":
        raise HTTPException(
            status_code=400, detail="Cannot modify questions on a non-draft interview"
        )

    result = await db.execute(
        select(InterviewQuestion).where(
            InterviewQuestion.interview_id == interview_id,
            InterviewQuestion.question_id == question_id,
        )
    )
    iq = result.scalar_one_or_none()
    if iq is None:
        raise HTTPException(status_code=404, detail="Question not attached to this interview")
    await db.delete(iq)


@router.get("/{interview_id}/sessions", response_model=list[SessionResponse])
async def list_sessions(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CandidateSession]:
    await _get_owned_interview(interview_id, current_user, db)
    result = await db.execute(
        select(CandidateSession).where(CandidateSession.interview_id == interview_id)
    )
    return list(result.scalars().all())
