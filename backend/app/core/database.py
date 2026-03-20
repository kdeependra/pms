from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import settings

# Determine async database URL
if "sqlite" in settings.DATABASE_URL:
    # SQLite with aiosqlite driver
    if "+aiosqlite" not in settings.DATABASE_URL:
        async_db_url = settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
    else:
        async_db_url = settings.DATABASE_URL
    engine = create_async_engine(
        async_db_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False}
    )
elif "postgresql" in settings.DATABASE_URL:
    # PostgreSQL with asyncpg driver  
    if "+asyncpg" not in settings.DATABASE_URL:
        async_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    else:
        async_db_url = settings.DATABASE_URL
    engine = create_async_engine(
        async_db_url,
        echo=False,
        future=True
    )
else:
    raise ValueError(f"Unsupported database URL: {settings.DATABASE_URL}")

# Session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()

# Dependency for database sessions
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
