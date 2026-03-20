from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import Risk
from app.schemas.schemas import RiskCreate, RiskUpdate, RiskResponse

router = APIRouter()

@router.post("/", response_model=RiskResponse, status_code=status.HTTP_201_CREATED)
async def create_risk(
    risk: RiskCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new risk"""
    risk_score = risk.probability * risk.impact
    db_risk = Risk(**risk.dict(), risk_score=risk_score)
    
    db.add(db_risk)
    await db.commit()
    await db.refresh(db_risk)
    
    return db_risk

@router.get("/", response_model=List[RiskResponse])
async def get_all_risks(
    project_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all risks, optionally filtered by project"""
    query = select(Risk)
    if project_id:
        query = query.where(Risk.project_id == project_id)
    
    result = await db.execute(query)
    risks = result.scalars().all()
    
    return risks

@router.get("/project/{project_id}", response_model=List[RiskResponse])
async def get_project_risks(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all risks for a project"""
    result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = result.scalars().all()
    
    return risks
