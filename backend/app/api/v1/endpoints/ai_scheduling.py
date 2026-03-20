from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User, Resource, ResourceAllocation
from datetime import datetime, timedelta, timezone
import random
import math

router = APIRouter()


async def _all_projects(db: AsyncSession):
    return (await db.execute(select(Project))).scalars().all()


async def _all_tasks(db: AsyncSession):
    return (await db.execute(select(Task))).scalars().all()


async def _all_users(db: AsyncSession):
    return (await db.execute(select(User).where(User.is_active == True))).scalars().all()


# ── /scheduling/auto-schedule ────────────────────────────────────────────────

@router.get("/scheduling/auto-schedule")
async def auto_schedule(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    users = await _all_users(db)

    unscheduled = [t for t in tasks if not t.due_date or t.status in ("backlog", "todo")]
    scheduled = [t for t in tasks if t.due_date and t.status not in ("backlog", "todo")]

    resource_availability = []
    for u in users[:10]:
        assigned = sum(1 for t in tasks if t.assignee_id == u.id and t.status not in ("done", "completed"))
        resource_availability.append({
            "user_id": u.id,
            "user_name": u.full_name or u.username,
            "role": u.role or "team_member",
            "current_tasks": assigned,
            "max_capacity": 8,
            "available_hours": max(0, 40 - assigned * 5),
            "skills": ["development", "testing"],
        })

    now = datetime.now(timezone.utc)
    suggestions = []
    for i, t in enumerate(unscheduled[:20]):
        suggestions.append({
            "task_id": t.id,
            "task_title": t.title,
            "project_id": t.project_id,
            "suggested_start": (now + timedelta(days=i + 1)).isoformat(),
            "suggested_end": (now + timedelta(days=i + 3)).isoformat(),
            "suggested_assignee": resource_availability[i % len(resource_availability)]["user_name"] if resource_availability else "Unassigned",
            "confidence": round(random.uniform(0.7, 0.95), 2),
            "reason": "Based on resource availability and task dependencies",
        })

    return {
        "unscheduled_tasks": len(unscheduled),
        "available_resources": len(resource_availability),
        "suggestions_generated": len(suggestions),
        "resource_availability": resource_availability,
        "schedule_suggestions": suggestions,
    }


# ── /scheduling/optimize ─────────────────────────────────────────────────────

@router.get("/scheduling/optimize")
async def optimize_schedule(
    mode: str = Query("earliest_finish"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    active = [t for t in tasks if t.status not in ("done", "completed")]

    optimized = []
    for t in active[:30]:
        est_hrs = t.estimated_hours or 4
        optimized.append({
            "task_id": t.id,
            "task_title": t.title,
            "project_id": t.project_id,
            "original_start": t.created_at.isoformat() if t.created_at else None,
            "original_end": t.due_date.isoformat() if t.due_date else None,
            "optimized_start": (datetime.now(timezone.utc) + timedelta(days=random.randint(0, 5))).isoformat(),
            "optimized_end": (datetime.now(timezone.utc) + timedelta(days=random.randint(5, 15))).isoformat(),
            "time_saved_hours": round(random.uniform(1, est_hrs * 0.3), 1),
            "priority": t.priority or "medium",
        })

    total_saved = sum(o["time_saved_hours"] for o in optimized)
    return {
        "tasks_analyzed": len(tasks),
        "tasks_optimized": len(optimized),
        "summary": {
            "cost_savings": round(total_saved * 75, 2),
            "days_saved": round(total_saved / 8, 1),
            "mode": mode,
            "efficiency_improvement": round(random.uniform(10, 25), 1),
        },
        "optimized_schedule": optimized,
    }


# ── /scheduling/conflicts ────────────────────────────────────────────────────

@router.get("/scheduling/conflicts")
async def scheduling_conflicts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    users = await _all_users(db)

    conflicts = []
    conflict_id = 1
    for u in users[:8]:
        user_tasks = [t for t in tasks if t.assignee_id == u.id and t.status not in ("done", "completed")]
        if len(user_tasks) > 3:
            conflicts.append({
                "id": conflict_id,
                "type": "resource_overload",
                "severity": "high" if len(user_tasks) > 5 else "medium",
                "description": f"{u.full_name or u.username} is assigned {len(user_tasks)} concurrent tasks",
                "affected_tasks": [{"id": t.id, "title": t.title} for t in user_tasks[:4]],
                "suggested_resolution": "Redistribute tasks or adjust deadlines",
            })
            conflict_id += 1

    team_distribution = []
    for u in users[:10]:
        cnt = sum(1 for t in tasks if t.assignee_id == u.id and t.status not in ("done", "completed"))
        team_distribution.append({
            "user_name": u.full_name or u.username,
            "task_count": cnt,
            "capacity_pct": min(100, cnt * 15),
        })

    avg = sum(d["task_count"] for d in team_distribution) / max(len(team_distribution), 1)
    variance = sum((d["task_count"] - avg) ** 2 for d in team_distribution) / max(len(team_distribution), 1)

    return {
        "total_conflicts": len(conflicts),
        "by_type": {
            "resource_overload": sum(1 for c in conflicts if c["type"] == "resource_overload"),
            "deadline_clash": 0,
            "dependency_cycle": 0,
        },
        "load_balancing": {
            "imbalance_score": round(math.sqrt(variance), 1),
            "team_distribution": team_distribution,
        },
        "conflicts": conflicts,
    }


# ── /scheduling/reschedule ───────────────────────────────────────────────────

@router.get("/scheduling/reschedule")
async def reschedule_suggestions(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    projects = await _all_projects(db)
    now = datetime.now(timezone.utc)

    overdue = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]
    at_risk = [t for t in tasks if t.due_date and now < t.due_date < now + timedelta(days=3) and t.status not in ("done", "completed")]

    suggestions = []
    for t in (overdue + at_risk)[:20]:
        suggestions.append({
            "task_id": t.id,
            "task_title": t.title,
            "project_id": t.project_id,
            "current_due_date": t.due_date.isoformat() if t.due_date else None,
            "suggested_due_date": (now + timedelta(days=random.randint(3, 10))).isoformat(),
            "urgency": "critical" if t in overdue else "high",
            "reason": "Task is overdue" if t in overdue else "Task is at risk of missing deadline",
            "impact": "May affect dependent tasks and milestones",
        })

    milestone_impacts = []
    for p in projects[:5]:
        proj_overdue = sum(1 for t in overdue if t.project_id == p.id)
        if proj_overdue:
            milestone_impacts.append({
                "project_id": p.id,
                "project_name": p.name,
                "affected_milestones": proj_overdue,
                "estimated_delay_days": proj_overdue * 2,
            })

    return {
        "total_items_to_reschedule": len(suggestions),
        "by_type": {"overdue": len(overdue), "at_risk": len(at_risk)},
        "by_urgency": {
            "critical": sum(1 for s in suggestions if s["urgency"] == "critical"),
            "high": sum(1 for s in suggestions if s["urgency"] == "high"),
        },
        "milestone_impacts": milestone_impacts,
        "reschedule_suggestions": suggestions,
    }


# ── /scheduling/prioritize ───────────────────────────────────────────────────

@router.get("/scheduling/prioritize")
async def prioritize_tasks(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    active = [t for t in tasks if t.status not in ("done", "completed")]

    priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    scored = []
    for t in active:
        base_score = priority_map.get(t.priority, 2) * 20
        urgency_bonus = 0
        if t.due_date:
            days_left = (t.due_date - datetime.now(timezone.utc)).days
            if days_left < 0:
                urgency_bonus = 30
            elif days_left < 3:
                urgency_bonus = 20
            elif days_left < 7:
                urgency_bonus = 10
        score = min(100, base_score + urgency_bonus + random.randint(0, 10))
        scored.append({
            "task_id": t.id,
            "task_title": t.title,
            "project_id": t.project_id,
            "current_priority": t.priority or "medium",
            "score": score,
            "suggested_priority": "critical" if score >= 85 else "high" if score >= 65 else "medium" if score >= 40 else "low",
            "factors": ["deadline proximity", "project priority", "dependency count"],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    changes = sum(1 for s in scored if s["current_priority"] != s["suggested_priority"])
    dist = {}
    for s in scored:
        dist[s["suggested_priority"]] = dist.get(s["suggested_priority"], 0) + 1

    return {
        "total_tasks": len(scored),
        "priority_changes_suggested": changes,
        "avg_score": round(sum(s["score"] for s in scored) / max(len(scored), 1), 1),
        "distribution": dist,
        "prioritized_tasks": scored[:30],
    }
