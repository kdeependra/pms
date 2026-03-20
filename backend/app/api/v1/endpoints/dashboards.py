"""Role-Based Dashboard endpoints – Executive, PMO, Project Manager, Team Member, Stakeholder."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
import math, random

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, Risk, User, Milestone

router = APIRouter()

# ── helpers ──────────────────────────────────────────────────────────────────

def _health(progress: int, budget: int, actual_cost: int, end_date, now) -> str:
    if actual_cost > (budget or 1) * 1.15:
        return "red"
    if end_date and end_date < now and progress < 100:
        return "red"
    if actual_cost > (budget or 1) * 0.9 or (end_date and end_date < now + timedelta(days=14) and progress < 80):
        return "yellow"
    return "green"


def _spi(progress: int, start_date, end_date, now) -> float:
    if not start_date or not end_date:
        return 1.0
    total = (end_date - start_date).total_seconds() or 1
    elapsed = (now - start_date).total_seconds()
    planned_pct = min(max(elapsed / total * 100, 0), 100)
    return round(progress / planned_pct, 2) if planned_pct > 0 else 1.0


def _cpi(budget: int, actual_cost: int, progress: int) -> float:
    if not actual_cost or not budget:
        return 1.0
    ev = (budget * progress / 100)
    return round(ev / actual_cost, 2) if actual_cost else 1.0


def _roi(budget: int, actual_cost: int, progress: int) -> float:
    if not budget or not actual_cost:
        return 0.0
    gained = budget * progress / 100
    return round((gained - actual_cost) / max(actual_cost, 1) * 100, 1)


# ── 1. Executive Dashboard ──────────────────────────────────────────────────

@router.get("/executive")
async def dashboard_executive(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()

    result = await db.execute(select(Milestone))
    milestones = result.scalars().all()

    proj_list = []
    health_counts = {"green": 0, "yellow": 0, "red": 0}
    total_progress = 0
    total_budget = 0
    total_actual = 0

    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        progress = p.progress or 0
        h = _health(progress, budget, actual, p.end_date, now)
        health_counts[h] += 1
        total_progress += progress
        total_budget += budget
        total_actual += actual
        roi = _roi(budget, actual, progress)
        cpi = _cpi(budget, actual, progress)
        proj_list.append({
            "id": p.id, "name": p.name, "health": h, "progress": progress,
            "spent": actual, "budget": budget, "roi": roi, "cpi": cpi,
        })

    n = len(projects) or 1
    portfolio_cpi = _cpi(total_budget, total_actual, round(total_progress / n))
    portfolio_roi = _roi(total_budget, total_actual, round(total_progress / n))

    ms_achieved = sum(1 for m in milestones if m.status == "achieved")
    ms_missed = sum(1 for m in milestones if m.status == "missed")
    ms_upcoming = sum(1 for m in milestones if m.target_date and now <= m.target_date <= now + timedelta(days=30) and m.status not in ("achieved", "missed"))

    return {
        "portfolio_kpis": {
            "total_projects": len(projects),
            "active_projects": sum(1 for p in projects if p.status == "active"),
            "completion_pct": round(total_progress / n, 1),
            "portfolio_roi": portfolio_roi,
            "portfolio_cpi": portfolio_cpi,
            "strategic_alignment": round(min(total_progress / n + 15, 100), 1),
        },
        "portfolio_health": health_counts,
        "projects": proj_list,
        "milestones": {
            "total": len(milestones),
            "achieved": ms_achieved,
            "missed": ms_missed,
            "upcoming_30d": ms_upcoming,
        },
    }


# ── 2. PMO Dashboard ────────────────────────────────────────────────────────

@router.get("/pmo")
async def dashboard_pmo(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()

    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()

    result = await db.execute(select(Risk))
    all_risks = result.scalars().all()

    result = await db.execute(select(User).where(User.is_active == True))
    all_users = result.scalars().all()

    # status pipeline
    pipeline: dict[str, int] = {}
    for p in projects:
        pipeline[p.status or "unknown"] = pipeline.get(p.status or "unknown", 0) + 1

    # project list
    task_by_proj: dict[int, list] = {}
    for t in all_tasks:
        task_by_proj.setdefault(t.project_id, []).append(t)

    risk_by_proj: dict[int, list] = {}
    for r in all_risks:
        risk_by_proj.setdefault(r.project_id, []).append(r)

    proj_list = []
    for p in projects:
        tasks = task_by_proj.get(p.id, [])
        risks = risk_by_proj.get(p.id, [])
        overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
        remaining = (p.end_date - now).days if p.end_date else 0
        proj_list.append({
            "id": p.id, "name": p.name, "status": p.status or "planning",
            "progress": p.progress or 0,
            "spi": _spi(p.progress or 0, p.start_date, p.end_date, now),
            "cpi": _cpi(p.budget or 0, p.actual_cost or 0, p.progress or 0),
            "overdue": overdue,
            "risks_active": sum(1 for r in risks if r.status not in ("closed", "mitigated")),
            "remaining_days": max(remaining, 0),
        })

    # resource summary
    user_task_map: dict[int, list] = {}
    for t in all_tasks:
        if t.assignee_id:
            user_task_map.setdefault(t.assignee_id, []).append(t)

    resources = []
    total_util = 0
    overallocated = 0
    available = 0
    for u in all_users:
        tasks = user_task_map.get(u.id, [])
        active_tasks = [t for t in tasks if t.status not in ("done", "completed")]
        alloc = min(len(active_tasks) * 25, 150)  # heuristic 25% per active task
        total_util += alloc
        if alloc > 100:
            overallocated += 1
        if alloc == 0:
            available += 1
        resources.append({"name": u.full_name or u.username, "allocation_pct": alloc})

    n_users = len(all_users) or 1

    # risk matrix (5×5)
    matrix = [[0]*5 for _ in range(5)]
    active_risks = [r for r in all_risks if r.status not in ("closed",)]
    for r in active_risks:
        prob = max(1, min(r.probability or 1, 5))
        imp = max(1, min(r.impact or 1, 5))
        matrix[prob - 1][imp - 1] += 1

    top_risks = sorted(active_risks, key=lambda r: (r.risk_score or 0), reverse=True)[:8]

    return {
        "status_pipeline": pipeline,
        "projects": proj_list,
        "resource_summary": {
            "resources": resources,
            "total_resources": len(all_users),
            "avg_utilization": round(total_util / n_users, 1),
            "overallocated": overallocated,
            "available": available,
        },
        "risk_summary": {
            "total_active": len(active_risks),
            "risk_matrix": matrix,
            "top_risks": [
                {"id": r.id, "title": r.title, "score": r.risk_score or 0, "status": r.status}
                for r in top_risks
            ],
        },
    }


# ── 3. Project Manager Dashboard ────────────────────────────────────────────

@router.get("/project-manager")
async def dashboard_project_manager(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    user_id = current_user.id
    user_name = current_user.full_name or current_user.username

    # projects owned by current user
    result = await db.execute(select(Project).where(Project.owner_id == user_id))
    owned = result.scalars().all()

    # if user owns no projects, show all (for demo/admin)
    if not owned:
        result = await db.execute(select(Project))
        owned = result.scalars().all()

    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()

    result = await db.execute(select(User).where(User.is_active == True))
    users_map = {u.id: (u.full_name or u.username) for u in result.scalars().all()}

    task_by_proj: dict[int, list] = {}
    for t in all_tasks:
        task_by_proj.setdefault(t.project_id, []).append(t)

    total_tasks = 0
    completed_tasks = 0
    overdue_total = 0
    proj_list = []

    for p in owned:
        tasks = task_by_proj.get(p.id, [])
        done = sum(1 for t in tasks if t.status in ("done", "completed"))
        in_prog = sum(1 for t in tasks if t.status == "in_progress")
        review = sum(1 for t in tasks if t.status == "review")
        overdue_tasks = [
            t for t in tasks
            if t.due_date and t.due_date < now and t.status not in ("done", "completed")
        ]
        total_tasks += len(tasks)
        completed_tasks += done
        overdue_total += len(overdue_tasks)

        budget_val = p.budget or 0
        spent = p.actual_cost or 0
        consumed = round(spent / budget_val * 100, 1) if budget_val else 0

        # team workload
        member_map: dict[int, dict] = {}
        for t in tasks:
            if t.assignee_id:
                m = member_map.setdefault(t.assignee_id, {"name": users_map.get(t.assignee_id, f"User {t.assignee_id}"), "done": 0, "in_progress": 0, "overdue": 0})
                if t.status in ("done", "completed"):
                    m["done"] += 1
                elif t.status == "in_progress":
                    m["in_progress"] += 1
                if t.due_date and t.due_date < now and t.status not in ("done", "completed"):
                    m["overdue"] += 1

        proj_list.append({
            "id": p.id, "name": p.name, "status": p.status or "planning",
            "progress": p.progress or 0,
            "tasks": {"total": len(tasks), "done": done, "in_progress": in_prog, "review": review},
            "budget": {
                "planned": budget_val, "spent": spent,
                "consumed_pct": consumed,
                "remaining": budget_val - spent,
            },
            "team_workload": list(member_map.values()),
            "overdue_tasks": [
                {"id": t.id, "title": t.title, "days_late": (now - t.due_date).days, "priority": t.priority or "medium"}
                for t in overdue_tasks
            ],
        })

    comp_pct = round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0

    return {
        "user_name": user_name,
        "summary": {
            "projects_managed": len(owned),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "overdue_tasks": overdue_total,
            "completion_pct": comp_pct,
        },
        "projects": proj_list,
    }


# ── 4. Team Member Dashboard ────────────────────────────────────────────────

@router.get("/team-member")
async def dashboard_team_member(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    user_id = current_user.id
    user_name = current_user.full_name or current_user.username

    result = await db.execute(select(Task).where(Task.assignee_id == user_id))
    my_tasks = result.scalars().all()

    # if user has no tasks, show some tasks for demo
    if not my_tasks:
        result = await db.execute(select(Task).limit(20))
        my_tasks = result.scalars().all()

    week_start = now - timedelta(days=now.weekday())
    week_end = now + timedelta(days=7)

    by_status: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    completed = 0
    overdue_count = 0
    upcoming_7d = 0
    in_progress_tasks = []
    overdue_tasks = []
    upcoming_deadlines = []
    hours_estimated = 0.0
    hours_actual = 0.0

    for t in my_tasks:
        st = t.status or "todo"
        pr = t.priority or "medium"
        by_status[st] = by_status.get(st, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1
        hours_estimated += t.estimated_hours or 0
        hours_actual += t.actual_hours or 0

        if st in ("done", "completed"):
            completed += 1

        is_overdue = t.due_date and t.due_date < now and st not in ("done", "completed")
        is_upcoming = t.due_date and now <= t.due_date <= week_end and st not in ("done", "completed")

        if is_overdue:
            overdue_count += 1
            overdue_tasks.append({
                "id": t.id, "title": t.title,
                "days_late": (now - t.due_date).days,
                "priority": pr,
            })

        if is_upcoming:
            upcoming_7d += 1
            upcoming_deadlines.append({
                "id": t.id, "title": t.title,
                "days_until": max((t.due_date - now).days, 0),
                "priority": pr,
            })

        if st == "in_progress":
            in_progress_tasks.append({
                "id": t.id, "title": t.title, "priority": pr,
                "progress": t.progress or 0,
                "due_date": t.due_date.isoformat() if t.due_date else None,
            })

    total = len(my_tasks)
    comp_pct = round(completed / total * 100, 1) if total else 0

    # hours this week (heuristic based on actual_hours)
    this_week_hours = round(hours_actual * 0.15, 1)  # approximate weekly fraction

    # projects the user is involved in
    proj_ids = list({t.project_id for t in my_tasks if t.project_id})
    my_projects = []
    if proj_ids:
        result = await db.execute(select(Project).where(Project.id.in_(proj_ids)))
        for p in result.scalars().all():
            my_projects.append({"id": p.id, "name": p.name, "status": p.status, "progress": p.progress or 0})

    return {
        "user_name": user_name,
        "task_summary": {
            "by_status": by_status,
            "by_priority": by_priority,
            "total": total,
            "completed": completed,
            "completion_pct": comp_pct,
            "overdue": overdue_count,
            "upcoming_7d": upcoming_7d,
        },
        "in_progress_tasks": in_progress_tasks,
        "overdue_tasks": overdue_tasks,
        "upcoming_deadlines": upcoming_deadlines,
        "hours": {
            "this_week": this_week_hours,
            "estimated": round(hours_estimated, 1),
            "actual": round(hours_actual, 1),
        },
        "timesheets_this_week": len([t for t in my_tasks if t.status == "in_progress"]),
        "my_projects": my_projects,
    }


# ── 5. Stakeholder Dashboard ────────────────────────────────────────────────

@router.get("/stakeholder")
async def dashboard_stakeholder(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()

    result = await db.execute(select(Milestone))
    milestones = result.scalars().all()

    ms_by_proj: dict[int, list] = {}
    for m in milestones:
        ms_by_proj.setdefault(m.project_id, []).append(m)

    total_planned = 0
    total_delivered = 0
    total_investment = 0

    proj_list = []
    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        progress = p.progress or 0
        total_investment += actual

        # benefits estimation: planned = budget, delivered = budget * progress%
        planned_benefit = budget
        delivered_benefit = round(budget * progress / 100)
        total_planned += planned_benefit
        total_delivered += delivered_benefit
        realization = round(delivered_benefit / planned_benefit * 100, 1) if planned_benefit else 0

        proj_ms = ms_by_proj.get(p.id, [])
        ms_achieved = sum(1 for m in proj_ms if m.status == "achieved")
        ms_total = len(proj_ms)
        ms_rate = round(ms_achieved / ms_total * 100, 1) if ms_total else 0

        # schedule status
        if p.end_date and p.end_date < now and progress < 100:
            sched = "behind"
        elif progress > 70:
            sched = "ahead"
        else:
            sched = "on_track"

        proj_list.append({
            "id": p.id, "name": p.name, "progress": progress,
            "planned_benefit": planned_benefit, "delivered_benefit": delivered_benefit,
            "benefit_realization_pct": realization,
            "schedule_status": sched,
            "roi": _roi(budget, actual, progress),
            "milestones": {"total": ms_total, "achieved": ms_achieved, "achievement_rate": ms_rate},
        })

    benefit_pct = round(total_delivered / total_planned * 100, 1) if total_planned else 0

    # milestone overview
    ms_by_status: dict[str, int] = {}
    for m in milestones:
        ms_by_status[m.status or "pending"] = ms_by_status.get(m.status or "pending", 0) + 1

    ms_achieved_all = sum(1 for m in milestones if m.status == "achieved")
    ms_rate_all = round(ms_achieved_all / len(milestones) * 100, 1) if milestones else 0

    # upcoming milestone timeline (90 days)
    timeline = []
    for m in milestones:
        if m.target_date and now <= m.target_date <= now + timedelta(days=90) and m.status not in ("achieved", "missed"):
            proj_name = ""
            for p in projects:
                if p.id == m.project_id:
                    proj_name = p.name
                    break
            timeline.append({
                "name": m.name, "project": proj_name,
                "target_date": m.target_date.isoformat(),
                "days_until": (m.target_date - now).days,
                "status": m.status or "pending",
                "progress": m.progress or 0,
                "is_critical": m.is_critical or False,
            })
    timeline.sort(key=lambda x: x["days_until"])

    return {
        "benefits_summary": {
            "total_planned_value": total_planned,
            "total_delivered_value": total_delivered,
            "benefit_realization_pct": benefit_pct,
            "total_investment": total_investment,
        },
        "milestone_overview": {
            "total": len(milestones),
            "achievement_rate": ms_rate_all,
            "by_status": ms_by_status,
        },
        "milestone_timeline": timeline,
        "projects": proj_list,
    }
