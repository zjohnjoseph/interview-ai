from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# 1. Engine — one per app, manages the connection pool
engine = create_async_engine(
    settings.database_url,
    echo=False,       # set True temporarily to see SQL queries in logs
    pool_size=5,      # max concurrent connections
    max_overflow=10,  # extra connections under load
)

# 2. Session factory — creates individual database sessions
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# 3. FastAPI dependency — every endpoint gets a session via Depends(get_db)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise