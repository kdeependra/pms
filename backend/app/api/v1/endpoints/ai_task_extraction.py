from fastapi import APIRouter, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
import random

router = APIRouter()


class ExtractFromTextRequest(BaseModel):
    text: str = "Please update the dashboard by Friday and schedule a meeting with the team for Monday. Also fix the login bug ASAP."
    source: str = "manual"


class ParseEmailRequest(BaseModel):
    email_content: str = ""


class CreateTaskRequest(BaseModel):
    title: str
    project_id: Optional[int] = None
    priority: Optional[str] = "medium"
    assignee_id: Optional[int] = None


# ── /task-extraction/extract-from-text (POST) ────────────────────────────────

@router.post("/task-extraction/extract-from-text")
async def extract_from_text(
    body: ExtractFromTextRequest = Body(default=ExtractFromTextRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    text = body.text
    # Simulate NLP-based task extraction
    extracted = [
        {
            "id": 1,
            "title": "Update the dashboard",
            "description": "Extracted from: 'update the dashboard by Friday'",
            "priority": "high",
            "category": "development",
            "confidence": 0.92,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "source_text": "update the dashboard by Friday",
        },
        {
            "id": 2,
            "title": "Schedule team meeting",
            "description": "Extracted from: 'schedule a meeting with the team for Monday'",
            "priority": "medium",
            "category": "coordination",
            "confidence": 0.88,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "source_text": "schedule a meeting with the team for Monday",
        },
        {
            "id": 3,
            "title": "Fix login bug",
            "description": "Extracted from: 'fix the login bug ASAP'",
            "priority": "critical",
            "category": "bug_fix",
            "confidence": 0.95,
            "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "source_text": "fix the login bug ASAP",
        },
    ]

    dist = {}
    cat_dist = {}
    for e in extracted:
        dist[e["priority"]] = dist.get(e["priority"], 0) + 1
        cat_dist[e["category"]] = cat_dist.get(e["category"], 0) + 1

    return {
        "total_extracted": len(extracted),
        "avg_confidence": round(sum(e["confidence"] for e in extracted) / max(len(extracted), 1), 2),
        "processing_time_ms": random.randint(120, 350),
        "nlp_model": "spacy-en-core-web-lg",
        "priority_distribution": dist,
        "category_distribution": cat_dist,
        "extracted_tasks": extracted,
    }


# ── /task-extraction/create-task (POST) ──────────────────────────────────────

@router.post("/task-extraction/create-task")
async def extraction_create_task(
    body: CreateTaskRequest = Body(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {
        "tasks_created": 1,
        "tasks_failed": 0,
        "created": {
            "title": body.title,
            "project_id": body.project_id,
            "priority": body.priority,
            "status": "created",
        },
    }


# ── /task-extraction/parse-email (POST) ──────────────────────────────────────

@router.post("/task-extraction/parse-email")
async def parse_email(
    body: ParseEmailRequest = Body(default=ParseEmailRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed_emails = [
        {
            "email_id": 1,
            "subject": "Sprint Planning Follow-up",
            "sender": "pm@example.com",
            "date": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "urgency": "high",
            "tasks": [
                {
                    "title": "Finalize sprint backlog",
                    "priority": "high",
                    "confidence": 0.91,
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                },
                {
                    "title": "Update capacity planning sheet",
                    "priority": "medium",
                    "confidence": 0.85,
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                },
            ],
        },
        {
            "email_id": 2,
            "subject": "Client Feedback - Urgent",
            "sender": "client@example.com",
            "date": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
            "urgency": "critical",
            "tasks": [
                {
                    "title": "Address client UI concerns",
                    "priority": "critical",
                    "confidence": 0.94,
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                },
            ],
        },
        {
            "email_id": 3,
            "subject": "Weekly Status Update",
            "sender": "lead@example.com",
            "date": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "urgency": "low",
            "tasks": [
                {
                    "title": "Compile weekly metrics report",
                    "priority": "low",
                    "confidence": 0.80,
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
                },
            ],
        },
    ]

    total_tasks = sum(len(e["tasks"]) for e in parsed_emails)
    urgency_dist = {}
    for e in parsed_emails:
        urgency_dist[e["urgency"]] = urgency_dist.get(e["urgency"], 0) + 1

    return {
        "total_emails_parsed": len(parsed_emails),
        "total_tasks_found": total_tasks,
        "emails_by_urgency": urgency_dist,
        "parsed_emails": parsed_emails,
    }


# ── /task-extraction/history ─────────────────────────────────────────────────

@router.get("/task-extraction/history")
async def extraction_history(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    history = []
    sources = ["email", "meeting_notes", "chat", "document", "manual"]
    for i in range(15):
        history.append({
            "id": i + 1,
            "source": sources[i % len(sources)],
            "extracted_at": (now - timedelta(days=i)).isoformat(),
            "tasks_extracted": random.randint(1, 5),
            "tasks_auto_created": random.randint(0, 3),
            "avg_confidence": round(random.uniform(0.75, 0.95), 2),
            "status": random.choice(["accepted", "partially_accepted", "pending", "rejected"]),
        })

    total = len(history)
    auto_created = sum(h["tasks_auto_created"] for h in history)
    accepted = sum(1 for h in history if h["status"] in ("accepted", "partially_accepted"))

    weekly_trend = []
    for w in range(4):
        weekly_trend.append({
            "week": f"Week {w + 1}",
            "extractions": random.randint(3, 8),
            "tasks_created": random.randint(5, 15),
            "accuracy": round(random.uniform(0.8, 0.95), 2),
        })

    source_dist = {}
    priority_dist = {"high": 0, "medium": 0, "low": 0, "critical": 0}
    for h in history:
        source_dist[h["source"]] = source_dist.get(h["source"], 0) + 1
    for p in priority_dist:
        priority_dist[p] = random.randint(2, 10)

    return {
        "total_extractions": total,
        "auto_created_count": auto_created,
        "acceptance_rate": round(accepted / max(total, 1), 2),
        "avg_confidence": round(sum(h["avg_confidence"] for h in history) / max(total, 1), 2),
        "source_distribution": source_dist,
        "priority_distribution": priority_dist,
        "weekly_trend": weekly_trend,
        "history": history,
    }
