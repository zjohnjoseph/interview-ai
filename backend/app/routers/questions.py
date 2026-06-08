import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.database_models import Question, User
from app.models.schemas import QuestionCreate, QuestionDetailResponse, SearchResultResponse
from app.services.rag_service import rag_service

router = APIRouter(prefix="/api/questions", tags=["Questions"])


@router.post("/", response_model=QuestionDetailResponse, status_code=201)
async def create_question(
    body: QuestionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    question = Question(
        text=body.text,
        domain=body.domain,
        difficulty=body.difficulty,
        reference_answer=body.reference_answer,
    )
    db.add(question)
    await db.flush()
    return question


@router.get("/", response_model=list[QuestionDetailResponse])
async def list_questions(
    domain: str | None = None,
    difficulty: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Question]:
    query = select(Question)
    if domain is not None:
        query = query.where(Question.domain == domain)
    if difficulty is not None:
        query = query.where(Question.difficulty == difficulty)
    if search is not None:
        query = query.where(Question.text.ilike(f"%{search}%"))
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/search", response_model=list[SearchResultResponse])
async def search_questions(
    q: str = Query(..., min_length=1, description="Semantic search query"),
    domain: str | None = None,
    difficulty: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await rag_service.search_similar_questions(
        query=q,
        db=db,
        domain=domain,
        difficulty=difficulty,
        limit=limit,
    )


@router.get("/{question_id}", response_model=QuestionDetailResponse)
async def get_question(
    question_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    result = await db.execute(select(Question).where(Question.id == question_id))
    question = result.scalar_one_or_none()
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question
