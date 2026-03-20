"""
RAID Log endpoint — aggregates Risks, Assumptions, Issues, and Dependencies
into a single unified view for project governance.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Risk, Issue, Project, Task, task_dependencies

router = APIRouter()


def _severity_from_score(score: Optional[int]) -> str:
    if not score:
        return "low"
    if score >= 20:
        return "critical"
    if score >= 12:
        return "high"
    if score >= 6:
        return "medium"
    return "low"


def _days_open(created_at) -> int:
    if not created_at:
        return 0
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - created).days)


@router.get("")
async def get_raid_log(
    project_id: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get unified RAID log combining Risks, Assumptions, Issues, and Dependencies."""
    now = datetime.now(timezone.utc)
    items = []

    # ── Risks ────────────────────────────────────────────────────────────────
    risk_q = select(Risk).options(selectinload(Risk.project))
    if project_id:
        risk_q = risk_q.where(Risk.project_id == project_id)
    risks = (await db.execute(risk_q)).scalars().all()

    for r in risks:
        items.append({
            "raid_type": "risk",
            "id": r.id,
            "project_id": r.project_id,
            "project_name": r.project.name if r.project else None,
            "title": r.title,
            "description": r.description or "",
            "status": r.status or "identified",
            "severity": _severity_from_score(r.risk_score),
            "score": r.risk_score,
            "owner": None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "days_open": _days_open(r.created_at),
        })

    # ── Assumptions (derived from risks with mitigation plans) ───────────────
    # Treat risks that have mitigation plans as having inherent assumptions
    assumption_id = 0
    for r in risks:
        if r.mitigation_plan and r.status in ("identified", "mitigated"):
            assumption_id += 1
            items.append({
                "raid_type": "assumption",
                "id": 10000 + r.id,
                "project_id": r.project_id,
                "project_name": r.project.name if r.project else None,
                "title": f"Assumption: {r.title} mitigation is viable",
                "description": f"Assumes the mitigation plan is effective: {r.mitigation_plan}",
                "status": "validated" if r.status == "mitigated" else "unvalidated",
                "severity": _severity_from_score(r.risk_score),
                "score": r.risk_score,
                "owner": None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "days_open": _days_open(r.created_at),
            })

    # ── Issues ───────────────────────────────────────────────────────────────
    issue_q = select(Issue).options(selectinload(Issue.project))
    if project_id:
        issue_q = issue_q.where(Issue.project_id == project_id)
    issues = (await db.execute(issue_q)).scalars().all()

    for i in issues:
        sev = i.severity.value if hasattr(i.severity, "value") else str(i.severity or "medium")
        sts = i.status.value if hasattr(i.status, "value") else str(i.status or "open")
        items.append({
            "raid_type": "issue",
            "id": i.id,
            "project_id": i.project_id,
            "project_name": i.project.name if i.project else None,
            "title": i.title,
            "description": i.description or "",
            "status": sts.lower(),
            "severity": sev.lower(),
            "score": i.priority,
            "owner": None,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "days_open": i.days_open or _days_open(i.created_at),
        })

    # ── Dependencies (from task dependencies) ────────────────────────────────
    dep_rows = (await db.execute(select(task_dependencies))).fetchall()

    # Load tasks for names and project filtering
    task_ids = set()
    for row in dep_rows:
        task_ids.add(row.predecessor_id)
        task_ids.add(row.successor_id)

    tasks_map = {}
    if task_ids:
        task_result = await db.execute(
            select(Task).options(selectinload(Task.project)).where(Task.id.in_(task_ids))
        )
        for t in task_result.scalars().all():
            tasks_map[t.id] = t

    for idx, row in enumerate(dep_rows):
        pred = tasks_map.get(row.predecessor_id)
        succ = tasks_map.get(row.successor_id)
        if not pred or not succ:
            continue

        # Filter by project if specified
        if project_id and pred.project_id != project_id and succ.project_id != project_id:
            continue

        is_cross = pred.project_id != succ.project_id
        blocked = pred.status not in ("done", "completed")
        dep_status = "blocked" if blocked else "on_track"
        dep_sev = "high" if blocked else "low"

        items.append({
            "raid_type": "dependency",
            "id": 20000 + idx,
            "project_id": pred.project_id,
            "project_name": pred.project.name if pred.project else None,
            "title": f"{pred.title} \u2192 {succ.title}",
            "description": f"Type: {row.dependency_type or 'finish_to_start'}",
            "status": dep_status,
            "severity": dep_sev,
            "score": None,
            "owner": None,
            "created_at": pred.created_at.isoformat() if pred.created_at else None,
            "days_open": _days_open(pred.created_at),
            "is_cross_project": is_cross,
        })

    # ── Summary ──────────────────────────────────────────────────────────────
    risk_count = sum(1 for i in items if i["raid_type"] == "risk")
    assumption_count = sum(1 for i in items if i["raid_type"] == "assumption")
    issue_count = sum(1 for i in items if i["raid_type"] == "issue")
    dep_count = sum(1 for i in items if i["raid_type"] == "dependency")
    critical_count = sum(
        1 for i in items if i["severity"] in ("critical", "high")
    )

    # Sort by severity (critical first), then days_open desc
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    items.sort(key=lambda x: (sev_order.get(x["severity"], 9), -x["days_open"]))

    return {
        "items": items,
        "summary": {
            "risks": risk_count,
            "assumptions": assumption_count,
            "issues": issue_count,
            "dependencies": dep_count,
            "critical_count": critical_count,
        },
    }
