from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, Risk, User
from app.schemas.schemas import TimelinePrediction, ResourceOptimization, RiskPrediction
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import Optional
import random
import math

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

async def _get_project(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _get_tasks(db: AsyncSession, project_id: int):
    result = await db.execute(select(Task).where(Task.project_id == project_id))
    return result.scalars().all()


# ── /projects-summary ────────────────────────────────────────────────────────

@router.get("/projects-summary")
async def projects_summary(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all projects with task counts for the AI analytics selector."""
    result = await db.execute(select(Project))
    projects = result.scalars().all()
    out = []
    for p in projects:
        cnt = await db.execute(
            select(func.count(Task.id)).where(Task.project_id == p.id)
        )
        out.append({
            "id": p.id,
            "name": p.name,
            "status": p.status or "planning",
            "progress": p.progress or 0,
            "task_count": cnt.scalar() or 0,
        })
    return out


# ── original three endpoints (kept) ─────────────────────────────────────────

@router.get("/timeline-prediction/{project_id}")
async def predict_timeline_legacy(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    total = len(tasks)
    done_tasks = [t for t in tasks if t.status in ("done", "completed")]
    remaining = [t for t in tasks if t.status not in ("done", "completed")]
    done_count = len(done_tasks)

    total_estimated = sum(t.estimated_hours or 4 for t in tasks)
    total_actual = sum(t.actual_hours or 0 for t in done_tasks)
    remaining_hrs = sum((t.estimated_hours or 4) * (1 - (t.progress or 0) / 100) for t in remaining)

    velocity_hrs_day = round(total_actual / max(done_count, 1), 1) if done_count else 4.0
    est_accuracy = round(total_actual / total_estimated, 2) if total_estimated > 0 else 1.0

    pred_days = math.ceil(remaining_hrs / velocity_hrs_day) if velocity_hrs_day > 0 else 30
    pred_completion = now + timedelta(days=pred_days)

    original_end = project.end_date
    on_track = True
    slippage = 0
    if original_end and pred_completion > original_end:
        on_track = False
        slippage = (pred_completion - original_end).days

    margin = max(int(pred_days * 0.25), 1)
    conf_level = min(0.5 + done_count * 0.05, 0.95) if done_count > 0 else 0.45

    overdue_count = sum(1 for t in remaining if t.due_date and t.due_date < now)
    delay_risk = min(overdue_count * 15 + (0 if on_track else 20), 100)

    progress_pct = round(done_count / total * 100) if total else 0

    # completion trend – last 10 done tasks
    trend = []
    for t in done_tasks[-10:]:
        trend.append({"title": t.title[:25], "estimated_hours": t.estimated_hours or 0, "actual_hours": t.actual_hours or 0})

    return {
        "project_id": project_id,
        "prediction": {
            "predicted_completion_date": pred_completion.isoformat(),
            "predicted_remaining_days": pred_days,
            "on_track": on_track,
            "slippage_days": slippage,
            "original_end_date": original_end.isoformat() if original_end else None,
        },
        "confidence": {
            "level": round(conf_level, 2),
            "margin_days": margin,
            "optimistic_date": (now + timedelta(days=max(pred_days - margin, 1))).isoformat(),
            "pessimistic_date": (now + timedelta(days=pred_days + margin)).isoformat(),
            "data_points_used": done_count,
        },
        "velocity": {
            "hours_per_day": velocity_hrs_day,
            "estimation_accuracy": est_accuracy,
        },
        "risk_factors": {"delay_risk_score": delay_risk},
        "summary": {"progress_pct": progress_pct, "total_tasks": total, "done": done_count},
        "completion_trend": trend,
    }


@router.get("/resource-optimization/{project_id}")
async def optimize_resources_legacy(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serves the rich resource data the PredictiveAnalytics frontend expects."""
    return await optimize_resources_v2(project_id, current_user, db)


@router.get("/risk-prediction/{project_id}")
async def predict_risks_legacy(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serves the rich risk data the PredictiveAnalytics frontend expects."""
    return await predict_risks_v2(project_id, current_user, db)


# ── /critical-path-risk/{project_id} ────────────────────────────────────────

@router.get("/critical-path-risk/{project_id}")
async def critical_path_risk(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    critical_tasks = []
    for t in tasks:
        risk_score = 0
        reasons = []
        # overdue
        if t.due_date and t.due_date < now and t.status not in ("done", "completed"):
            days_late = (now - t.due_date).days
            risk_score += min(days_late * 5, 40)
            reasons.append(f"Overdue by {days_late} day(s)")
        # blocked
        if t.status == "blocked":
            risk_score += 30
            reasons.append("Blocked")
        # high/critical priority unfinished
        if t.priority in ("high", "critical") and t.status not in ("done", "completed"):
            risk_score += 15
            reasons.append(f"{t.priority.capitalize()} priority")
        # low progress near due
        if t.due_date and t.progress < 50 and t.status not in ("done", "completed"):
            days_left = (t.due_date - now).days
            if 0 < days_left < 7:
                risk_score += 20
                reasons.append("Low progress near deadline")
        risk_score = min(risk_score, 100)
        level = "critical" if risk_score >= 70 else "high" if risk_score >= 50 else "medium" if risk_score >= 30 else "low"
        critical_tasks.append({
            "task_id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "progress": t.progress,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "risk_score": risk_score, "risk_level": level, "risk_reasons": reasons,
        })

    critical_tasks.sort(key=lambda x: x["risk_score"], reverse=True)

    scores = [c["risk_score"] for c in critical_tasks]
    avg_score = round(sum(scores) / len(scores)) if scores else 0
    max_score = max(scores) if scores else 0
    health = "healthy" if avg_score < 20 else "at_risk" if avg_score < 50 else "critical"

    summary = {
        "critical_count": sum(1 for c in critical_tasks if c["risk_level"] == "critical"),
        "high_count": sum(1 for c in critical_tasks if c["risk_level"] == "high"),
        "medium_count": sum(1 for c in critical_tasks if c["risk_level"] == "medium"),
        "low_count": sum(1 for c in critical_tasks if c["risk_level"] == "low"),
    }

    return {
        "project_id": project_id,
        "critical_path_health": health,
        "average_risk_score": avg_score,
        "max_risk_score": max_score,
        "total_at_risk": summary["critical_count"] + summary["high_count"],
        "summary": summary,
        "critical_tasks": critical_tasks,
    }


# ── /confidence-intervals/{project_id} ──────────────────────────────────────

@router.get("/confidence-intervals/{project_id}")
async def confidence_intervals(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    remaining = [t for t in tasks if t.status not in ("done", "completed")]
    total_remaining_hrs = sum((t.estimated_hours or 4) * (1 - (t.progress or 0) / 100) for t in remaining)

    done_tasks = [t for t in tasks if t.status in ("done", "completed") and t.actual_hours and t.actual_hours > 0]
    velocity = 4.0  # default hrs/day
    if done_tasks:
        avg_actual = sum(t.actual_hours for t in done_tasks) / len(done_tasks)
        velocity = max(avg_actual, 1.0)

    base_days = math.ceil(total_remaining_hrs / velocity) if velocity > 0 else 30

    intervals = [
        {"percentile": "p25", "estimated_days": max(1, int(base_days * 0.7)),
         "completion_date": (now + timedelta(days=int(base_days * 0.7))).isoformat()},
        {"percentile": "p50", "estimated_days": base_days,
         "completion_date": (now + timedelta(days=base_days)).isoformat()},
        {"percentile": "p75", "estimated_days": int(base_days * 1.3),
         "completion_date": (now + timedelta(days=int(base_days * 1.3))).isoformat()},
        {"percentile": "p90", "estimated_days": int(base_days * 1.6),
         "completion_date": (now + timedelta(days=int(base_days * 1.6))).isoformat()},
    ]

    return {
        "project_id": project_id,
        "intervals": intervals,
        "data_points": len(done_tasks),
    }


# ── /predict-risks/{project_id} (rich version for the frontend) ─────────────

@router.get("/predict-risks/{project_id}")
async def predict_risks_v2(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    blocked = sum(1 for t in tasks if t.status == "blocked")
    in_progress = sum(1 for t in tasks if t.status == "in_progress")

    predictions = []

    # Schedule risk
    if total > 0:
        overdue_pct = overdue / total * 100
        sched_prob = min(int(overdue_pct * 2 + 10), 95) if overdue > 0 else 10
        predictions.append({
            "category": "schedule_delay", "probability": sched_prob,
            "impact": "high" if sched_prob > 60 else "medium",
            "description": f"{overdue} task(s) overdue out of {total}",
            "mitigation": "Re-prioritize overdue tasks and add resources to critical items",
        })

    # Resource risk
    if blocked > 0:
        res_prob = min(blocked * 20 + 20, 90)
        predictions.append({
            "category": "resource_constraint", "probability": res_prob,
            "impact": "high" if res_prob > 60 else "medium",
            "description": f"{blocked} task(s) currently blocked",
            "mitigation": "Identify and resolve blockers; consider reallocating resources",
        })

    # Scope risk
    scope_prob = min(total * 3, 70) if total > 10 else 15
    predictions.append({
        "category": "scope_creep", "probability": scope_prob,
        "impact": "medium",
        "description": f"Project has {total} tasks; larger scope increases change risk",
        "mitigation": "Enforce change control and freeze scope for current sprint",
    })

    # Quality risk
    qual_prob = 15
    if done > 0:
        avg_progress = sum(t.progress or 0 for t in tasks) / total
        if avg_progress < 30:
            qual_prob = 45
    predictions.append({
        "category": "quality", "probability": qual_prob,
        "impact": "medium" if qual_prob < 50 else "high",
        "description": "Risk of quality issues based on progress metrics",
        "mitigation": "Increase code-review coverage and schedule regression testing",
    })

    overall = round(sum(p["probability"] for p in predictions) / len(predictions)) if predictions else 0
    level = "critical" if overall > 65 else "high" if overall > 50 else "medium" if overall > 30 else "low"

    return {
        "project_id": project_id,
        "risk_level": level,
        "overall_probability": overall,
        "predictions": predictions,
        "project_health": {
            "total_tasks": total, "done": done, "in_progress": in_progress,
            "overdue": overdue, "blocked": blocked,
            "progress": project.progress or 0,
        },
    }


# ── /optimize-resources/{project_id} (rich version) ─────────────────────────

@router.get("/optimize-resources/{project_id}")
async def optimize_resources_v2(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)

    assignee_hours: dict[int, float] = {}
    for t in tasks:
        if t.assignee_id and t.status not in ("done", "completed"):
            assignee_hours[t.assignee_id] = assignee_hours.get(t.assignee_id, 0) + (t.estimated_hours or 4)

    total_members = len(assignee_hours) or 1
    total_hours = sum(assignee_hours.values())
    avg_hours = total_hours / total_members if total_members else 0

    recommendations = []
    if total_hours > total_members * 40:
        recommendations.append({
            "type": "over_allocation",
            "priority": "high",
            "description": "Team is over-allocated. Consider extending deadlines or adding resources.",
            "action": "Review workload distribution and reassign tasks to balance team capacity.",
        })
    if total_members > 0 and max(assignee_hours.values(), default=0) > avg_hours * 1.5:
        recommendations.append({
            "type": "uneven_distribution",
            "priority": "medium",
            "description": "Work distribution is uneven. Rebalance tasks across team members.",
            "action": "Identify overloaded members and redistribute tasks to underutilized resources.",
        })
    if not recommendations:
        recommendations.append({
            "type": "balanced",
            "priority": "low",
            "description": "Resource allocation looks balanced.",
            "action": "Continue monitoring workload as new tasks are added.",
        })

    return {
        "project_id": project_id,
        "team_metrics": {
            "team_size": total_members,
            "total_remaining_hours": round(total_hours, 1),
            "avg_hours_per_member": round(avg_hours, 1),
            "utilization_pct": min(round(total_hours / (total_members * 40) * 100), 200) if total_members else 0,
        },
        "recommendations": recommendations,
    }


# ── /dashboard/{project_id} ─────────────────────────────────────────────────

@router.get("/dashboard/{project_id}")
async def ai_dashboard(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    blocked = sum(1 for t in tasks if t.status == "blocked")
    progress = project.progress or (round(done / total * 100) if total else 0)

    # Health score
    health = 100
    if total > 0:
        health -= min(overdue * 8, 30)
        health -= min(blocked * 10, 20)
        health += min(int(done / total * 30), 30) - 15
    health = max(0, min(100, health))
    health_label = "Healthy" if health >= 75 else "At Risk" if health >= 50 else "Critical"

    status_dist: dict[str, int] = {}
    for t in tasks:
        status_dist[t.status] = status_dist.get(t.status, 0) + 1

    return {
        "project_id": project_id,
        "health_score": health,
        "health_label": health_label,
        "progress": progress,
        "quick_stats": {
            "total": total, "done": done, "in_progress": in_progress,
            "overdue": overdue, "blocked": blocked,
        },
        "status_distribution": status_dist,
    }


# ── /schedule-impact/{project_id} ───────────────────────────────────────────

class ScheduleImpactRequest(BaseModel):
    added_tasks: int = 0
    added_hours: float = 0
    removed_tasks: int = 0
    resource_change: int = 0


@router.post("/schedule-impact/{project_id}")
async def schedule_impact(
    project_id: int,
    body: ScheduleImpactRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    remaining = [t for t in tasks if t.status not in ("done", "completed")]
    total_rem_hrs = sum((t.estimated_hours or 4) * (1 - (t.progress or 0) / 100) for t in remaining)

    assignees = {t.assignee_id for t in tasks if t.assignee_id}
    team_size = max(len(assignees), 1)
    velocity = round(total_rem_hrs / max(len(remaining), 1), 1) if remaining else 4.0

    net_tasks = body.added_tasks - body.removed_tasks
    added_hrs = body.added_hours + net_tasks * velocity
    new_team = max(team_size + body.resource_change, 1)
    adjusted_velocity = round(velocity * new_team / team_size, 1)

    original_days = math.ceil(total_rem_hrs / (velocity * team_size)) if velocity * team_size > 0 else 30
    new_total_hrs = total_rem_hrs + added_hrs
    new_days = math.ceil(new_total_hrs / (adjusted_velocity * new_team)) if adjusted_velocity * new_team > 0 else 30
    impact_days = new_days - original_days

    severity = "low" if abs(impact_days) <= 3 else "medium" if abs(impact_days) <= 10 else "high" if abs(impact_days) <= 20 else "critical"

    original_completion = (now + timedelta(days=original_days)).isoformat()
    new_completion = (now + timedelta(days=new_days)).isoformat()

    recs = []
    if impact_days > 5:
        recs.append("Consider adding more resources to absorb the additional scope.")
    if impact_days > 10:
        recs.append("Negotiate deadline extension with stakeholders.")
    if body.resource_change < 0:
        recs.append("Losing resources will slow delivery. Re-prioritize tasks.")
    if impact_days <= 0:
        recs.append("Schedule looks stable or improved with these changes.")
    if not recs:
        recs.append("Impact is manageable within current capacity.")

    return {
        "project_id": project_id,
        "scope_change": {
            "net_tasks_change": net_tasks,
            "net_hours_change": round(added_hrs, 1),
        },
        "velocity": {"current": velocity, "adjusted": adjusted_velocity},
        "impact": {
            "impact_days": impact_days,
            "severity": severity,
            "original_completion": original_completion,
            "new_completion": new_completion,
        },
        "recommendations": recs,
    }


# ── /task-estimation ─────────────────────────────────────────────────────────

class TaskEstimationRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    project_id: Optional[int] = None


@router.post("/task-estimation")
async def task_estimation(
    body: TaskEstimationRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Find similar completed tasks based on priority; use actual_hours as baseline
    query = select(Task).where(
        Task.status.in_(["done", "completed"]),
        Task.actual_hours.isnot(None),
    )
    if body.project_id:
        query = query.where(Task.project_id == body.project_id)
    result = await db.execute(query.limit(50))
    done_tasks = result.scalars().all()

    similar = []
    for t in done_tasks:
        score = 0.5
        if t.priority == body.priority:
            score += 0.2
        if body.title and t.title and any(w in t.title.lower() for w in body.title.lower().split() if len(w) > 3):
            score += 0.3
        similar.append({"task_id": t.id, "title": t.title, "actual_hours": t.actual_hours, "similarity_score": round(score, 2)})

    similar.sort(key=lambda x: x["similarity_score"], reverse=True)
    top = similar[:5]

    if top:
        weighted = sum(s["actual_hours"] * s["similarity_score"] for s in top)
        weight_sum = sum(s["similarity_score"] for s in top)
        estimate = round(weighted / weight_sum, 1)
        method = "historical_similarity"
        conf = min(0.5 + len(top) * 0.08, 0.9)
    else:
        pri_map = {"low": 4, "medium": 8, "high": 12, "critical": 16}
        estimate = pri_map.get(body.priority, 8)
        method = "heuristic_default"
        conf = 0.4

    return {
        "title": body.title,
        "estimated_hours": estimate,
        "range": {
            "optimistic": round(estimate * 0.6, 1),
            "pessimistic": round(estimate * 1.6, 1),
        },
        "confidence": round(conf, 2),
        "estimation_method": method,
        "data_points": len(done_tasks),
        "similar_tasks": top,
    }


# ── /risk-forecast/{project_id} ─────────────────────────────────────────────

@router.get("/risk-forecast/{project_id}")
async def risk_forecast(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Comprehensive risk forecast with category scores."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    blocked = sum(1 for t in tasks if t.status == "blocked")

    # Fetch risks from DB
    risk_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = risk_result.scalars().all()
    active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]

    progress = project.progress or (round(done / total * 100) if total else 0)
    budget = project.budget or 0
    actual_cost = project.actual_cost or 0
    budget_pct = round(actual_cost / budget * 100) if budget > 0 else 0

    # Category scoring
    # Schedule risk
    sched_score = 0
    sched_drivers = []
    if total > 0 and overdue > 0:
        sched_score += min(overdue / total * 150, 60)
        sched_drivers.append(f"{overdue} overdue task(s)")
    if project.end_date and project.end_date < now and progress < 100:
        sched_score += 25
        sched_drivers.append("Project past deadline")
    if blocked > 0:
        sched_score += min(blocked * 8, 20)
        sched_drivers.append(f"{blocked} blocked task(s)")
    sched_score = min(round(sched_score), 100)

    # Budget risk
    budget_score = 0
    budget_drivers = []
    if budget > 0:
        if budget_pct > 90:
            budget_score = min(budget_pct - 40, 100)
            budget_drivers.append(f"Budget utilization at {budget_pct}%")
        elif budget_pct > 70:
            budget_score = int((budget_pct - 70) * 1.5)
            budget_drivers.append(f"Budget utilization at {budget_pct}%")
        if actual_cost > budget:
            budget_score = min(budget_score + 30, 100)
            budget_drivers.append("Over budget")
    budget_score = min(round(budget_score), 100)

    # Resource risk
    assignees = {t.assignee_id for t in tasks if t.assignee_id and t.status not in ("done", "completed")}
    unassigned = sum(1 for t in tasks if not t.assignee_id and t.status not in ("done", "completed"))
    res_score = 0
    res_drivers = []
    if unassigned > 0:
        res_score += min(unassigned * 10, 40)
        res_drivers.append(f"{unassigned} unassigned task(s)")
    if len(assignees) > 0:
        per_person = sum(1 for t in tasks if t.status not in ("done", "completed")) / len(assignees)
        if per_person > 8:
            res_score += 30
            res_drivers.append(f"Avg {per_person:.0f} tasks per person")
    res_score = min(round(res_score), 100)

    # Scope risk
    scope_score = 0
    scope_drivers = []
    if total > 20:
        scope_score += min((total - 20) * 2, 40)
        scope_drivers.append(f"Large project ({total} tasks)")
    todo = sum(1 for t in tasks if t.status == "todo")
    if total > 0 and todo / total > 0.6:
        scope_score += 25
        scope_drivers.append(f"{round(todo / total * 100)}% tasks still to-do")
    scope_score = min(round(scope_score), 100)

    # Quality risk
    quality_score = 0
    quality_drivers = []
    high_pri_incomplete = sum(1 for t in tasks if t.priority in ("high", "critical") and t.status not in ("done", "completed"))
    if high_pri_incomplete > 2:
        quality_score += min(high_pri_incomplete * 8, 40)
        quality_drivers.append(f"{high_pri_incomplete} high/critical priority tasks pending")
    if total > 0 and progress < 30:
        quality_score += 20
        quality_drivers.append(f"Low overall progress ({progress}%)")
    quality_score = min(round(quality_score), 100)

    category_scores = {
        "schedule": {"label": "Schedule Risk", "score": sched_score, "drivers": sched_drivers},
        "budget": {"label": "Budget Risk", "score": budget_score, "drivers": budget_drivers},
        "resource": {"label": "Resource Risk", "score": res_score, "drivers": res_drivers},
        "scope": {"label": "Scope Risk", "score": scope_score, "drivers": scope_drivers},
        "quality": {"label": "Quality Risk", "score": quality_score, "drivers": quality_drivers},
    }

    scores = [v["score"] for v in category_scores.values()]
    overall = round(sum(scores) / len(scores))
    level = "critical" if overall >= 65 else "high" if overall >= 45 else "medium" if overall >= 25 else "low"

    return {
        "project_id": project_id,
        "overall_risk_score": overall,
        "overall_risk_level": level,
        "category_scores": category_scores,
        "project_attributes": {
            "total_tasks": total, "done_tasks": done, "overdue_tasks": overdue,
            "blocked_tasks": blocked, "progress": progress,
            "budget": budget, "actual_cost": actual_cost, "budget_utilization": budget_pct,
            "active_risks": len(active_risks), "team_size": len(assignees),
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
        },
    }


# ── /risk-early-warnings/{project_id} ───────────────────────────────────────

@router.get("/risk-early-warnings/{project_id}")
async def risk_early_warnings(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect early warning signals in the project."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    risk_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = risk_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]
    blocked = [t for t in tasks if t.status == "blocked"]

    warnings_list = []

    # Overdue tasks warning
    if overdue:
        sev = "critical" if len(overdue) > 5 else "high" if len(overdue) > 2 else "medium"
        warnings_list.append({
            "title": f"{len(overdue)} Overdue Task(s)",
            "severity": sev,
            "category": "schedule",
            "description": f"{len(overdue)} tasks have passed their due dates without completion.",
            "recommendation": "Review and re-prioritize overdue tasks; add resources if needed.",
            "trend": "worsening" if len(overdue) > 3 else "stable",
            "affected_tasks": [{"id": t.id, "title": t.title} for t in overdue[:5]],
        })

    # Blocked tasks warning
    if blocked:
        sev = "high" if len(blocked) > 2 else "medium"
        warnings_list.append({
            "title": f"{len(blocked)} Blocked Task(s)",
            "severity": sev,
            "category": "resource",
            "description": f"{len(blocked)} tasks are currently blocked and cannot proceed.",
            "recommendation": "Identify blockers and resolve dependencies urgently.",
            "trend": "stable",
            "affected_tasks": [{"id": t.id, "title": t.title} for t in blocked[:5]],
        })

    # High-impact risks
    critical_risks = [r for r in risks if r.risk_score and r.risk_score >= 15 and r.status not in ("closed", "mitigated")]
    if critical_risks:
        warnings_list.append({
            "title": f"{len(critical_risks)} High-Impact Risk(s)",
            "severity": "high",
            "category": "risk",
            "description": f"{len(critical_risks)} identified risks with score ≥ 15.",
            "recommendation": "Activate mitigation plans for top risks immediately.",
            "trend": "stable",
            "affected_tasks": None,
        })

    # Budget overrun
    if project.budget and project.actual_cost and project.actual_cost > project.budget * 0.9:
        pct = round(project.actual_cost / project.budget * 100)
        sev = "critical" if pct > 100 else "high"
        warnings_list.append({
            "title": "Budget Near/Over Limit",
            "severity": sev,
            "category": "budget",
            "description": f"Budget utilization at {pct}%. {'Over budget!' if pct > 100 else 'Approaching limit.'}",
            "recommendation": "Review remaining expenditures and freeze non-essential spending.",
            "trend": "worsening",
            "affected_tasks": None,
        })

    # Low progress near deadline
    if project.end_date:
        days_left = (project.end_date - now).days
        progress = project.progress or 0
        if 0 < days_left < 30 and progress < 50:
            warnings_list.append({
                "title": "Low Progress Near Deadline",
                "severity": "critical",
                "category": "schedule",
                "description": f"Only {progress}% complete with {days_left} days until deadline.",
                "recommendation": "Escalate to stakeholders; consider scope reduction or deadline extension.",
                "trend": "worsening",
                "affected_tasks": None,
            })

    critical_count = sum(1 for w in warnings_list if w["severity"] == "critical")
    high_count = sum(1 for w in warnings_list if w["severity"] == "high")

    return {
        "project_id": project_id,
        "warning_count": len(warnings_list),
        "critical_count": critical_count,
        "high_count": high_count,
        "warnings": warnings_list,
        "checked_at": now.isoformat(),
    }


# ── /risk-progress-adjustment/{project_id} ──────────────────────────────────

@router.get("/risk-progress-adjustment/{project_id}")
async def risk_progress_adjustment(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adjust risk probabilities based on real project progress."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    risk_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = risk_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    total_estimated = sum(t.estimated_hours or 0 for t in tasks)
    total_actual = sum(t.actual_hours or 0 for t in tasks if t.status in ("done", "completed"))
    estimation_accuracy = round(total_actual / total_estimated, 2) if total_estimated > 0 else 1.0
    done_pct = round(done / total * 100) if total else 0
    overdue_pct = round(overdue / total * 100) if total else 0

    # Schedule performance index (1.0 = on track, < 1.0 = behind)
    spi = round(done_pct / max(project.progress or done_pct, 1), 2) if (project.progress or done_pct) else 1.0
    spi = min(spi, 2.0)

    adjustment_factors = {
        "schedule_performance_index": spi,
        "completion_pct": done_pct,
        "overdue_pct": overdue_pct,
        "estimation_accuracy": estimation_accuracy,
        "active_risk_count": sum(1 for r in risks if r.status not in ("closed", "mitigated")),
    }

    adjusted_risks = []
    increased = 0
    decreased = 0
    unchanged = 0

    for r in risks:
        original_prob = r.probability or 3
        original_impact = r.impact or 3
        original_score = original_prob * original_impact

        # Adjust probability based on progress factors
        adj = 0
        reason_parts = []
        if spi < 0.8:
            adj += 1
            reason_parts.append("behind schedule")
        elif spi > 1.2:
            adj -= 1
            reason_parts.append("ahead of schedule")
        if overdue_pct > 20:
            adj += 1
            reason_parts.append("high overdue rate")
        if estimation_accuracy > 1.5:
            adj += 1
            reason_parts.append("poor estimation accuracy")
        if r.status == "mitigated":
            adj -= 1
            reason_parts.append("mitigation applied")
        if r.status == "occurred":
            adj += 1
            reason_parts.append("risk materialized")

        adjusted_prob = max(1, min(5, original_prob + adj))
        adjusted_score = adjusted_prob * original_impact
        change = adjusted_prob - original_prob

        if change > 0:
            increased += 1
        elif change < 0:
            decreased += 1
        else:
            unchanged += 1

        adjusted_risks.append({
            "risk_id": r.id,
            "title": r.title,
            "status": r.status,
            "original_probability": original_prob,
            "adjusted_probability": adjusted_prob,
            "adjustment": change,
            "impact": original_impact,
            "original_score": original_score,
            "adjusted_score": adjusted_score,
            "adjustment_reason": "; ".join(reason_parts) if reason_parts else "No adjustment needed",
        })

    adjusted_risks.sort(key=lambda x: x["adjusted_score"], reverse=True)

    return {
        "project_id": project_id,
        "adjustment_factors": adjustment_factors,
        "adjusted_risks": adjusted_risks,
        "summary": {"increased": increased, "decreased": decreased, "unchanged": unchanged},
    }


# ── /risk-whatif/{project_id} ────────────────────────────────────────────────

class RiskWhatIfRequest(BaseModel):
    scenario_type: str  # scope_increase, deadline_moved, budget_cut, key_person_leaves, risk_materializes
    scope_increase_pct: int = 0
    days_change: int = 0
    cut_pct: int = 0
    resource_id: Optional[int] = None
    risk_id: Optional[int] = None


@router.post("/risk-whatif/{project_id}")
async def risk_whatif(
    project_id: int,
    body: RiskWhatIfRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate what-if risk scenarios."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    remaining = [t for t in tasks if t.status not in ("done", "completed")]
    overdue = sum(1 for t in remaining if t.due_date and t.due_date < now)
    rem_hrs = sum((t.estimated_hours or 4) * (1 - (t.progress or 0) / 100) for t in remaining)
    assignees = {t.assignee_id for t in tasks if t.assignee_id}
    team_size = max(len(assignees), 1)
    velocity = rem_hrs / max(len(remaining), 1) if remaining else 4.0
    current_rem_days = math.ceil(rem_hrs / (velocity * team_size)) if velocity * team_size > 0 else 30

    # Baseline category scores
    progress = project.progress or (round(done / total * 100) if total else 0)
    budget = project.budget or 0
    actual_cost = project.actual_cost or 0
    budget_pct = round(actual_cost / budget * 100) if budget > 0 else 0

    baseline = {
        "schedule": {"label": "Schedule Risk", "score": min(round(overdue / max(total, 1) * 150), 100)},
        "budget": {"label": "Budget Risk", "score": min(max(budget_pct - 50, 0), 100)},
        "resource": {"label": "Resource Risk", "score": min(round(len(remaining) / max(team_size, 1) * 8), 100)},
        "scope": {"label": "Scope Risk", "score": min(max(total - 10, 0) * 3, 100)},
        "quality": {"label": "Quality Risk", "score": min(max(50 - progress, 0) * 2, 100)},
    }
    baseline_overall = round(sum(v["score"] for v in baseline.values()) / 5)

    # Apply scenario delta
    scenario = {k: {"label": v["label"], "baseline": v["score"], "scenario": v["score"]} for k, v in baseline.items()}
    sched_delta = 0
    budget_delta = 0
    description = ""

    sched_delta_days = 0

    if body.scenario_type == "scope_increase":
        pct = body.scope_increase_pct or 20
        description = f"Scope increase by {pct}%"
        extra_tasks = round(total * pct / 100)
        sched_delta = min(extra_tasks * 3, 40)
        scenario["scope"]["scenario"] = min(scenario["scope"]["scenario"] + pct, 100)
        scenario["schedule"]["scenario"] = min(scenario["schedule"]["scenario"] + sched_delta, 100)
        scenario["quality"]["scenario"] = min(scenario["quality"]["scenario"] + 10, 100)
        scenario["resource"]["scenario"] = min(scenario["resource"]["scenario"] + 15, 100)
        extra_hrs = extra_tasks * velocity
        sched_delta_days = math.ceil(extra_hrs / (velocity * team_size)) if velocity * team_size > 0 else 5

    elif body.scenario_type == "deadline_moved":
        days = body.days_change or -14
        description = f"Deadline moved by {days} days"
        if days < 0:
            scenario["schedule"]["scenario"] = min(scenario["schedule"]["scenario"] + abs(days) * 2, 100)
            scenario["quality"]["scenario"] = min(scenario["quality"]["scenario"] + 15, 100)
        else:
            scenario["schedule"]["scenario"] = max(scenario["schedule"]["scenario"] - days, 0)
        sched_delta_days = days

    elif body.scenario_type == "budget_cut":
        cut = body.cut_pct or 15
        description = f"Budget cut by {cut}%"
        scenario["budget"]["scenario"] = min(scenario["budget"]["scenario"] + cut * 2, 100)
        scenario["resource"]["scenario"] = min(scenario["resource"]["scenario"] + cut, 100)
        scenario["schedule"]["scenario"] = min(scenario["schedule"]["scenario"] + 10, 100)
        budget_delta = cut
        sched_delta_days = math.ceil(cut / 5)

    elif body.scenario_type == "key_person_leaves":
        description = "Key team member leaves"
        scenario["resource"]["scenario"] = min(scenario["resource"]["scenario"] + 35, 100)
        scenario["schedule"]["scenario"] = min(scenario["schedule"]["scenario"] + 20, 100)
        scenario["quality"]["scenario"] = min(scenario["quality"]["scenario"] + 10, 100)
        new_team = max(team_size - 1, 1)
        sched_delta_days = math.ceil(rem_hrs / (velocity * new_team)) - current_rem_days if velocity * new_team > 0 else 7

    elif body.scenario_type == "risk_materializes":
        description = "A key risk materializes"
        scenario["schedule"]["scenario"] = min(scenario["schedule"]["scenario"] + 25, 100)
        scenario["budget"]["scenario"] = min(scenario["budget"]["scenario"] + 20, 100)
        scenario["quality"]["scenario"] = min(scenario["quality"]["scenario"] + 15, 100)
        sched_delta_days = 10
        budget_delta = 10

    else:
        description = body.scenario_type
        sched_delta_days = 0

    scenario_overall = round(sum(v["scenario"] for v in scenario.values()) / 5)

    return {
        "project_id": project_id,
        "scenario_params": {"type": body.scenario_type, "description": description},
        "impact_summary": {
            "schedule_impact_days": sched_delta_days,
            "budget_impact_pct": budget_delta,
            "risk_score_change": scenario_overall - baseline_overall,
            "baseline_risk_score": baseline_overall,
            "scenario_risk_score": scenario_overall,
            "current_remaining_days": current_rem_days,
            "scenario_remaining_days": current_rem_days + sched_delta_days,
        },
        "category_comparison": scenario,
    }


# ── /risk-mitigations/{project_id} ──────────────────────────────────────────

@router.get("/risk-mitigations/{project_id}")
async def risk_mitigations(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate actionable mitigation recommendations."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    risk_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = risk_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    blocked = sum(1 for t in tasks if t.status == "blocked")
    progress = project.progress or (round(done / total * 100) if total else 0)

    recommendations = []

    # Schedule recommendations
    if overdue > 0:
        recommendations.append({
            "title": "Address Overdue Tasks",
            "priority": "critical" if overdue > 5 else "high",
            "category": "schedule",
            "description": f"{overdue} task(s) are past their due date. This directly impacts project timeline.",
            "actions": [
                "Review and re-estimate overdue tasks",
                "Assign additional resources to critical-path items",
                "Communicate revised timeline to stakeholders",
            ],
            "expected_impact": "high",
            "effort": "medium",
        })

    # Blocked tasks
    if blocked > 0:
        recommendations.append({
            "title": "Resolve Blocked Tasks",
            "priority": "high",
            "category": "resource",
            "description": f"{blocked} task(s) are blocked, causing cascading delays.",
            "actions": [
                "Identify root cause of each blocker",
                "Escalate external dependencies",
                "Re-arrange task order to work around blockers",
            ],
            "expected_impact": "high",
            "effort": "low",
        })

    # Budget risk
    if project.budget and project.actual_cost:
        util = round(project.actual_cost / project.budget * 100)
        if util > 80:
            recommendations.append({
                "title": "Control Budget Spending",
                "priority": "high" if util > 90 else "medium",
                "category": "budget",
                "description": f"Budget utilization at {util}%. Risk of overrun.",
                "actions": [
                    "Freeze non-essential expenditures",
                    "Review remaining scope for cost savings",
                    "Negotiate with vendors for better rates",
                ],
                "expected_impact": "medium",
                "effort": "medium",
            })

    # Risk mitigation
    active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]
    high_risks = [r for r in active_risks if r.risk_score and r.risk_score >= 12]
    if high_risks:
        recommendations.append({
            "title": "Activate Risk Mitigation Plans",
            "priority": "high",
            "category": "risk",
            "description": f"{len(high_risks)} risk(s) with high impact need active mitigation.",
            "actions": [
                f"Mitigate: {r.title} (score {r.risk_score})" for r in high_risks[:5]
            ] + (["Review and update mitigation plans for remaining risks"] if len(high_risks) > 5 else []),
            "expected_impact": "high",
            "effort": "high",
        })

    # Resource balancing
    assignees = {}
    for t in tasks:
        if t.assignee_id and t.status not in ("done", "completed"):
            assignees[t.assignee_id] = assignees.get(t.assignee_id, 0) + 1
    if assignees:
        max_load = max(assignees.values())
        min_load = min(assignees.values())
        if max_load > min_load * 2 and max_load > 5:
            recommendations.append({
                "title": "Rebalance Workload",
                "priority": "medium",
                "category": "resource",
                "description": f"Workload imbalance detected (max {max_load}, min {min_load} tasks per person).",
                "actions": [
                    "Redistribute tasks from overloaded members",
                    "Consider pair programming for complex items",
                    "Review task assignments weekly",
                ],
                "expected_impact": "medium",
                "effort": "low",
            })

    # Quality recommendation
    if progress < 40 and total > 5:
        recommendations.append({
            "title": "Improve Delivery Velocity",
            "priority": "medium",
            "category": "quality",
            "description": f"Overall progress is only {progress}%. Consider process improvements.",
            "actions": [
                "Break large tasks into smaller deliverables",
                "Implement daily standups if not already done",
                "Set up automated testing to speed up review",
            ],
            "expected_impact": "medium",
            "effort": "medium",
        })

    # General positive note if no major issues
    if not recommendations:
        recommendations.append({
            "title": "Maintain Current Practices",
            "priority": "low",
            "category": "general",
            "description": "No significant risk signals detected. Keep up the good work.",
            "actions": [
                "Continue regular risk reviews",
                "Monitor project metrics weekly",
                "Keep stakeholders informed of progress",
            ],
            "expected_impact": "low",
            "effort": "low",
        })

    return {
        "project_id": project_id,
        "recommendation_count": len(recommendations),
        "risk_summary": {
            "total_tasks": total, "done_tasks": done,
            "overdue_tasks": overdue, "blocked_tasks": blocked,
            "active_risks": len(active_risks), "progress": progress,
        },
        "recommendations": recommendations,
    }


# ── /budget-overrun-prediction/{project_id} ──────────────────────────────────

@router.get("/budget-overrun-prediction/{project_id}")
async def budget_overrun_prediction(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Earned‑value based cost‑overrun prediction."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual_cost = project.actual_cost or 0
    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    progress_pct = project.progress or (round(done / total * 100) if total else 0)

    # Earned Value metrics
    ev = budget * progress_pct / 100  # earned value
    pv = budget * min(progress_pct + 5, 100) / 100  # planned value (approximation)
    cpi = round(ev / actual_cost, 2) if actual_cost > 0 else 1.0
    spi = round(ev / pv, 2) if pv > 0 else 1.0

    # EAC methods
    eac_cpi = round(budget / cpi) if cpi > 0 else budget * 2
    eac_cpi_spi = round(actual_cost + (budget - ev) / (cpi * spi)) if cpi * spi > 0 else budget * 2
    eac_bottom_up = round(actual_cost + (budget - ev) * 1.05)
    eac_methods = {
        "cpi": {"label": "EAC (CPI)", "value": eac_cpi},
        "cpi_spi": {"label": "EAC (CPI×SPI)", "value": eac_cpi_spi},
        "bottom_up": {"label": "Bottom-Up EAC", "value": eac_bottom_up},
    }

    predicted_overrun = eac_cpi - budget
    overrun_pct = round(predicted_overrun / budget * 100, 1) if budget > 0 else 0
    overrun_prob = min(100, max(0, round(50 + overrun_pct * 1.5)))

    # Time
    start = project.start_date or now
    end = project.end_date or (now + timedelta(days=90))
    total_days = max((end - start).days, 1)
    elapsed = max((now - start).days, 0)
    time_elapsed_pct = min(100, round(elapsed / total_days * 100))
    remaining_days = max((end - now).days, 1)

    daily_burn = round(actual_cost / max(elapsed, 1), 2)

    # Budget exhaustion estimate
    if daily_burn > 0 and budget > actual_cost:
        exhaust_days = int((budget - actual_cost) / daily_burn)
        exhaust_date = (now + timedelta(days=exhaust_days)).isoformat()
    else:
        exhaust_date = None

    # Confidence intervals
    base = eac_cpi
    p10 = round(base * 0.88)
    p50 = base
    p90 = round(base * 1.15)

    # Risk signals
    signals = []
    if cpi < 0.9:
        signals.append({"signal": "Low CPI", "detail": f"CPI is {cpi}, indicating poor cost performance", "severity": "critical"})
    elif cpi < 1.0:
        signals.append({"signal": "Below-target CPI", "detail": f"CPI is {cpi}, slightly behind cost baseline", "severity": "warning"})
    if spi < 0.9:
        signals.append({"signal": "Schedule behind", "detail": f"SPI is {spi}, schedule slippage impacts budget", "severity": "critical" if spi < 0.8 else "warning"})
    if daily_burn > budget / total_days * 1.3:
        signals.append({"signal": "High burn rate", "detail": f"${daily_burn:.0f}/day vs planned ${budget / total_days:.0f}/day", "severity": "warning"})
    if time_elapsed_pct > progress_pct + 15:
        signals.append({"signal": "Progress lag", "detail": f"{time_elapsed_pct}% time used but only {progress_pct}% complete", "severity": "warning"})

    return {
        "project_id": project_id,
        "overrun_probability": overrun_prob,
        "predicted_overrun": predicted_overrun,
        "overrun_percentage": overrun_pct,
        "budget_at_completion": budget,
        "actual_cost": actual_cost,
        "earned_value": round(ev),
        "planned_value": round(pv),
        "cpi": cpi,
        "spi": spi,
        "daily_burn_rate": daily_burn,
        "remaining_days": remaining_days,
        "percent_complete": progress_pct,
        "time_elapsed_pct": time_elapsed_pct,
        "eac_methods": eac_methods,
        "confidence_intervals": {
            "p10": {"eac": p10, "overrun": p10 - budget},
            "p50": {"eac": p50, "overrun": p50 - budget},
            "p90": {"eac": p90, "overrun": p90 - budget},
        },
        "budget_exhaustion_date": exhaust_date,
        "risk_signals": signals,
    }


# ── /budget-spend-patterns/{project_id} ─────────────────────────────────────

@router.get("/budget-spend-patterns/{project_id}")
async def budget_spend_patterns(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Spending pattern analysis with category breakdowns and anomaly detection."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual_cost = project.actual_cost or 0
    start = project.start_date or (now - timedelta(days=90))
    end = project.end_date or (now + timedelta(days=90))
    elapsed_months = max((now - start).days / 30, 1)

    # Generate monthly spending data from project timeline
    monthly_spending = []
    cumulative = 0
    months_count = max(int(elapsed_months), 1)
    avg_monthly = actual_cost / months_count if months_count > 0 else 0
    for i in range(months_count):
        d = start + timedelta(days=30 * i)
        period = d.strftime("%Y-%m")
        # Simulate variance: early months lower, later months higher
        factor = 0.7 + 0.6 * (i / max(months_count - 1, 1))
        expenses = round(avg_monthly * factor)
        cumulative += expenses
        monthly_spending.append({
            "period": period,
            "expenses": expenses,
            "cumulative": cumulative,
        })

    # Spend velocity
    current_monthly = round(avg_monthly * 1.1)
    trend = "increasing" if actual_cost > budget * 0.5 and elapsed_months < (end - start).days / 60 else "stable"

    # Category patterns — derive from tasks
    categories_data = {}
    for t in tasks:
        cat = t.priority or "medium"
        cat_label = {"critical": "Engineering", "high": "QA & Testing", "medium": "Design", "low": "Administration"}.get(cat, "Other")
        hrs = t.estimated_hours or 4
        act_hrs = t.actual_hours or 0
        rate = 50  # assumed hourly rate
        categories_data.setdefault(cat_label, {"planned": 0, "actual": 0, "type": "variable"})
        categories_data[cat_label]["planned"] += round(hrs * rate)
        categories_data[cat_label]["actual"] += round(act_hrs * rate) if act_hrs > 0 else round(hrs * rate * 0.6)

    if not categories_data:
        categories_data = {
            "Engineering": {"planned": round(budget * 0.4), "actual": round(actual_cost * 0.42), "type": "variable"},
            "QA & Testing": {"planned": round(budget * 0.2), "actual": round(actual_cost * 0.18), "type": "variable"},
            "Design": {"planned": round(budget * 0.15), "actual": round(actual_cost * 0.16), "type": "variable"},
            "Infrastructure": {"planned": round(budget * 0.15), "actual": round(actual_cost * 0.15), "type": "fixed"},
            "Administration": {"planned": round(budget * 0.1), "actual": round(actual_cost * 0.09), "type": "fixed"},
        }

    total_actual = sum(c["actual"] for c in categories_data.values()) or 1
    category_patterns = []
    for cat, d in categories_data.items():
        util = round(d["actual"] / d["planned"] * 100) if d["planned"] > 0 else 0
        category_patterns.append({
            "category": cat,
            "type": d["type"],
            "planned": d["planned"],
            "actual": d["actual"],
            "variance": d["actual"] - d["planned"],
            "utilization": util,
            "actual_pct": round(d["actual"] / total_actual * 100),
        })

    # Find concentration risk
    top_cat = max(category_patterns, key=lambda c: c["actual"])
    concentrated = top_cat["actual_pct"] > 50

    # Anomalies — flag months where spend deviates significantly
    anomalies = []
    if len(monthly_spending) > 2:
        mean_spend = sum(m["expenses"] for m in monthly_spending) / len(monthly_spending)
        std_spend = max((sum((m["expenses"] - mean_spend) ** 2 for m in monthly_spending) / len(monthly_spending)) ** 0.5, 1)
        for m in monthly_spending:
            dev = (m["expenses"] - mean_spend) / std_spend
            if abs(dev) > 1.5:
                anomalies.append({
                    "period": m["period"],
                    "type": "spike" if dev > 0 else "dip",
                    "amount": m["expenses"],
                    "expected": round(mean_spend),
                    "deviation": round(abs(dev), 1),
                })

    return {
        "project_id": project_id,
        "total_budget": budget,
        "total_spent": actual_cost,
        "monthly_spending": monthly_spending,
        "spend_velocity": {
            "current_monthly": current_monthly,
            "average_monthly": round(avg_monthly),
            "trend": trend,
        },
        "category_patterns": category_patterns,
        "concentration_risk": {
            "is_concentrated": concentrated,
            "top_category": top_cat["category"],
            "top_category_pct": top_cat["actual_pct"],
        },
        "anomalies": anomalies,
    }


# ── /budget-forecast-to-complete/{project_id} ───────────────────────────────

@router.get("/budget-forecast-to-complete/{project_id}")
async def budget_forecast_to_complete(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Forecast remaining cost, ETC methods, TCPI, and monthly projections."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual_cost = project.actual_cost or 0
    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    progress_pct = project.progress or (round(done / total * 100) if total else 0)

    ev = budget * progress_pct / 100
    pv = budget * min(progress_pct + 5, 100) / 100
    cpi = round(ev / actual_cost, 2) if actual_cost > 0 else 1.0
    spi = round(ev / pv, 2) if pv > 0 else 1.0
    remaining_work = budget - ev

    # CPI / SPI status
    def _idx_status(v):
        if v >= 1.0:
            return "good"
        if v >= 0.9:
            return "warning"
        return "critical"

    # ETC methods
    etc_typical = round(remaining_work / cpi) if cpi > 0 else round(remaining_work * 2)
    etc_atypical = round(remaining_work)
    etc_composite = round(remaining_work / (cpi * spi)) if cpi * spi > 0 else round(remaining_work * 2)

    methods = [
        {"method": "Typical (CPI)", "etc": etc_typical, "eac": actual_cost + etc_typical,
         "vac": budget - (actual_cost + etc_typical),
         "description": "Assumes future cost efficiency matches past CPI"},
        {"method": "Atypical", "etc": etc_atypical, "eac": actual_cost + etc_atypical,
         "vac": budget - (actual_cost + etc_atypical),
         "description": "Assumes remaining work will proceed at budgeted rate"},
        {"method": "Composite (CPI×SPI)", "etc": etc_composite, "eac": actual_cost + etc_composite,
         "vac": budget - (actual_cost + etc_composite),
         "description": "Accounts for both cost and schedule performance"},
    ]

    # TCPI
    tcpi_bac = round((budget - ev) / (budget - actual_cost), 2) if (budget - actual_cost) > 0 else 9.99
    feasibility = "feasible" if tcpi_bac <= 1.1 else "challenging" if tcpi_bac <= 1.3 else "unlikely"
    interpretation = f"Need CPI of {tcpi_bac} for remaining work to finish on budget — {feasibility}."

    # Monthly forecast
    start = project.start_date or (now - timedelta(days=60))
    end = project.end_date or (now + timedelta(days=90))
    remaining_months = max(math.ceil((end - now).days / 30), 1)
    planned_monthly = round((budget - actual_cost) / remaining_months)
    forecast_monthly = round(etc_typical / remaining_months) if remaining_months > 0 else 0

    monthly_forecast = []
    cum_forecast = actual_cost
    cum_budget = actual_cost
    for i in range(remaining_months):
        period = (now + timedelta(days=30 * (i + 1))).strftime("%Y-%m")
        cum_forecast += forecast_monthly
        cum_budget += planned_monthly
        monthly_forecast.append({
            "period": period,
            "forecast_spend": forecast_monthly,
            "planned_spend": planned_monthly,
            "cumulative_forecast": cum_forecast,
            "cumulative_budget": cum_budget,
        })

    # Completion prediction
    planned_end = end.isoformat() if end else now.isoformat()
    velocity_factor = 1 / spi if spi > 0 else 1.5
    predicted_days = round((end - now).days * velocity_factor)
    predicted_end = (now + timedelta(days=predicted_days)).isoformat()
    sched_var_days = predicted_days - max((end - now).days, 0)

    return {
        "project_id": project_id,
        "cost_baseline": {
            "bac": budget, "actual_cost": actual_cost,
            "earned_value": round(ev), "remaining_work": round(remaining_work),
        },
        "performance_indices": {
            "cpi": cpi, "cpi_status": _idx_status(cpi),
            "spi": spi, "spi_status": _idx_status(spi),
        },
        "progress": {
            "percent_complete": progress_pct,
            "tasks_total": total, "tasks_completed": done, "tasks_in_progress": in_progress,
        },
        "etc_methods": methods,
        "tcpi": {
            "to_bac": tcpi_bac, "feasibility": feasibility,
            "interpretation": interpretation,
        },
        "monthly_forecast": monthly_forecast,
        "completion_prediction": {
            "planned_end": planned_end,
            "predicted_end": predicted_end,
            "schedule_variance_days": sched_var_days,
        },
    }


# ── /budget-variance-trends/{project_id} ────────────────────────────────────

@router.get("/budget-variance-trends/{project_id}")
async def budget_variance_trends(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historical and predicted cost variance trends."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual_cost = project.actual_cost or 0
    start = project.start_date or (now - timedelta(days=90))
    end = project.end_date or (now + timedelta(days=90))
    progress_pct = project.progress or 0

    ev = budget * progress_pct / 100
    cpi = round(ev / actual_cost, 2) if actual_cost > 0 else 1.0
    cv_amount = round(ev - actual_cost)
    cv_pct = round(cv_amount / budget * 100, 1) if budget else 0

    elapsed_months = max(int((now - start).days / 30), 1)

    # Historical variance trend
    variance_trend = []
    for i in range(elapsed_months):
        frac = (i + 1) / elapsed_months
        d = start + timedelta(days=30 * (i + 1))
        period_ev = budget * progress_pct / 100 * frac
        period_ac = actual_cost * frac * (0.85 + 0.3 * (i / max(elapsed_months - 1, 1)))
        period_cv = round(period_ev - period_ac)
        period_cpi = round(period_ev / period_ac, 2) if period_ac > 0 else 1.0
        variance_trend.append({
            "period": d.strftime("%Y-%m"),
            "cost_variance": period_cv,
            "cv_pct": round(period_cv / budget * 100, 1) if budget else 0,
            "cpi_snapshot": period_cpi,
        })

    # Predicted future variances
    remaining_months = max(math.ceil((end - now).days / 30), 1)
    predicted_variances = []
    for i in range(min(remaining_months, 6)):
        d = now + timedelta(days=30 * (i + 1))
        # Assume trend continues with slight degradation
        degradation = 1 - 0.02 * (i + 1)
        pred_cpi = round(cpi * degradation, 2)
        pred_cv = round(cv_amount * degradation - (budget * 0.02 * (i + 1)))
        pred_cv_pct = round(pred_cv / budget * 100, 1) if budget else 0
        confidence = max(50, 95 - i * 10)
        predicted_variances.append({
            "period": d.strftime("%Y-%m"),
            "predicted_cv": pred_cv,
            "predicted_cv_pct": pred_cv_pct,
            "predicted_cpi": max(round(pred_cpi, 2), 0.5),
            "confidence": confidence,
        })

    # Category (item-level) variances from tasks
    category_variances = []
    # Group tasks by priority as proxy categories
    cat_map = {"critical": "Critical Path", "high": "Core Features", "medium": "Enhancements", "low": "Nice-to-Have"}
    cat_data = {}
    for t in tasks:
        cat = cat_map.get(t.priority or "medium", "Other")
        cat_data.setdefault(cat, {"planned": 0, "actual": 0})
        planned_h = t.estimated_hours or 4
        actual_h = t.actual_hours or (planned_h * 0.8 if t.status in ("done", "completed") else 0)
        rate = 50
        cat_data[cat]["planned"] += round(planned_h * rate)
        cat_data[cat]["actual"] += round(actual_h * rate)

    items_over = 0
    for item, d in cat_data.items():
        var = d["actual"] - d["planned"]
        var_pct = round(var / d["planned"] * 100) if d["planned"] > 0 else 0
        severity = "critical" if var_pct > 20 else "warning" if var_pct > 5 else "good"
        status = "over" if var > 0 else "under" if var < 0 else "on_budget"
        if var > 0:
            items_over += 1
        category_variances.append({
            "item": item, "category": "labor",
            "planned": d["planned"], "actual": d["actual"],
            "variance": var, "variance_pct": var_pct,
            "status": status, "severity": severity,
        })

    # Trend analysis
    if len(variance_trend) >= 2:
        recent_cv = variance_trend[-1]["cost_variance"]
        earlier_cv = variance_trend[-2]["cost_variance"]
        direction = "worsening" if recent_cv < earlier_cv else "improving" if recent_cv > earlier_cv else "stable"
    else:
        direction = "stable"

    breach_risk = "high" if cv_pct < -10 else "medium" if cv_pct < -3 else "low"

    return {
        "project_id": project_id,
        "current_state": {
            "cost_variance": cv_amount,
            "cost_variance_pct": cv_pct,
            "cpi": cpi,
        },
        "trend_analysis": {
            "direction": direction,
            "breach_risk": breach_risk,
            "items_over_budget": items_over,
        },
        "variance_trend": variance_trend,
        "predicted_variances": predicted_variances,
        "category_variances": category_variances,
    }


# ── /budget-cost-optimization/{project_id} ──────────────────────────────────

@router.get("/budget-cost-optimization/{project_id}")
async def budget_cost_optimization(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate cost optimisation recommendations and savings opportunities."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual_cost = project.actual_cost or 0
    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    progress_pct = project.progress or (round(done / total * 100) if total else 0)

    ev = budget * progress_pct / 100
    cpi = round(ev / actual_cost, 2) if actual_cost > 0 else 1.0
    remaining = budget - actual_cost

    start = project.start_date or (now - timedelta(days=60))
    elapsed = max((now - start).days, 1)
    daily_burn = round(actual_cost / elapsed, 2)

    # Optimization recommendations
    recommendations = []
    total_savings = 0

    # Over-budget check
    if cpi < 1.0:
        waste = round((actual_cost - ev) * 0.3)
        total_savings += waste
        recommendations.append({
            "title": "Improve Cost Efficiency",
            "priority": "critical" if cpi < 0.85 else "high",
            "category": "cost_control",
            "description": f"CPI of {cpi} indicates spending {round((1 - cpi) * 100)}% more than earned. Tighten budget controls.",
            "actions": [
                "Review all pending expenditures against value delivered",
                "Implement weekly cost performance reviews",
                "Identify and eliminate low-value activities",
            ],
            "potential_savings": waste,
            "roi": "high",
            "effort": "medium",
        })

    # Resource optimisation
    overestimated = [t for t in tasks if t.estimated_hours and t.actual_hours and t.actual_hours < t.estimated_hours * 0.6 and t.status in ("done", "completed")]
    if len(overestimated) > 2:
        savings = round(sum((t.estimated_hours - t.actual_hours) * 50 for t in overestimated))
        total_savings += round(savings * 0.4)
        recommendations.append({
            "title": "Refine Estimation Process",
            "priority": "medium",
            "category": "estimation",
            "description": f"{len(overestimated)} tasks completed in much less time than estimated — reclaim buffer budgets.",
            "actions": [
                "Update estimation models with actuals",
                "Reduce contingency buffers for well-understood work",
                "Reallocate freed budget to at-risk items",
            ],
            "potential_savings": round(savings * 0.4),
            "roi": "medium",
            "effort": "low",
        })

    # Parallelisation opportunity
    blocked = [t for t in tasks if t.status == "blocked"]
    if blocked:
        delay_cost = round(len(blocked) * daily_burn * 2)
        total_savings += round(delay_cost * 0.5)
        recommendations.append({
            "title": "Unblock Stalled Tasks",
            "priority": "high",
            "category": "process_improvement",
            "description": f"{len(blocked)} blocked tasks. Delays cost ~${delay_cost:,} in idle burn.",
            "actions": [
                "Resolve blocking dependencies immediately",
                "Assign dedicated person to dependency management",
                "Set up escalation process for cross-team blockers",
            ],
            "potential_savings": round(delay_cost * 0.5),
            "roi": "high",
            "effort": "low",
        })

    # Scope trimming
    low_pri = [t for t in tasks if t.priority == "low" and t.status not in ("done", "completed")]
    if low_pri and cpi < 1.0:
        trim_savings = round(sum((t.estimated_hours or 4) * 50 for t in low_pri) * 0.5)
        total_savings += trim_savings
        recommendations.append({
            "title": "Defer Low-Priority Scope",
            "priority": "medium",
            "category": "scope_optimization",
            "description": f"{len(low_pri)} low-priority tasks can be deferred to save budget.",
            "actions": [
                "Move low-priority items to a backlog phase",
                "Negotiate scope reduction with stakeholders",
                "Focus resources on high-value deliverables",
            ],
            "potential_savings": trim_savings,
            "roi": "high",
            "effort": "low",
        })

    # Burn rate warning
    end = project.end_date or (now + timedelta(days=90))
    remaining_days = max((end - now).days, 1)
    needed_daily = round(remaining / remaining_days, 2) if remaining_days > 0 else 0
    if daily_burn > needed_daily * 1.2 and remaining > 0:
        excess_cost = round((daily_burn - needed_daily) * remaining_days * 0.3)
        total_savings += excess_cost
        recommendations.append({
            "title": "Reduce Daily Burn Rate",
            "priority": "high",
            "category": "resource_management",
            "description": f"Burning ${daily_burn:.0f}/day vs needed ${needed_daily:.0f}/day. Excess spend over remaining timeline.",
            "actions": [
                "Right-size team for remaining work",
                "Shift to part-time resourcing where feasible",
                "Automate repetitive tasks to reduce labor hours",
            ],
            "potential_savings": excess_cost,
            "roi": "medium",
            "effort": "medium",
        })

    # Always have at least one recommendation
    if not recommendations:
        recommendations.append({
            "title": "Maintain Cost Discipline",
            "priority": "low",
            "category": "general",
            "description": "Budget performance is healthy. Continue current practices.",
            "actions": [
                "Continue weekly cost reviews",
                "Monitor CPI trends for early warning",
                "Document cost-saving lessons learned",
            ],
            "potential_savings": 0,
            "roi": "low",
            "effort": "low",
        })

    # Optimization score (0‑100, higher is better)
    score = min(100, max(0, round(cpi * 50 + (1 - min(actual_cost / budget, 1.5)) * 30 + (progress_pct / 100) * 20))) if budget > 0 else 50

    return {
        "project_id": project_id,
        "optimization_score": score,
        "total_potential_savings": total_savings,
        "recommendation_count": len(recommendations),
        "financial_summary": {
            "budget": budget,
            "spent": actual_cost,
            "remaining": remaining,
            "cpi": cpi,
            "daily_burn_rate": daily_burn,
        },
        "recommendations": recommendations,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI‑Generated Reports
# ══════════════════════════════════════════════════════════════════════════════

# ── /report/executive-summary ────────────────────────────────────────────────

@router.get("/report/executive-summary")
async def report_executive_summary(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Portfolio‑level weekly executive summary across all projects."""
    now = datetime.now(timezone.utc)
    proj_result = await db.execute(select(Project))
    projects = proj_result.scalars().all()

    total_tasks_all = 0
    completed_tasks_all = 0
    overdue_tasks_all = 0
    total_budget = 0
    total_actual = 0
    green = 0; yellow = 0; red = 0

    project_summaries = []
    critical_issues = []

    for p in projects:
        t_result = await db.execute(select(Task).where(Task.project_id == p.id))
        tasks = t_result.scalars().all()
        r_result = await db.execute(select(Risk).where(Risk.project_id == p.id))
        risks = r_result.scalars().all()

        total = len(tasks)
        done = sum(1 for t in tasks if t.status in ("done", "completed"))
        overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
        progress = p.progress or (round(done / total * 100) if total else 0)
        budget = p.budget or 0
        actual = p.actual_cost or 0
        ev = budget * progress / 100 if budget else 0
        cpi = round(ev / actual, 2) if actual > 0 else 1.0
        active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]
        high_risks = sum(1 for r in active_risks if r.risk_score and r.risk_score >= 12)

        # Health
        health = "green"
        issues = []
        if cpi < 0.85 or overdue > total * 0.3:
            health = "red"
        elif cpi < 1.0 or overdue > 2:
            health = "yellow"
        if health == "green":
            green += 1
        elif health == "yellow":
            yellow += 1
        else:
            red += 1

        if overdue > 3:
            issues.append(f"{overdue} overdue tasks — immediate attention needed")
        if cpi < 0.85:
            issues.append(f"CPI at {cpi} — significant budget overrun risk")
        if high_risks > 0:
            issues.append(f"{high_risks} high‑severity risks unmitigated")
        if issues:
            critical_issues.append({"project": p.name, "issues": issues})

        total_tasks_all += total
        completed_tasks_all += done
        overdue_tasks_all += overdue
        total_budget += budget
        total_actual += actual

        project_summaries.append({
            "project_id": p.id,
            "project_name": p.name,
            "health": health,
            "progress": progress,
            "tasks": {"total": total, "done": done, "overdue": overdue},
            "budget": {"budget": budget, "actual": actual, "cpi": cpi},
            "risks": {"active": len(active_risks), "high_severity": high_risks},
        })

    portfolio_ev = total_budget * (completed_tasks_all / max(total_tasks_all, 1))
    portfolio_cpi = round(portfolio_ev / total_actual, 2) if total_actual > 0 else 1.0
    completion_pct = round(completed_tasks_all / max(total_tasks_all, 1) * 100)

    # Narrative
    lines = [f"This week the portfolio comprises {len(projects)} active project(s) with an overall completion rate of {completion_pct}%."]
    if red > 0:
        lines.append(f"{red} project(s) are flagged red and require executive attention.")
    if overdue_tasks_all > 0:
        lines.append(f"There are {overdue_tasks_all} overdue tasks across the portfolio.")
    if portfolio_cpi < 1.0:
        lines.append(f"Portfolio CPI is {portfolio_cpi}, indicating cost overrun. Review corrective actions.")
    else:
        lines.append(f"Portfolio CPI is {portfolio_cpi}, indicating healthy budget performance.")
    narr = " ".join(lines)

    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    week_end = (now - timedelta(days=now.weekday()) + timedelta(days=6)).strftime("%Y-%m-%d")

    return {
        "period": f"{week_start} — {week_end}",
        "portfolio_overview": {
            "total_projects": len(projects),
            "completion_pct": completion_pct,
            "total_tasks": total_tasks_all,
            "completed_tasks": completed_tasks_all,
            "overdue_tasks": overdue_tasks_all,
            "portfolio_cpi": portfolio_cpi,
            "total_budget": total_budget,
            "total_actual": total_actual,
            "health_distribution": {"green": green, "yellow": yellow, "red": red},
        },
        "project_summaries": project_summaries,
        "critical_issues": critical_issues,
        "narrative": narr,
    }


# ── /report/project-status/{project_id} ─────────────────────────────────────

@router.get("/report/project-status/{project_id}")
async def report_project_status(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detailed project status report with radar, budget, and AI insights."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    r_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = r_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    overdue_tasks = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]
    progress = project.progress or (round(done / total * 100) if total else 0)

    budget = project.budget or 0
    actual = project.actual_cost or 0
    ev = budget * progress / 100 if budget else 0
    pv = budget * min(progress + 5, 100) / 100 if budget else 0
    cpi = round(ev / actual, 2) if actual > 0 else 1.0
    spi = round(ev / pv, 2) if pv > 0 else 1.0
    committed = round(actual * 1.05)

    start = project.start_date or (now - timedelta(days=60))
    end = project.end_date or (now + timedelta(days=90))
    elapsed_days = max((now - start).days, 1)
    total_days = max((end - start).days, 1)
    remaining_days = max((end - now).days, 0)
    time_elapsed_pct = min(100, round(elapsed_days / total_days * 100))

    active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]
    high_risks = sum(1 for r in active_risks if r.risk_score and r.risk_score >= 12)

    # Health indicators
    sched_health = "green" if spi >= 1.0 else ("yellow" if spi >= 0.9 else "red")
    budget_health = "green" if cpi >= 1.0 else ("yellow" if cpi >= 0.9 else "red")

    # AI insights
    insights = []
    if spi < 0.9:
        insights.append({"type": "warning", "message": f"Schedule behind (SPI {spi})", "recommendation": "Re‑prioritize tasks and add resources to critical path"})
    elif spi >= 1.0:
        insights.append({"type": "positive", "message": "Schedule on track", "recommendation": "Continue current pace"})
    if cpi < 0.9:
        insights.append({"type": "warning", "message": f"Budget overrun risk (CPI {cpi})", "recommendation": "Review spending and freeze non‑essential costs"})
    elif cpi >= 1.0:
        insights.append({"type": "positive", "message": "Budget under control", "recommendation": "Maintain cost discipline"})
    if len(overdue_tasks) > 3:
        insights.append({"type": "warning", "message": f"{len(overdue_tasks)} overdue tasks", "recommendation": "Conduct blocking analysis and reassign as needed"})
    if high_risks > 0:
        insights.append({"type": "info", "message": f"{high_risks} high‑severity risks", "recommendation": "Activate mitigation plans immediately"})

    # Narrative
    parts = [f"Project '{project.name}' is {progress}% complete with {remaining_days} days remaining."]
    if spi < 1.0:
        parts.append(f"The schedule is behind plan (SPI {spi}).")
    if cpi < 1.0:
        parts.append(f"Costs are running over plan (CPI {cpi}, actual ${actual:,} vs budget ${budget:,}).")
    if len(overdue_tasks) > 0:
        parts.append(f"{len(overdue_tasks)} task(s) are overdue.")
    if high_risks > 0:
        parts.append(f"{high_risks} high‑severity risk(s) need attention.")
    parts.append("Overall the project health is " + sched_health + " for schedule and " + budget_health + " for budget.")

    return {
        "project_id": project_id,
        "project_name": project.name,
        "schedule": {
            "progress_pct": progress,
            "time_elapsed_pct": time_elapsed_pct,
            "spi": spi,
            "remaining_days": remaining_days,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "schedule_health": sched_health,
        },
        "budget": {
            "bac": budget, "actual": actual, "committed": committed,
            "earned_value": round(ev), "cpi": cpi, "budget_health": budget_health,
        },
        "tasks": {
            "total": total, "done": done, "in_progress": in_progress,
            "overdue": len(overdue_tasks),
            "overdue_list": [
                {"id": t.id, "title": t.title, "priority": t.priority or "medium",
                 "due": t.due_date.isoformat() if t.due_date else None}
                for t in overdue_tasks[:10]
            ],
        },
        "risks": {"active": len(active_risks), "high_severity": high_risks},
        "ai_insights": insights,
        "narrative": " ".join(parts),
    }


# ── /report/performance-trends/{project_id} ─────────────────────────────────

@router.get("/report/performance-trends/{project_id}")
async def report_performance_trends(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Weekly performance trend data: CPI, SPI, velocity, burn rate."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    budget = project.budget or 100000
    actual = project.actual_cost or 0
    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    progress = project.progress or (round(done / total * 100) if total else 0)

    ev = budget * progress / 100
    pv = budget * min(progress + 5, 100) / 100
    cpi = round(ev / actual, 2) if actual > 0 else 1.0
    spi = round(ev / pv, 2) if pv > 0 else 1.0

    start = project.start_date or (now - timedelta(days=60))
    end = project.end_date or (now + timedelta(days=90))
    elapsed_weeks = max(int((now - start).days / 7), 1)

    total_est = sum(t.estimated_hours or 0 for t in tasks)
    total_act = sum(t.actual_hours or 0 for t in tasks if t.status in ("done", "completed"))
    est_accuracy = round(min(total_act / total_est * 100, 150)) if total_est > 0 else 100

    # Synthetic weekly trend data
    weekly_trends = []
    avg_velocity = max(round(done / elapsed_weeks, 1), 0.5)
    for w in range(min(elapsed_weeks, 12)):
        week_label = f"W{w + 1}"
        frac = (w + 1) / elapsed_weeks
        w_cpi = round(1.0 + (cpi - 1.0) * frac + random.uniform(-0.05, 0.05), 2)
        w_spi = round(1.0 + (spi - 1.0) * frac + random.uniform(-0.05, 0.05), 2)
        w_velocity = max(1, round(avg_velocity + random.uniform(-1, 1)))
        w_planned = round(progress * frac * 0.95, 1)
        w_actual = round(progress * frac, 1)
        w_burn = round(actual / elapsed_weeks * (0.8 + 0.4 * (w / max(elapsed_weeks - 1, 1))))
        weekly_trends.append({
            "week": week_label,
            "cpi": max(w_cpi, 0.5),
            "spi": max(w_spi, 0.5),
            "velocity": w_velocity,
            "planned_completion": min(w_planned, 100),
            "actual_completion": min(w_actual, 100),
            "burn_rate": w_burn,
        })

    # Velocity trend
    if len(weekly_trends) >= 4:
        recent = sum(t["velocity"] for t in weekly_trends[-2:]) / 2
        earlier = sum(t["velocity"] for t in weekly_trends[:2]) / 2
        vel_trend = "improving" if recent > earlier * 1.1 else ("declining" if recent < earlier * 0.9 else "stable")
    else:
        vel_trend = "stable"

    # Forecast
    remaining_tasks = total - done
    weeks_to_complete = round(remaining_tasks / avg_velocity) if avg_velocity > 0 else None
    predicted_end = (now + timedelta(weeks=weeks_to_complete)).isoformat() if weeks_to_complete else None

    return {
        "project_id": project_id,
        "project_name": project.name,
        "current_performance": {
            "progress": progress,
            "cpi": cpi,
            "spi": spi,
            "velocity": round(avg_velocity, 1),
            "velocity_trend": vel_trend,
            "estimation_accuracy": est_accuracy,
        },
        "weekly_trends": weekly_trends,
        "forecast": {
            "remaining_tasks": remaining_tasks,
            "weeks_to_complete": weeks_to_complete,
            "predicted_end": predicted_end,
            "planned_end": end.isoformat(),
        },
    }


# ── /report/exceptions/{project_id} ─────────────────────────────────────────

@router.get("/report/exceptions/{project_id}")
async def report_exceptions(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exception report: items breaching thresholds."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    r_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = r_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    overdue = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]
    blocked = [t for t in tasks if t.status == "blocked"]
    progress = project.progress or (round(done / total * 100) if total else 0)

    budget = project.budget or 0
    actual = project.actual_cost or 0
    ev = budget * progress / 100 if budget else 0
    cpi = round(ev / actual, 2) if actual > 0 else 1.0
    pv = budget * min(progress + 5, 100) / 100 if budget else 0
    spi = round(ev / pv, 2) if pv > 0 else 1.0

    active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]
    high_risks = [r for r in active_risks if r.risk_score and r.risk_score >= 12]

    exceptions = []
    cat_counts: dict = {}

    def add_exception(sev, cat, title, desc, metric, action):
        exceptions.append({"severity": sev, "category": cat, "title": title,
                           "description": desc, "metric": metric, "action": action})
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    # Overdue tasks
    if len(overdue) > 0:
        sev = "critical" if len(overdue) > 5 else "high" if len(overdue) > 2 else "medium"
        add_exception(sev, "schedule",
                      f"{len(overdue)} Overdue Task(s)",
                      f"{len(overdue)} tasks past due date. Oldest: {overdue[0].title}.",
                      f"{len(overdue)} tasks",
                      "Review and re‑prioritize overdue items; add resources if needed")

    # Blocked tasks
    if blocked:
        sev = "high" if len(blocked) > 2 else "medium"
        add_exception(sev, "workflow",
                      f"{len(blocked)} Blocked Task(s)",
                      "Blocked tasks prevent downstream progress.",
                      f"{len(blocked)} tasks",
                      "Identify and resolve blockers immediately")

    # CPI breach
    if cpi < 0.9:
        add_exception("critical", "budget",
                      "Cost Performance Below Threshold",
                      f"CPI is {cpi} (threshold 0.90). Spending more than earned.",
                      f"CPI {cpi}",
                      "Freeze discretionary spending; investigate overruns")
    elif cpi < 1.0:
        add_exception("medium", "budget",
                      "Cost Performance Warning",
                      f"CPI is {cpi}, slightly below 1.0.",
                      f"CPI {cpi}",
                      "Monitor closely and control new commitments")

    # SPI breach
    if spi < 0.85:
        add_exception("critical", "schedule",
                      "Schedule Performance Below Threshold",
                      f"SPI is {spi} (threshold 0.85). Significant schedule slippage.",
                      f"SPI {spi}",
                      "Fast‑track critical path items; consider scope reduction")
    elif spi < 1.0:
        add_exception("medium", "schedule",
                      "Schedule Performance Warning",
                      f"SPI is {spi}, behind baseline.",
                      f"SPI {spi}",
                      "Identify bottlenecks and accelerate key tasks")

    # High risks
    if high_risks:
        add_exception("high", "risk",
                      f"{len(high_risks)} High‑Impact Risk(s)",
                      "Risks with score ≥ 12 requiring active mitigation.",
                      f"{len(high_risks)} risks",
                      "Activate mitigation plans and escalate as needed")

    # Budget overrun
    if budget > 0 and actual > budget:
        add_exception("critical", "budget",
                      "Budget Overrun",
                      f"Actual cost ${actual:,} exceeds budget ${budget:,}.",
                      f"+${actual - budget:,}",
                      "Escalate to sponsor; develop recovery plan")

    severity_summary = {
        "critical": sum(1 for e in exceptions if e["severity"] == "critical"),
        "high": sum(1 for e in exceptions if e["severity"] == "high"),
        "medium": sum(1 for e in exceptions if e["severity"] == "medium"),
    }

    # Narrative
    if exceptions:
        narr = f"{len(exceptions)} exception(s) detected for project '{project.name}'. "
        if severity_summary["critical"] > 0:
            narr += f"{severity_summary['critical']} are critical and need immediate attention. "
        narr += "Review the details above and take corrective action."
    else:
        narr = f"No exceptions detected for project '{project.name}'. All metrics are within acceptable thresholds."

    return {
        "project_id": project_id,
        "project_name": project.name,
        "exception_count": len(exceptions),
        "severity_summary": severity_summary,
        "category_summary": cat_counts,
        "exceptions": exceptions,
        "narrative": narr,
    }


# ── /report/narrative/{project_id} ──────────────────────────────────────────

@router.get("/report/narrative/{project_id}")
async def report_narrative(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI‑generated narrative report with structured sections."""
    project = await _get_project(db, project_id)
    tasks = await _get_tasks(db, project_id)
    now = datetime.now(timezone.utc)

    r_result = await db.execute(select(Risk).where(Risk.project_id == project_id))
    risks = r_result.scalars().all()

    total = len(tasks)
    done = sum(1 for t in tasks if t.status in ("done", "completed"))
    in_progress = sum(1 for t in tasks if t.status == "in_progress")
    overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))
    blocked = sum(1 for t in tasks if t.status == "blocked")
    progress = project.progress or (round(done / total * 100) if total else 0)

    budget = project.budget or 0
    actual = project.actual_cost or 0
    ev = budget * progress / 100 if budget else 0
    pv = budget * min(progress + 5, 100) / 100 if budget else 0
    cpi = round(ev / actual, 2) if actual > 0 else 1.0
    spi = round(ev / pv, 2) if pv > 0 else 1.0

    start = project.start_date or (now - timedelta(days=60))
    end = project.end_date or (now + timedelta(days=90))
    remaining_days = max((end - now).days, 0)
    budget_consumed = round(actual / budget * 100) if budget > 0 else 0

    active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]
    high_risks = sum(1 for r in active_risks if r.risk_score and r.risk_score >= 12)

    # Sections
    sections = []

    # 1 — Executive Overview
    overview = f"Project '{project.name}' is currently {progress}% complete with {remaining_days} days until the planned deadline. "
    overview += f"Out of {total} tasks, {done} are completed, {in_progress} are in progress"
    if overdue > 0:
        overview += f", and {overdue} are overdue"
    overview += ". "
    if budget > 0:
        overview += f"The project budget is ${budget:,} with ${actual:,} spent so far ({budget_consumed}% consumed)."
    sections.append({"title": "Executive Overview", "content": overview})

    # 2 — Schedule Analysis
    sched = f"The Schedule Performance Index (SPI) is {spi}. "
    if spi >= 1.0:
        sched += "The project is on or ahead of schedule. "
    elif spi >= 0.9:
        sched += "The project is slightly behind schedule but within acceptable range. "
    else:
        sched += "The project has significant schedule slippage that requires corrective action. "
    if overdue > 0:
        sched += f"{overdue} task(s) are overdue, which is contributing to schedule pressure. "
    if blocked > 0:
        sched += f"{blocked} task(s) are blocked, causing downstream delays. "
    sched += f"At the current pace, the team needs to maintain consistent velocity over the remaining {remaining_days} days."
    sections.append({"title": "Schedule Analysis", "content": sched})

    # 3 — Budget & Cost
    cost = f"The Cost Performance Index (CPI) is {cpi}. "
    if cpi >= 1.0:
        cost += "The project is under budget — good cost management. "
    elif cpi >= 0.9:
        cost += "Costs are slightly over plan. Close monitoring is recommended. "
    else:
        cost += "There is a significant cost overrun. Immediate corrective measures are required. "
    if budget > 0:
        remaining_budget = budget - actual
        cost += f"Remaining budget is ${max(remaining_budget, 0):,}. "
        if remaining_budget < 0:
            cost += f"The project is ${abs(remaining_budget):,} over budget. "
    sections.append({"title": "Budget & Cost Analysis", "content": cost})

    # 4 — Risk Assessment
    risk_text = f"There are {len(active_risks)} active risk(s)"
    if high_risks > 0:
        risk_text += f", of which {high_risks} are high‑severity"
    risk_text += ". "
    if high_risks > 0:
        top = [r for r in active_risks if r.risk_score and r.risk_score >= 12][:3]
        for r in top:
            risk_text += f"\n• {r.title} (score {r.risk_score}): {r.mitigation_plan or 'No mitigation plan documented.'} "
    elif len(active_risks) == 0:
        risk_text += "No active risks — the risk register is clean."
    else:
        risk_text += "All active risks are within acceptable thresholds."
    sections.append({"title": "Risk Assessment", "content": risk_text})

    # 5 — Recommendations
    recs = []
    if overdue > 0:
        recs.append(f"Address the {overdue} overdue task(s) by re-assigning or re-scheduling.")
    if cpi < 1.0:
        recs.append("Implement tighter cost controls and review upcoming expenditures.")
    if spi < 1.0:
        recs.append("Accelerate critical‑path tasks to recover schedule.")
    if high_risks > 0:
        recs.append("Activate mitigation plans for high‑severity risks.")
    if blocked > 0:
        recs.append(f"Resolve blockers on {blocked} task(s) to restore workflow.")
    if not recs:
        recs.append("Continue current practices — all indicators are healthy.")
    sections.append({"title": "Recommendations", "content": "\n".join(f"• {r}" for r in recs)})

    return {
        "project_id": project_id,
        "project_name": project.name,
        "generated_at": now.isoformat(),
        "key_metrics": {
            "progress": progress,
            "spi": spi,
            "cpi": cpi,
            "overdue_tasks": overdue,
            "active_risks": len(active_risks),
            "budget_consumed_pct": budget_consumed,
            "remaining_days": remaining_days,
        },
        "sections": sections,
    }


# ══════════════════════════════════════════════════════════════════════════════
# AI INSIGHTS – Anomalies, Recommendations, Predictive KPIs, Trends
# ══════════════════════════════════════════════════════════════════════════════


# ── /insights/anomalies ──────────────────────────────────────────────────────

@router.get("/insights/anomalies")
async def insights_anomalies(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()
    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()
    result = await db.execute(select(Risk))
    all_risks = result.scalars().all()

    anomalies = []

    task_by_proj: dict[int, list] = {}
    for t in all_tasks:
        task_by_proj.setdefault(t.project_id, []).append(t)

    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        progress = p.progress or 0
        tasks = task_by_proj.get(p.id, [])
        overdue = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]

        # Budget overrun
        if budget and actual > budget * 0.9:
            pct = round(actual / budget * 100, 1)
            sev = "critical" if actual > budget * 1.15 else "high"
            anomalies.append({
                "severity": sev, "type": "budget_overrun",
                "entity_name": p.name, "message": f"Budget consumed {pct}% (${actual:,} of ${budget:,})",
                "value": pct, "threshold": 90,
            })

        # Schedule slip
        if p.end_date and p.end_date < now and progress < 100:
            days_late = (now - p.end_date).days
            sev = "critical" if days_late > 30 else ("high" if days_late > 14 else "medium")
            anomalies.append({
                "severity": sev, "type": "schedule_slip",
                "entity_name": p.name, "message": f"Project {days_late}d past deadline at {progress}% progress",
                "value": days_late, "threshold": 0,
            })

        # High overdue tasks
        if len(overdue) >= 3:
            sev = "high" if len(overdue) >= 5 else "medium"
            anomalies.append({
                "severity": sev, "type": "task_overdue_cluster",
                "entity_name": p.name, "message": f"{len(overdue)} tasks overdue",
                "value": len(overdue), "threshold": 3,
            })

        # Low progress with time running out
        if p.end_date and p.start_date:
            total_d = max((p.end_date - p.start_date).days, 1)
            elapsed_d = max((now - p.start_date).days, 0)
            pct_time = elapsed_d / total_d * 100
            if pct_time > 70 and progress < 40:
                anomalies.append({
                    "severity": "high", "type": "progress_lag",
                    "entity_name": p.name,
                    "message": f"{round(pct_time)}% time elapsed but only {progress}% complete",
                    "value": progress, "threshold": 40,
                })

    # Resource anomalies – anyone with too many active tasks
    user_active: dict[str, int] = {}
    for t in all_tasks:
        if t.assignee_id and t.status not in ("done", "completed"):
            user_active[str(t.assignee_id)] = user_active.get(str(t.assignee_id), 0) + 1
    for uid, cnt in user_active.items():
        if cnt >= 8:
            anomalies.append({
                "severity": "medium", "type": "resource_overload",
                "entity_name": f"User #{uid}", "message": f"{cnt} active tasks assigned",
                "value": cnt, "threshold": 8,
            })

    # Risk anomalies
    for r in all_risks:
        if (r.risk_score or 0) >= 20 and r.status not in ("closed", "mitigated"):
            anomalies.append({
                "severity": "critical", "type": "extreme_risk",
                "entity_name": r.title, "message": f"Risk score {r.risk_score} (prob {r.probability} × impact {r.impact})",
                "value": r.risk_score, "threshold": 20,
            })

    anomalies.sort(key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a["severity"], 4))

    by_sev: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for a in anomalies:
        by_sev[a["severity"]] = by_sev.get(a["severity"], 0) + 1
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1

    return {
        "total_anomalies": len(anomalies),
        "by_severity": {k: by_sev.get(k, 0) for k in ("critical", "high", "medium", "low")},
        "by_type": by_type,
        "anomalies": anomalies,
    }


# ── /insights/recommendations ───────────────────────────────────────────────

@router.get("/insights/recommendations")
async def insights_recommendations(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()
    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()
    result = await db.execute(select(Risk))
    all_risks = result.scalars().all()

    task_by_proj: dict[int, list] = {}
    for t in all_tasks:
        task_by_proj.setdefault(t.project_id, []).append(t)

    risk_by_proj: dict[int, list] = {}
    for r in all_risks:
        risk_by_proj.setdefault(r.project_id, []).append(r)

    recs = []

    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        progress = p.progress or 0
        tasks = task_by_proj.get(p.id, [])
        risks = risk_by_proj.get(p.id, [])
        overdue = [t for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed")]
        active_risks = [r for r in risks if r.status not in ("closed", "mitigated")]

        # Schedule recommendations
        if len(overdue) > 0:
            recs.append({
                "priority": "high" if len(overdue) >= 5 else "medium",
                "category": "schedule",
                "title": f"Address {len(overdue)} overdue tasks",
                "description": f"Project '{p.name}' has {len(overdue)} overdue tasks. Review blockers, re-prioritize, or reassign to reduce schedule debt.",
                "project_name": p.name,
                "impact": "high", "effort": "medium",
            })

        if p.end_date and p.end_date < now + timedelta(days=14) and progress < 80:
            recs.append({
                "priority": "critical",
                "category": "schedule",
                "title": "Fast-track critical path activities",
                "description": f"'{p.name}' is near deadline ({progress}% done). Focus on critical-path tasks and defer non-essential scope.",
                "project_name": p.name,
                "impact": "high", "effort": "high",
            })

        # Budget recommendations
        if budget and actual > budget * 0.85:
            recs.append({
                "priority": "high",
                "category": "budget",
                "title": "Implement cost controls",
                "description": f"'{p.name}' has consumed {round(actual/budget*100)}% of budget. Freeze discretionary spend and optimize resource allocation.",
                "project_name": p.name,
                "impact": "high", "effort": "low",
            })

        # Resource recommendations
        assignees = {}
        for t in tasks:
            if t.assignee_id and t.status not in ("done", "completed"):
                assignees[t.assignee_id] = assignees.get(t.assignee_id, 0) + 1
        overloaded = [uid for uid, c in assignees.items() if c >= 6]
        if overloaded:
            recs.append({
                "priority": "medium",
                "category": "resource",
                "title": "Rebalance team workload",
                "description": f"'{p.name}' has {len(overloaded)} overloaded team member(s). Redistribute tasks to balance utilization.",
                "project_name": p.name,
                "impact": "medium", "effort": "low",
            })

        # Risk recommendations
        high_risks = [r for r in active_risks if (r.risk_score or 0) >= 12]
        if high_risks:
            recs.append({
                "priority": "high",
                "category": "risk",
                "title": f"Mitigate {len(high_risks)} high-severity risks",
                "description": f"'{p.name}' has {len(high_risks)} high-score risks. Execute mitigation plans and escalate blockers.",
                "project_name": p.name,
                "impact": "high", "effort": "medium",
            })

    recs.sort(key=lambda r: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r["priority"], 4))

    by_cat: dict[str, int] = {}
    by_pri: dict[str, int] = {}
    for r in recs:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_pri[r["priority"]] = by_pri.get(r["priority"], 0) + 1

    return {
        "total_recommendations": len(recs),
        "by_category": by_cat,
        "by_priority": by_pri,
        "recommendations": recs,
    }


# ── /insights/predictive-kpis ───────────────────────────────────────────────

@router.get("/insights/predictive-kpis")
async def insights_predictive_kpis(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()
    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()

    task_by_proj: dict[int, list] = {}
    for t in all_tasks:
        task_by_proj.setdefault(t.project_id, []).append(t)

    proj_kpis = []
    total_eac_sum = 0
    total_budget_sum = 0
    cpi_sum = 0
    spi_sum = 0
    health_sum = 0
    n = 0

    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        progress = p.progress or 0
        tasks = task_by_proj.get(p.id, [])
        total_t = len(tasks) or 1
        done = sum(1 for t in tasks if t.status in ("done", "completed"))
        overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status not in ("done", "completed"))

        # EVM metrics
        ev = budget * progress / 100
        cpi = round(ev / actual, 2) if actual > 0 else 1.0
        # SPI
        if p.start_date and p.end_date:
            total_d = max((p.end_date - p.start_date).total_seconds(), 1)
            elapsed = max((now - p.start_date).total_seconds(), 0)
            planned_pct = min(elapsed / total_d * 100, 100)
            spi = round(progress / planned_pct, 2) if planned_pct > 0 else 1.0
        else:
            spi = 1.0

        eac = round(budget / cpi) if cpi > 0 else budget * 2
        vac = budget - eac
        bac_remain = budget - ev
        tcpi = round(bac_remain / (budget - actual), 2) if (budget - actual) > 0 else 2.0

        # Health score (0–100)
        health = 100
        if cpi < 1:
            health -= min(round((1 - cpi) * 50), 30)
        if spi < 1:
            health -= min(round((1 - spi) * 40), 25)
        if overdue > 0:
            health -= min(overdue * 3, 20)
        health = max(health, 0)

        # Velocity
        elapsed_weeks = max(1, (now - (p.start_date or now - timedelta(weeks=4))).days // 7) or 1
        velocity = round(done / elapsed_weeks, 1)

        # Predicted end
        remaining = total_t - done
        weeks_left = round(remaining / velocity) if velocity > 0 else None
        predicted_end = (now + timedelta(weeks=weeks_left)).strftime("%Y-%m-%d") if weeks_left else None

        proj_kpis.append({
            "project_id": p.id,
            "project_name": p.name,
            "health_score": health,
            "progress_pct": progress,
            "cpi": cpi,
            "spi": spi,
            "eac": eac,
            "vac": vac,
            "tcpi": tcpi,
            "task_velocity_per_week": velocity,
            "predicted_end_date": predicted_end,
            "overdue_tasks": overdue,
        })

        total_eac_sum += eac
        total_budget_sum += budget
        cpi_sum += cpi
        spi_sum += spi
        health_sum += health
        n += 1

    n = n or 1

    return {
        "portfolio_summary": {
            "avg_cpi": round(cpi_sum / n, 2),
            "avg_spi": round(spi_sum / n, 2),
            "avg_health_score": round(health_sum / n, 1),
            "portfolio_variance": total_budget_sum - total_eac_sum,
            "active_projects": n,
            "total_eac": total_eac_sum,
            "total_budget": total_budget_sum,
        },
        "projects": proj_kpis,
    }


# ── /insights/trends ────────────────────────────────────────────────────────

@router.get("/insights/trends")
async def insights_trends(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    result = await db.execute(select(Project))
    projects = result.scalars().all()
    result = await db.execute(select(Task))
    all_tasks = result.scalars().all()
    result = await db.execute(select(Risk))
    all_risks = result.scalars().all()

    # --- Task completion trend (past 12 weeks + 4-week forecast) ---
    task_trend = []
    total_done = sum(1 for t in all_tasks if t.status in ("done", "completed"))
    total_created = len(all_tasks)
    avg_done_wk = max(round(total_done / 12, 1), 1)
    avg_created_wk = max(round(total_created / 16, 1), 1)

    for w in range(12):
        week_label = (now - timedelta(weeks=11 - w)).strftime("W%V")
        completed = max(1, round(avg_done_wk + random.uniform(-2, 2)))
        created = max(1, round(avg_created_wk + random.uniform(-2, 2)))
        task_trend.append({
            "week": week_label, "completed": completed, "created": created, "net": completed - created,
        })

    task_forecast = []
    for w in range(1, 5):
        week_label = (now + timedelta(weeks=w)).strftime("W%V")
        task_forecast.append({
            "week": week_label,
            "completed_forecast": max(1, round(avg_done_wk * 1.05 + random.uniform(-1, 1))),
            "created_forecast": max(1, round(avg_created_wk * 0.95 + random.uniform(-1, 1))),
            "net_forecast": round(avg_done_wk * 1.05 - avg_created_wk * 0.95),
        })

    # --- Hours trend (past 12 weeks + forecast) ---
    total_actual_hrs = sum(t.actual_hours or 0 for t in all_tasks)
    avg_hrs_wk = max(round(total_actual_hrs / 12, 1), 5)
    hours_trend = []
    for w in range(12):
        week_label = (now - timedelta(weeks=11 - w)).strftime("W%V")
        hrs = max(1, round(avg_hrs_wk + random.uniform(-5, 5), 1))
        hours_trend.append({
            "week": week_label, "total_hours": hrs,
            "billable_hours": round(hrs * 0.75, 1),
            "utilization_pct": round(min(hrs / max(avg_hrs_wk * 1.2, 1) * 100, 100), 1),
        })

    hours_forecast = []
    for w in range(1, 5):
        week_label = (now + timedelta(weeks=w)).strftime("W%V")
        hours_forecast.append({
            "week": week_label, "total_hours_forecast": round(avg_hrs_wk * 1.02 + random.uniform(-3, 3), 1),
        })

    # --- Budget burn vs progress ---
    budget_burn = []
    for p in projects:
        budget = p.budget or 0
        actual = p.actual_cost or 0
        if budget > 0:
            budget_burn.append({
                "project_name": p.name,
                "burn_pct": round(actual / budget * 100, 1),
                "progress_pct": p.progress or 0,
            })

    # --- Risk trend (past 12 weeks) ---
    active_now = sum(1 for r in all_risks if r.status not in ("closed", "mitigated"))
    risk_trend = []
    for w in range(12):
        week_label = (now - timedelta(weeks=11 - w)).strftime("W%V")
        risk_trend.append({
            "week": week_label,
            "active_risks": max(0, active_now + random.randint(-3, 3) - (11 - w) // 3),
        })

    # --- Progress forecast per project ---
    progress_forecast = []
    for p in projects:
        progress = p.progress or 0
        if p.start_date and p.end_date:
            total_d = max((p.end_date - p.start_date).days, 1)
            elapsed_d = max((now - p.start_date).days, 0)
            if elapsed_d > 0:
                daily_rate = progress / elapsed_d
                remaining_d = max((p.end_date - now).days, 0)
                forecast = min(round(progress + daily_rate * remaining_d), 100)
            else:
                forecast = progress
        else:
            forecast = progress

        progress_forecast.append({
            "project_name": p.name,
            "current_progress": progress,
            "forecasted_progress_at_deadline": forecast,
            "on_track": forecast >= 95,
        })

    return {
        "task_completion": {"trend": task_trend, "forecast": task_forecast},
        "hours": {"trend": hours_trend, "forecast": hours_forecast},
        "budget_burn": budget_burn,
        "risk_trend": risk_trend,
        "progress_forecast": progress_forecast,
    }
