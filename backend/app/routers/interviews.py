import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.database_models import (
    CandidateSession,
    Interview,
    User,
)
from app.models.schemas import (
    InterviewCreate,
    InterviewResponse,
    InterviewUpdate,
    SessionResponse,
)
from app.services.pdf_parser import extract_text_from_pdf

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
        job_title=body.job_title,
        job_description=body.job_description,
        required_skills=body.required_skills,
        role_level=body.role_level,
        max_questions=body.max_questions,
    )
    db.add(interview)
    await db.flush()
    return interview


@router.get("/", response_model=list[InterviewResponse])
async def list_interviews(
    status: str | None = None,
    role_level: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Interview]:
    query = select(Interview).where(Interview.user_id == current_user.id)
    if status is not None:
        query = query.where(Interview.status == status)
    if role_level is not None:
        query = query.where(Interview.role_level == role_level)
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
    if body.job_title is not None:
        interview.job_title = body.job_title
    if body.job_description is not None:
        interview.job_description = body.job_description
    if body.required_skills is not None:
        interview.required_skills = body.required_skills
    if body.role_level is not None:
        interview.role_level = body.role_level
    if body.max_questions is not None:
        interview.max_questions = body.max_questions
    return interview


@router.delete("/{interview_id}", status_code=204)
async def archive_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    interview = await _get_owned_interview(interview_id, current_user, db)
    interview.status = "archived"


@router.post("/{interview_id}/publish", response_model=InterviewResponse)
async def publish_interview(
    interview_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Interview:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft interviews can be published")
    interview.status = "active"
    await db.flush()
    return interview


@router.post("/{interview_id}/candidates", response_model=SessionResponse, status_code=201)
async def add_candidate(
    interview_id: uuid.UUID,
    candidate_name: str = Form(min_length=2),
    candidate_email: str = Form(),
    resume: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CandidateSession:
    interview = await _get_owned_interview(interview_id, current_user, db)
    if interview.status != "active":
        raise HTTPException(
            status_code=400, detail="Interview must be published before adding candidates"
        )
    if resume.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Resume must be a PDF file")

    pdf_bytes = await resume.read()
    if len(pdf_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Resume must be smaller than 5MB")

    resume_text = extract_text_from_pdf(pdf_bytes)
    session = CandidateSession(
        interview_id=interview_id,
        token=secrets.token_urlsafe(48),
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        resume_text=resume_text,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(session)
    await db.flush()
    return session


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
