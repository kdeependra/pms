"""Reports & Analytics endpoint – aggregated summary data for the Reports page."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, Risk, User, Milestone

router = APIRouter()


@router.get("")
async def get_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # Projects
    result = await db.execute(select(Project))
    projects = result.scalars().all()
    active_projects = sum(1 for p in projects if p.status in ("active", "in_progress"))
    completed_projects = sum(1 for p in projects if p.status in ("completed", "done"))

    # Tasks
    result = await db.execute(select(Task))
    tasks = result.scalars().all()
    active_tasks = sum(1 for t in tasks if t.status in ("in_progress", "review"))
    completed_tasks = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue_tasks = sum(
        1 for t in tasks
        if t.due_date and t.due_date < now and t.status not in ("done", "completed")
    )

    # Risks
    result = await db.execute(select(Risk))
    risks = result.scalars().all()
    active_risks = sum(1 for r in risks if r.status not in ("closed", "mitigated"))
    high_risks = sum(1 for r in risks if (r.risk_score or 0) >= 12 and r.status not in ("closed", "mitigated"))

    # Milestones
    result = await db.execute(select(Milestone))
    milestones = result.scalars().all()
    achieved_milestones = sum(1 for m in milestones if m.status == "achieved")
    missed_milestones = sum(1 for m in milestones if m.status == "missed")

    # Users / Resources
    result = await db.execute(select(User).where(User.is_active == True))
    users = result.scalars().all()
    # "available" = users with fewer than 5 active tasks
    user_task_count: dict[int, int] = {}
    for t in tasks:
        if t.assignee_id and t.status not in ("done", "completed"):
            user_task_count[t.assignee_id] = user_task_count.get(t.assignee_id, 0) + 1
    available_resources = sum(1 for u in users if user_task_count.get(u.id, 0) < 5)

    return [
        {
            "name": "Projects",
            "type": "projects",
            "total": len(projects),
            "active": active_projects,
            "completed": completed_projects,
        },
        {
            "name": "Tasks",
            "type": "tasks",
            "total": len(tasks),
            "active": active_tasks,
            "completed": completed_tasks,
            "overdue": overdue_tasks,
        },
        {
            "name": "Risks",
            "type": "risks",
            "total": len(risks),
            "active": active_risks,
            "high": high_risks,
        },
        {
            "name": "Milestones",
            "type": "milestones",
            "total": len(milestones),
            "achieved": achieved_milestones,
            "missed": missed_milestones,
        },
        {
            "name": "Resources",
            "type": "resources",
            "total": len(users),
            "available": available_resources,
        },
    ]
