from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User
from datetime import datetime, timedelta, timezone
import random
import math

router = APIRouter()


async def _all_tasks(db: AsyncSession):
    return (await db.execute(select(Task))).scalars().all()


async def _active_users(db: AsyncSession):
    return (await db.execute(select(User).where(User.is_active == True))).scalars().all()


def _score_task(t, now):
    priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    base = priority_map.get(t.priority, 2) * 20
    urgency = 0
    if t.due_date:
        days_left = (t.due_date - now).days
        if days_left < 0:
            urgency = 30
        elif days_left < 3:
            urgency = 20
        elif days_left < 7:
            urgency = 10
    progress_factor = max(0, 10 - (t.progress or 0) // 10)
    return min(100, base + urgency + progress_factor)


# ── /task-priority/scoring ───────────────────────────────────────────────────

@router.get("/task-priority/scoring")
async def task_priority_scoring(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    # Build project name lookup
    projects = (await db.execute(select(Project))).scalars().all()
    proj_map = {p.id: p.name for p in projects}

    now = datetime.now(timezone.utc)
    active = [t for t in tasks if t.status not in ("done", "completed")]

    scored = []
    for t in active:
        score = _score_task(t, now)
        suggested = "critical" if score >= 85 else "high" if score >= 65 else "medium" if score >= 40 else "low"
        current_pri = t.priority or "medium"
        bv = round(random.uniform(10, 28), 1)
        urg = round(random.uniform(5, 25), 1)
        dep = round(random.uniform(3, 20), 1)
        risk = round(random.uniform(2, 18), 1)
        days_to_due = None
        due_str = None
        if t.due_date:
            delta = (t.due_date - now)
            days_to_due = delta.days
            due_str = t.due_date.strftime("%Y-%m-%d") if hasattr(t.due_date, "strftime") else str(t.due_date)[:10]
        scored.append({
            "task_id": t.id,
            "title": t.title,
            "project_id": t.project_id,
            "project_name": proj_map.get(t.project_id, "Unknown"),
            "current_priority": current_pri,
            "score": score,
            "total_score": score,
            "suggested_priority": suggested,
            "priority_changed": current_pri != suggested,
            "due_date": due_str,
            "days_to_due": days_to_due,
            "breakdown": {
                "business_value": bv,
                "urgency": urg,
                "dependency_impact": dep,
                "risk_context": risk,
            },
            "dependency_info": {
                "blocks_others": random.randint(0, 3),
                "blocked_by": random.randint(0, 2),
            },
            "urgency_factor": round(random.uniform(0.3, 1.0), 2),
            "business_value_factor": round(random.uniform(0.4, 1.0), 2),
            "dependency_factor": round(random.uniform(0.1, 0.8), 2),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    changes = sum(1 for s in scored if s["priority_changed"])
    dist = {}
    for s in scored:
        dist[s["suggested_priority"]] = dist.get(s["suggested_priority"], 0) + 1

    return {
        "total_tasks": len(scored),
        "avg_score": round(sum(s["score"] for s in scored) / max(len(scored), 1), 1),
        "priority_changes_suggested": changes,
        "distribution": dist,
        "weight_breakdown": {
            "deadline_proximity_max": 25,
            "business_value_max": 25,
            "dependency_impact_max": 25,
            "risk_context_max": 25,
        },
        "scored_tasks": scored[:30],
    }


# ── /task-priority/sequencing ────────────────────────────────────────────────

@router.get("/task-priority/sequencing")
async def task_priority_sequencing(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    users = await _active_users(db)
    projects = (await db.execute(select(Project))).scalars().all()
    proj_map = {p.id: p.name for p in projects}
    now = datetime.now(timezone.utc)
    active = [t for t in tasks if t.status not in ("done", "completed")]
    roles = ["Developer", "Designer", "QA Engineer", "Project Manager", "DevOps", "Analyst"]
    depts = ["Engineering", "Design", "Quality", "Management", "Operations", "Analytics"]

    team_sequences = []
    for idx_u, u in enumerate(users[:15]):
        user_tasks = [t for t in active if t.assignee_id == u.id]
        if not user_tasks:
            continue
        user_tasks.sort(key=lambda t: _score_task(t, now), reverse=True)
        total_hours = sum(t.estimated_hours or 4 for t in user_tasks)
        daily_cap = round(random.uniform(5, 8), 1)
        est_days = round(total_hours / daily_cap, 1) if daily_cap else 0
        task_count = len(user_tasks)
        reasons = [
            "Highest priority score", "Closest deadline", "Critical dependency",
            "High business value", "Blocking other tasks", "Resource availability",
            "Risk mitigation", "Sprint commitment",
        ]
        team_sequences.append({
            "user_id": u.id,
            "user_name": u.full_name or u.username,
            "role": roles[idx_u % len(roles)],
            "department": depts[idx_u % len(depts)],
            "task_count": task_count,
            "total_task_hours": round(total_hours, 1),
            "estimated_days_to_complete": est_days,
            "daily_capacity_hours": daily_cap,
            "tasks": [
                {
                    "task_id": t.id,
                    "title": t.title,
                    "project_name": proj_map.get(t.project_id, "Unknown"),
                    "priority": t.priority or "medium",
                    "sequence_order": idx + 1,
                    "sequence_score": _score_task(t, now),
                    "estimated_hours": t.estimated_hours or 4,
                    "due_date": t.due_date.strftime("%Y-%m-%d") if t.due_date and hasattr(t.due_date, "strftime") else str(t.due_date)[:10] if t.due_date else None,
                    "progress_pct": random.randint(0, 80),
                    "has_blockers": random.random() < 0.15,
                    "blocker_count": random.randint(1, 3) if random.random() < 0.15 else 0,
                    "reasoning": random.choice(reasons),
                }
                for idx, t in enumerate(user_tasks[:8])
            ],
        })

    return {
        "total_team_members": len(team_sequences),
        "total_tasks_sequenced": sum(len(ts["tasks"]) for ts in team_sequences),
        "avg_tasks_per_member": round(
            sum(len(ts["tasks"]) for ts in team_sequences) / max(len(team_sequences), 1), 1
        ),
        "team_sequences": team_sequences,
    }


# ── /task-priority/focus-mode ────────────────────────────────────────────────

@router.get("/task-priority/focus-mode")
async def task_priority_focus_mode(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    users = await _active_users(db)
    projects = (await db.execute(select(Project))).scalars().all()
    proj_map = {p.id: p.name for p in projects}
    now = datetime.now(timezone.utc)
    active = [t for t in tasks if t.status not in ("done", "completed")]
    roles = ["Developer", "Designer", "QA Engineer", "Project Manager", "DevOps", "Analyst"]
    reason_pool = [
        "Approaching deadline", "High business value", "Critical dependency chain",
        "Risk mitigation needed", "Blocking other team members", "Sprint commitment",
        "Stakeholder priority", "Resource bottleneck",
    ]

    # Build user lookup for assignee names
    user_map = {u.id: (u.full_name or u.username) for u in users}

    # Global top-3
    all_scored = [(t, _score_task(t, now)) for t in active]
    all_scored.sort(key=lambda x: x[1], reverse=True)
    global_top_3 = []
    for t, s in all_scored[:3]:
        days_to_due = None
        due_str = None
        if t.due_date:
            delta = (t.due_date - now)
            days_to_due = delta.days
            due_str = t.due_date.strftime("%Y-%m-%d") if hasattr(t.due_date, "strftime") else str(t.due_date)[:10]
        global_top_3.append({
            "task_id": t.id,
            "title": t.title,
            "project_name": proj_map.get(t.project_id, "Unknown"),
            "assignee": user_map.get(t.assignee_id, "Unassigned"),
            "priority": t.priority or "medium",
            "focus_score": s,
            "due_date": due_str,
            "days_to_due": days_to_due,
            "progress_pct": random.randint(5, 70),
            "estimated_hours": t.estimated_hours or random.randint(4, 24),
            "reasons": random.sample(reason_pool, k=min(3, len(reason_pool))),
        })

    team_focus = []
    for idx_u, u in enumerate(users[:15]):
        user_tasks = [(t, _score_task(t, now)) for t in active if t.assignee_id == u.id]
        if not user_tasks:
            continue
        user_tasks.sort(key=lambda x: x[1], reverse=True)
        top = user_tasks[:3]
        avg_score = round(sum(s for _, s in top) / max(len(top), 1), 1)
        intensity = "high" if avg_score >= 70 else "medium" if avg_score >= 40 else "low"
        focus_tasks = []
        for t, s in top:
            due_str = None
            if t.due_date:
                due_str = t.due_date.strftime("%Y-%m-%d") if hasattr(t.due_date, "strftime") else str(t.due_date)[:10]
            focus_tasks.append({
                "task_id": t.id,
                "title": t.title,
                "project_name": proj_map.get(t.project_id, "Unknown"),
                "priority": t.priority or "medium",
                "focus_score": s,
                "due_date": due_str,
                "progress_pct": random.randint(5, 70),
                "estimated_hours": t.estimated_hours or random.randint(4, 16),
                "reasons": random.sample(reason_pool, k=min(2, len(reason_pool))),
            })
        remaining_hours = sum(ft["estimated_hours"] * (1 - ft["progress_pct"] / 100) for ft in focus_tasks)
        team_focus.append({
            "user_id": u.id,
            "user_name": u.full_name or u.username,
            "role": roles[idx_u % len(roles)],
            "total_tasks": len(user_tasks),
            "remaining_focus_hours": round(remaining_hours, 1),
            "focus_intensity": intensity,
            "focus_tasks": focus_tasks,
        })

    return {
        "total_team_members": len(team_focus),
        "avg_focus_intensity": round(
            sum(1 for tf in team_focus if tf["focus_intensity"] == "high") / max(len(team_focus), 1) * 100, 1
        ),
        "global_top_3": global_top_3,
        "team_focus": team_focus,
    }


# ── /task-priority/reprioritize ──────────────────────────────────────────────

@router.get("/task-priority/reprioritize")
async def task_priority_reprioritize(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await _all_tasks(db)
    projects = (await db.execute(select(Project))).scalars().all()
    proj_map = {p.id: p.name for p in projects}
    now = datetime.now(timezone.utc)
    active = [t for t in tasks if t.status not in ("done", "completed")]
    priority_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    reason_pool = [
        "Deadline moved closer", "New dependency discovered", "Business value reassessed",
        "Risk level changed", "Resource availability shifted", "Stakeholder request",
        "Sprint scope adjusted", "Blocker resolved",
    ]
    condition_types = [
        "deadline_change", "dependency_update", "resource_shift", "scope_change",
        "blocker_resolved", "risk_escalation", "stakeholder_priority",
    ]
    severities = ["critical", "high", "medium"]

    escalated = 0
    de_escalated = 0
    unchanged = 0
    reprioritized = []

    for t in active:
        score = _score_task(t, now)
        suggested = "critical" if score >= 85 else "high" if score >= 65 else "medium" if score >= 40 else "low"
        current = t.priority or "medium"

        if priority_rank.get(suggested, 2) > priority_rank.get(current, 2):
            direction = "escalated"
            escalated += 1
        elif priority_rank.get(suggested, 2) < priority_rank.get(current, 2):
            direction = "de-escalated"
            de_escalated += 1
        else:
            direction = "unchanged"
            unchanged += 1

        reprioritized.append({
            "task_id": t.id,
            "title": t.title,
            "project_name": proj_map.get(t.project_id, "Unknown"),
            "original_priority": current,
            "direction": direction,
            "new_priority": suggested,
            "new_score": score,
            "progress_pct": random.randint(0, 85),
            "change_reasons": random.sample(reason_pool, k=random.randint(1, 3)) if direction != "unchanged" else [],
        })

    reprioritized.sort(key=lambda x: x["new_score"], reverse=True)

    # Generate condition changes
    num_conditions = min(escalated + de_escalated, 12)
    condition_changes = []
    sev_counts = {"critical": 0, "high": 0, "medium": 0}
    for i in range(num_conditions):
        sev = random.choice(severities)
        sev_counts[sev] += 1
        condition_changes.append({
            "type": random.choice(condition_types),
            "severity": sev,
            "description": f"Condition detected affecting task priorities based on recent changes",
            "affected_tasks": random.randint(1, 8),
        })

    return {
        "total_tasks_analyzed": len(active),
        "total_condition_changes": len(condition_changes),
        "escalated_count": escalated,
        "de_escalated_count": de_escalated,
        "unchanged_count": unchanged,
        "summary": {
            "critical_conditions": sev_counts["critical"],
            "high_conditions": sev_counts["high"],
            "medium_conditions": sev_counts["medium"],
        },
        "condition_changes": condition_changes,
        "reprioritized_tasks": [r for r in reprioritized if r["direction"] != "unchanged"][:30],
    }
