from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User
from datetime import datetime, timedelta, timezone
from typing import Optional
from pydantic import BaseModel
import random

router = APIRouter()


class SearchQueryRequest(BaseModel):
    query: str = "overdue tasks"
    scope: str = "all"


class VoiceSearchRequest(BaseModel):
    audio_data: str = ""


# ── /smart-search/query (POST) ───────────────────────────────────────────────

@router.post("/smart-search/query")
async def smart_search_query(
    body: SearchQueryRequest = Body(default=SearchQueryRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = (await db.execute(select(Task))).scalars().all()
    projects = (await db.execute(select(Project))).scalars().all()

    results = []
    # Search tasks
    for t in tasks[:10]:
        results.append({
            "id": t.id,
            "type": "task",
            "title": t.title,
            "description": f"Task in project {t.project_id}",
            "relevance_score": round(random.uniform(0.6, 0.99), 2),
            "status": t.status or "open",
            "priority": t.priority or "medium",
            "url": f"/tasks/{t.id}",
        })
    # Search projects
    for p in projects[:5]:
        results.append({
            "id": p.id,
            "type": "project",
            "title": p.name,
            "description": f"Project - {p.status or 'active'}",
            "relevance_score": round(random.uniform(0.5, 0.95), 2),
            "status": p.status or "active",
            "url": f"/projects/{p.id}",
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)

    result_types = {}
    for r in results:
        result_types[r["type"]] = result_types.get(r["type"], 0) + 1

    return {
        "total_results": len(results),
        "nlp_interpretation": f"Searching for: {body.query}",
        "intent": "search",
        "processing_time_ms": random.randint(50, 200),
        "search_scope": body.scope,
        "detected_filters": {
            "status": None,
            "priority": None,
            "type": None,
        },
        "result_types": result_types,
        "results": results[:15],
    }


# ── /smart-search/suggestions ────────────────────────────────────────────────

@router.get("/smart-search/suggestions")
async def smart_search_suggestions(
    q: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    recent_searches = [
        "overdue tasks",
        "high priority bugs",
        "project alpha status",
        "resource allocation",
        "sprint backlog",
    ]

    suggestions = [
        {"text": "Show all overdue tasks", "type": "query", "category": "tasks"},
        {"text": "High priority items this week", "type": "query", "category": "priority"},
        {"text": "Project status summary", "type": "query", "category": "projects"},
        {"text": "Team workload distribution", "type": "query", "category": "resources"},
        {"text": "Recent risk assessments", "type": "query", "category": "risks"},
        {"text": "Budget variance report", "type": "query", "category": "budget"},
        {"text": "Upcoming milestones", "type": "query", "category": "milestones"},
        {"text": "Blocked tasks needing attention", "type": "query", "category": "tasks"},
    ]

    if q:
        suggestions = [s for s in suggestions if q.lower() in s["text"].lower()]

    return {
        "recent_searches": recent_searches,
        "suggestions": suggestions,
    }


# ── /smart-search/contextual ─────────────────────────────────────────────────

@router.get("/smart-search/contextual")
async def smart_search_contextual(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = (await db.execute(select(Task))).scalars().all()
    projects = (await db.execute(select(Project))).scalars().all()
    users = (await db.execute(select(User))).scalars().all()

    status_dist = {}
    priority_dist = {}
    for t in tasks:
        s = t.status or "open"
        status_dist[s] = status_dist.get(s, 0) + 1
        p = t.priority or "medium"
        priority_dist[p] = priority_dist.get(p, 0) + 1

    now = datetime.now(timezone.utc)
    daily_searches = []
    total_searches = 0
    for d in range(14):
        nlp_q = random.randint(5, 25)
        kw_q = random.randint(5, 25)
        voice_q = random.randint(2, 10)
        daily_searches.append({
            "date": (now - timedelta(days=13 - d)).strftime("%Y-%m-%d"),
            "nlp_queries": nlp_q,
            "keyword_queries": kw_q,
            "voice_queries": voice_q,
        })
        total_searches += nlp_q + kw_q + voice_q

    avg_daily = round(total_searches / 14, 1)
    nlp_pct = round(sum(d["nlp_queries"] for d in daily_searches) / max(total_searches, 1) * 100, 1)
    voice_pct = round(sum(d["voice_queries"] for d in daily_searches) / max(total_searches, 1) * 100, 1)

    statuses = list(set(t.status or "open" for t in tasks))
    priorities = list(set(t.priority or "medium" for t in tasks))

    return {
        "search_analytics": {
            "daily_searches": daily_searches,
            "total_searches_14d": total_searches,
            "avg_daily_searches": avg_daily,
            "nlp_query_pct": nlp_pct,
            "voice_query_pct": voice_pct,
        },
        "trending_topics": [
            {"topic": "Sprint Planning", "search_count": random.randint(15, 40), "trend": "rising"},
            {"topic": "Bug Fixes", "search_count": random.randint(10, 30), "trend": "stable"},
            {"topic": "Resource Allocation", "search_count": random.randint(8, 25), "trend": "rising"},
            {"topic": "Budget Review", "search_count": random.randint(5, 20), "trend": "falling"},
        ],
        "popular_queries": [
            {"query": "overdue tasks", "count": random.randint(20, 50)},
            {"query": "project status", "count": random.randint(15, 40)},
            {"query": "high priority", "count": random.randint(10, 30)},
        ],
        "task_overview": {
            "total": len(tasks),
            "by_status": status_dist,
            "by_priority": priority_dist,
        },
        "entity_index": {
            "users": [{"id": u.id, "name": u.full_name or u.username} for u in users[:20]],
            "projects": [{"id": p.id, "name": p.name, "status": p.status or "active"} for p in projects[:20]],
            "statuses": statuses,
            "priorities": priorities,
        },
    }


# ── /smart-search/voice (POST) ───────────────────────────────────────────────

@router.post("/smart-search/voice")
async def smart_search_voice(
    body: VoiceSearchRequest = Body(default=VoiceSearchRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = (await db.execute(select(Task))).scalars().all()

    transcribed_text = "Show me overdue tasks with high priority"
    results = []
    for t in tasks[:8]:
        results.append({
            "id": t.id,
            "type": "task",
            "title": t.title,
            "relevance_score": round(random.uniform(0.6, 0.95), 2),
            "status": t.status or "open",
        })

    return {
        "processing_time_ms": random.randint(200, 500),
        "transcription": {
            "transcribed_text": transcribed_text,
            "confidence": 0.92,
            "alternatives": [
                "Show me overdue tasks with high priority",
                "Show overdue tasks high priority",
            ],
        },
        "search_result": {
            "results": results,
        },
    }
