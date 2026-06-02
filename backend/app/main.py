from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.routers.auth import auth_router, limiter, sessions_router
from app.routers.interviews import router as interviews_router
from app.routers.questions import router as questions_router

app = FastAPI(title="Interview AI Core")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(interviews_router)
app.include_router(questions_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "healthy", "service": "interview-ai"}
