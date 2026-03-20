from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, Risk, Milestone, User

router = APIRouter()


@router.get("/summary")
async def get_portfolio_summary(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio summary with project health metrics"""
    result = await db.execute(select(Project))
    projects = result.scalars().all()

    portfolio = []
    for p in projects:
        # Task stats
        task_result = await db.execute(select(Task).where(Task.project_id == p.id))
        tasks = task_result.scalars().all()
        task_total = len(tasks)
        task_done = sum(1 for t in tasks if t.status in ("done", "completed"))
        task_blocked = sum(1 for t in tasks if t.status == "blocked")
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        task_overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))

        # Risk count
        risk_result = await db.execute(select(func.count(Risk.id)).where(Risk.project_id == p.id))
        risk_count = risk_result.scalar() or 0

        # Milestone stats
        ms_result = await db.execute(select(Milestone).where(Milestone.project_id == p.id))
        milestones = ms_result.scalars().all()
        milestone_total = len(milestones)
        milestone_done = sum(1 for m in milestones if m.status == "achieved")

        # Owner name
        owner_name = ""
        if p.owner_id:
            owner_result = await db.execute(select(User).where(User.id == p.owner_id))
            owner = owner_result.scalar_one_or_none()
            owner_name = owner.full_name or owner.username if owner else ""

        # Health score heuristic
        health = 100
        if task_total > 0:
            done_ratio = task_done / task_total
            health = int(done_ratio * 40 + (p.progress or 0) * 0.4 + (20 - min(task_overdue * 5, 20)))
        health = max(0, min(100, health))

        budget = p.budget or 0
        actual_cost = p.actual_cost or 0
        budget_util = round((actual_cost / budget * 100), 1) if budget > 0 else 0

        portfolio.append({
            "id": p.id, "name": p.name, "status": p.status or "planning",
            "priority": p.priority or "medium", "progress": p.progress or 0,
            "health_score": health, "budget": budget, "actual_cost": actual_cost,
            "budget_utilization": budget_util,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "owner": owner_name,
            "task_total": task_total, "task_done": task_done,
            "task_blocked": task_blocked, "task_overdue": task_overdue,
            "risk_count": risk_count,
            "milestone_total": milestone_total, "milestone_done": milestone_done,
        })

    return {"projects": portfolio}
