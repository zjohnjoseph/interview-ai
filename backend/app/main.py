from typing import Any

from fastapi import Depends, FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.auth import auth_router, limiter, sessions_router
from app.routers.interviews import router as interviews_router
from app.routers.questions import router as questions_router
from app.routers.sessions import router as candidate_router
from app.services.llm_service import llm_service
from app.services.redis_service import redis_service

app = FastAPI(title="Interview AI Core")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(interviews_router)
app.include_router(questions_router)
app.include_router(candidate_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "healthy", "service": "interview-ai"}


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Report the state of every dependency.

    Only the database is critical: if it is down the app is "unhealthy".
    Redis and the LLM circuit breakers are non-critical — the interview still
    runs without them — so they only downgrade the status to "degraded".
    """
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = await redis_service.is_healthy()
    circuits = llm_service.circuit_states()

    if not db_ok:
        status = "unhealthy"
    elif not redis_ok or any(s != "closed" for s in circuits.values()):
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "database": "connected" if db_ok else "down",
        "redis": "connected" if redis_ok else "down",
        "groq_circuit": circuits["groq"],
        "gemini_circuit": circuits["gemini"],
    }
