from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_session, get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.database_models import CandidateSession, User
from app.models.schemas import (
    LoginRequest,
    SessionJoin,
    SessionResponse,
    SignupRequest,
    TokenResponse,
    UserResponse,
)

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])
sessions_router = APIRouter(prefix="/api/sessions", tags=["Sessions"])
limiter = Limiter(key_func=get_remote_address)


@auth_router.post("/signup", response_model=TokenResponse)
@limiter.limit("3/minute")
async def signup(
    request: Request,
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == str(body.email)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=str(body.email),
        name=body.name,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    return TokenResponse(access_token=create_access_token(str(user.id), user.role))


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == str(body.email)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(str(user.id), user.role))


@auth_router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@sessions_router.post("/{token}/join", response_model=SessionResponse)
@limiter.limit("5/minute")
async def join_session(
    request: Request,
    token: str,
    body: SessionJoin,
    session: CandidateSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> CandidateSession:
    if session.status != "pending":
        raise HTTPException(status_code=400, detail=f"Session is already {session.status}")
    session.candidate_name = body.candidate_name
    session.candidate_email = str(body.candidate_email)
    session.status = "active"
    session.started_at = datetime.now(timezone.utc)
    return session
