from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import Milestone, Project, Task, User
from app.schemas.schemas import (
    MilestoneCreate,
    MilestoneUpdate,
    MilestoneResponse,
    MilestoneAnalytics
)

router = APIRouter()

@router.post("/", response_model=MilestoneResponse, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    milestone: MilestoneCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new milestone for a project"""
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == milestone.project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create milestone
    db_milestone = Milestone(**milestone.model_dump())
    db.add(db_milestone)
    await db.commit()
    await db.refresh(db_milestone)
    
    return db_milestone

@router.get("/", response_model=List[MilestoneResponse])
async def get_milestones(
    project_id: int = None,
    status: str = None,
    is_critical: bool = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get milestones with optional filters"""
    query = select(Milestone)
    
    filters = []
    if project_id:
        filters.append(Milestone.project_id == project_id)
    if status:
        filters.append(Milestone.status == status)
    if is_critical is not None:
        filters.append(Milestone.is_critical == is_critical)
    
    if filters:
        query = query.where(and_(*filters))
    
    query = query.order_by(Milestone.target_date)
    
    result = await db.execute(query)
    milestones = result.scalars().all()
    
    return milestones

@router.get("/{milestone_id}", response_model=MilestoneResponse)
async def get_milestone(
    milestone_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific milestone by ID"""
    result = await db.execute(select(Milestone).where(Milestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    return milestone

@router.put("/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    milestone_id: int,
    milestone_update: MilestoneUpdate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a milestone"""
    result = await db.execute(select(Milestone).where(Milestone.id == milestone_id))
    db_milestone = result.scalar_one_or_none()
    
    if not db_milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    # Update fields
    update_data = milestone_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_milestone, field, value)
    
    # Auto-update status based on progress and dates
    if db_milestone.progress == 100 and not db_milestone.actual_date:
        db_milestone.actual_date = datetime.now()
        db_milestone.status = "achieved"
    elif db_milestone.target_date < datetime.now() and db_milestone.status == "pending":
        db_milestone.status = "missed"
    
    db_milestone.updated_at = datetime.now()
    
    await db.commit()
    await db.refresh(db_milestone)
    
    return db_milestone

@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    milestone_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a milestone"""
    result = await db.execute(select(Milestone).where(Milestone.id == milestone_id))
    milestone = result.scalar_one_or_none()
    
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    
    await db.delete(milestone)
    await db.commit()
    
    return None

@router.get("/project/{project_id}/analytics", response_model=MilestoneAnalytics)
async def get_milestone_analytics(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get milestone analytics for a project"""
    # Get all milestones for the project
    result = await db.execute(
        select(Milestone).where(Milestone.project_id == project_id)
    )
    milestones = result.scalars().all()
    
    if not milestones:
        return MilestoneAnalytics(
            total_milestones=0,
            achieved_milestones=0,
            pending_milestones=0,
            missed_milestones=0,
            at_risk_milestones=0,
            critical_path_milestones=[],
            upcoming_milestones=[],
            achievement_rate=0.0
        )
    
    # Calculate statistics
    total = len(milestones)
    achieved = len([m for m in milestones if m.status == "achieved"])
    pending = len([m for m in milestones if m.status == "pending"])
    missed = len([m for m in milestones if m.status == "missed"])
    
    # Calculate at-risk milestones (pending and within 7 days)
    now = datetime.now()
    at_risk = []
    for m in milestones:
        if m.status == "pending" and m.target_date:
            days_until = (m.target_date - now).days
            if 0 <= days_until <= 7:
                m.status = "at_risk"
                at_risk.append(m)
    
    # Get critical path milestones
    critical_milestones = [m for m in milestones if m.is_critical]
    
    # Get upcoming milestones (next 30 days)
    upcoming = [
        m for m in milestones 
        if m.status == "pending" and m.target_date 
        and 0 <= (m.target_date - now).days <= 30
    ]
    upcoming.sort(key=lambda x: x.target_date)
    
    # Calculate achievement rate
    achievement_rate = (achieved / total * 100) if total > 0 else 0
    
    return MilestoneAnalytics(
        total_milestones=total,
        achieved_milestones=achieved,
        pending_milestones=pending,
        missed_milestones=missed,
        at_risk_milestones=len(at_risk),
        critical_path_milestones=critical_milestones,
        upcoming_milestones=upcoming[:5],  # Top 5 upcoming
        achievement_rate=round(achievement_rate, 2)
    )

@router.post("/project/{project_id}/critical-path")
async def analyze_critical_path(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analyze and update critical path for project milestones"""
    # Get all milestones and tasks for the project
    milestone_result = await db.execute(
        select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.target_date)
    )
    milestones = milestone_result.scalars().all()
    
    task_result = await db.execute(
        select(Task).where(Task.project_id == project_id)
    )
    tasks = task_result.scalars().all()
    
    if not milestones:
        return {"message": "No milestones found for analysis"}
    
    # Simple critical path logic: mark milestones with tasks that have tight deadlines
    critical_milestone_ids = set()
    
    for milestone in milestones:
        # Find tasks close to this milestone date
        related_tasks = [
            t for t in tasks 
            if t.due_date and milestone.target_date 
            and abs((t.due_date - milestone.target_date).days) <= 7
        ]
        
        # If milestone has high-priority incomplete tasks, mark as critical
        has_critical_tasks = any(
            t.priority in ['high', 'critical'] and t.status != 'completed'
            for t in related_tasks
        )
        
        if has_critical_tasks or milestone.target_date <= datetime.now() + timedelta(days=14):
            milestone.is_critical = True
            critical_milestone_ids.add(milestone.id)
        else:
            milestone.is_critical = False
    
    await db.commit()
    
    return {
        "message": "Critical path analysis completed",
        "critical_milestones": len(critical_milestone_ids),
        "total_milestones": len(milestones),
        "critical_milestone_ids": list(critical_milestone_ids)
    }

@router.get("/notifications/upcoming")
async def get_upcoming_milestone_notifications(
    days_ahead: int = 7,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notifications for upcoming milestones"""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    future_date = now + timedelta(days=days_ahead)
    
    result = await db.execute(
        select(Milestone, Project).join(Project).where(
            and_(
                Milestone.status == "pending",
                Milestone.target_date >= now,
                Milestone.target_date <= future_date
            )
        ).order_by(Milestone.target_date)
    )
    
    notifications = []
    for milestone, project in result:
        days_until = (milestone.target_date - now).days
        notifications.append({
            "milestone_id": milestone.id,
            "milestone_name": milestone.name,
            "project_id": project.id,
            "project_name": project.name,
            "target_date": milestone.target_date,
            "days_until": days_until,
            "is_critical": milestone.is_critical,
            "progress": milestone.progress,
            "urgency": "high" if days_until <= 3 else "medium" if days_until <= 7 else "low"
        })
    
    return notifications

@router.get("/notifications/missed")
async def get_missed_milestone_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notifications for missed milestones"""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    
    result = await db.execute(
        select(Milestone, Project).join(Project).where(
            and_(
                Milestone.status.in_(["pending", "at_risk"]),
                Milestone.target_date < now
            )
        ).order_by(Milestone.target_date.desc())
    )
    
    notifications = []
    for milestone, project in result:
        days_overdue = (now - milestone.target_date).days
        notifications.append({
            "milestone_id": milestone.id,
            "milestone_name": milestone.name,
            "project_id": project.id,
            "project_name": project.name,
            "target_date": milestone.target_date,
            "days_overdue": days_overdue,
            "is_critical": milestone.is_critical,
            "progress": milestone.progress
        })
    
    return notifications
