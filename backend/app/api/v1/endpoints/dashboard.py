from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Task, Project, User

router = APIRouter()


@router.get("/personal")
async def get_personal_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get personal dashboard data for the current user"""
    user_id = current_user.id
    user_name = current_user.full_name or current_user.username

    # My tasks
    result = await db.execute(select(Task).where(Task.assignee_id == user_id))
    my_tasks = result.scalars().all()

    total_tasks = len(my_tasks)
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)

    tasks_by_status: dict[str, int] = {}
    overdue_tasks = []
    upcoming_tasks = []

    for t in my_tasks:
        tasks_by_status[t.status] = tasks_by_status.get(t.status, 0) + 1

        task_dict = {
            "id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "progress": t.progress,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "project_id": t.project_id,
        }

        if t.due_date and t.due_date < now and t.status not in ("done", "completed"):
            overdue_tasks.append(task_dict)
        elif t.due_date and now <= t.due_date <= week_end:
            upcoming_tasks.append(task_dict)

    # Projects owned by user
    result = await db.execute(select(Project).where(Project.owner_id == user_id))
    owned_projects = result.scalars().all()
    my_projects = [
        {"id": p.id, "name": p.name, "status": p.status, "progress": p.progress or 0, "priority": p.priority}
        for p in owned_projects
    ]

    # Projects user is involved in (has tasks assigned)
    involved_ids = {t.project_id for t in my_tasks if t.project_id}
    owned_ids = {p.id for p in owned_projects}
    other_ids = involved_ids - owned_ids
    involved_projects = []
    if other_ids:
        result = await db.execute(select(Project).where(Project.id.in_(other_ids)))
        for p in result.scalars().all():
            involved_projects.append(
                {"id": p.id, "name": p.name, "status": p.status, "progress": p.progress or 0}
            )

    return {
        "user_name": user_name,
        "total_tasks": total_tasks,
        "tasks_by_status": tasks_by_status,
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks": upcoming_tasks,
        "my_projects": my_projects,
        "involved_projects": involved_projects,
    }
