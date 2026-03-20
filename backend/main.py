"""
AI-Powered Project Management System - Backend Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.router import api_router
from app.middleware.logging import LoggingMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup: create tables
    logger.info("Starting AI-PMS Backend...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    # Seed admin user if not exists
    from app.core.database import AsyncSessionLocal
    from app.models.models import User, UserRole, Resource, Timesheet, Project
    from app.core.security import get_password_hash
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()
        if not admin:
            admin_user = User(
                email="admin@pms.local",
                username="admin",
                full_name="System Administrator",
                hashed_password=get_password_hash("admin123"),
                role=UserRole.ADMIN,
                is_active=True,
                department="IT",
            )
            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)
            admin = admin_user
            logger.info("Default admin user created (admin / admin123)")
        else:
            logger.info("Admin user already exists.")

        # Ensure admin has a resource record
        res_result = await session.execute(
            select(Resource).where(Resource.user_id == admin.id)
        )
        if not res_result.scalar_one_or_none():
            session.add(Resource(
                user_id=admin.id, role="Admin", department="IT",
                cost_per_hour=150.0, availability_percentage=100.0,
                is_available=True, vacation_days_remaining=20.0,
            ))
            await session.commit()
            logger.info("Admin resource profile created.")

        # Seed demo timesheets if none exist
        ts_count = (await session.execute(select(func.count()).select_from(Timesheet))).scalar() or 0
        if ts_count == 0:
            await _seed_demo_timesheets(session)
            logger.info("Demo timesheet data seeded.")

    yield

    # Shutdown
    logger.info("Shutting down AI-PMS Backend...")
    await engine.dispose()


async def _seed_demo_timesheets(session):
    """Seed realistic demo timesheet entries for the last 30 days."""
    from datetime import datetime, timedelta, timezone
    from app.models.models import Resource, Timesheet, Project
    from sqlalchemy import select
    import random

    resources = (await session.execute(select(Resource))).scalars().all()
    projects = (await session.execute(select(Project))).scalars().all()
    if not resources or not projects:
        return

    now = datetime.now(timezone.utc)
    project_ids = [p.id for p in projects]

    # Assign 1-2 projects to each resource for realistic data
    resource_projects = {}
    for r in resources:
        rng = random.Random(r.id)  # deterministic per resource
        count = rng.choice([1, 2, 2])
        resource_projects[r.id] = rng.sample(project_ids, min(count, len(project_ids)))

    entries = []
    for r in resources:
        pids = resource_projects[r.id]
        rng = random.Random(r.id * 100)
        for day_offset in range(30, 0, -1):
            day = now - timedelta(days=day_offset)
            if day.weekday() >= 5:  # skip weekends
                continue
            for pid in pids:
                hours = rng.choice([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
                if rng.random() < 0.15:  # 15% chance to skip a day
                    continue
                status = "approved" if day_offset > 7 else ("submitted" if day_offset > 3 else "draft")
                entries.append(Timesheet(
                    resource_id=r.id,
                    project_id=pid,
                    date=day.replace(hour=9, minute=0, second=0),
                    hours=hours,
                    is_billable=rng.random() > 0.2,
                    description=rng.choice([
                        "Development work", "Code review", "Bug fixes",
                        "Feature implementation", "Testing", "Documentation",
                        "Design work", "Sprint planning", "Deployment tasks",
                        "Technical debt", "Meetings", "Research",
                    ]),
                    status=status,
                ))
    session.add_all(entries)
    await session.commit()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Project Management System API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging middleware
app.add_middleware(LoggingMiddleware)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.APP_NAME}


@app.get("/")
async def root():
    return {
        "message": "AI-Powered Project Management System API",
        "docs": "/docs",
        "health": "/health",
    }
