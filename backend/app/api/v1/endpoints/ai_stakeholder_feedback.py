from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import Optional
import random

router = APIRouter()


class TextMiningRequest(BaseModel):
    project_id: Optional[int] = None


class ActionItemsRequest(BaseModel):
    project_id: Optional[int] = None


# ── /stakeholder-feedback/surveys ────────────────────────────────────────────

@router.get("/stakeholder-feedback/surveys")
async def stakeholder_surveys(
    project_id: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = (await db.execute(select(Project))).scalars().all()
    now = datetime.now(timezone.utc)

    surveys = []
    for i, p in enumerate(projects[:8]):
        rating = round(random.uniform(3.0, 4.8), 1)
        surveys.append({
            "id": i + 1,
            "project_id": p.id,
            "project_name": p.name,
            "respondent": f"Stakeholder {i + 1}",
            "role": random.choice(["Executive Sponsor", "Business Owner", "Client Rep", "Board Member"]),
            "rating": rating,
            "satisfaction": "satisfied" if rating >= 4 else "neutral" if rating >= 3 else "dissatisfied",
            "feedback": f"Good progress on {p.name}. Some concerns about timeline.",
            "date": (now - timedelta(days=i * 5)).isoformat(),
            "categories": {
                "communication": round(random.uniform(3, 5), 1),
                "quality": round(random.uniform(3, 5), 1),
                "timeliness": round(random.uniform(2.5, 4.8), 1),
                "value": round(random.uniform(3, 5), 1),
            },
        })

    avg_rating = round(sum(s["rating"] for s in surveys) / max(len(surveys), 1), 1)
    categories = ["communication", "quality", "timeliness", "value"]
    cat_breakdown = []
    for c in categories:
        cat_breakdown.append({
            "category": c,
            "avg_rating": round(sum(s["categories"][c] for s in surveys) / max(len(surveys), 1), 1),
            "response_count": len(surveys),
        })

    weekly_trend = []
    for w in range(8):
        weekly_trend.append({
            "week": (now - timedelta(weeks=7 - w)).strftime("%Y-W%W"),
            "avg_rating": round(random.uniform(3.2, 4.5), 1),
            "responses": random.randint(3, 10),
        })

    # NPS calculation
    promoters = sum(1 for s in surveys if s["rating"] >= 4.5)
    detractors = sum(1 for s in surveys if s["rating"] < 3.0)

    return {
        "total_surveys": len(surveys),
        "avg_rating": avg_rating,
        "response_rate": round(random.uniform(0.65, 0.9), 2),
        "nps_score": round((promoters - detractors) / max(len(surveys), 1) * 100, 1),
        "category_breakdown": cat_breakdown,
        "weekly_trend": weekly_trend,
        "surveys": surveys,
    }


# ── /stakeholder-feedback/text-mining (POST) ─────────────────────────────────

@router.post("/stakeholder-feedback/text-mining")
async def stakeholder_text_mining(
    body: TextMiningRequest = Body(default=TextMiningRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = (await db.execute(select(Project))).scalars().all()
    users = (await db.execute(select(User))).scalars().all()

    comments_raw = [
        ("Great communication from the team", "positive", ["communication", "team"]),
        ("Timeline is slipping, need more resources", "negative", ["timeline", "resources"]),
        ("Quality of deliverables has been excellent", "positive", ["quality", "deliverables"]),
        ("Budget concerns need to be addressed soon", "negative", ["budget", "concerns"]),
        ("Overall satisfied with progress", "positive", ["progress", "satisfaction"]),
        ("Meeting cadence is good but agendas need work", "neutral", ["meetings", "communication"]),
        ("Tests are thorough, documentation could improve", "neutral", ["testing", "documentation"]),
        ("Impressed by the team's problem-solving", "positive", ["team", "problem-solving"]),
    ]

    analyzed = []
    sentiments = {"positive": 0, "negative": 0, "neutral": 0}
    keyword_count = {}
    topics = {}

    for i, (text, sentiment, keywords) in enumerate(comments_raw):
        sentiments[sentiment] += 1
        for kw in keywords:
            keyword_count[kw] = keyword_count.get(kw, 0) + 1
            topics[kw] = topics.get(kw, {"positive": 0, "negative": 0, "neutral": 0})
            topics[kw][sentiment] += 1
        author = users[i % len(users)] if users else None
        project = projects[i % len(projects)] if projects else None
        analyzed.append({
            "id": i + 1,
            "text": text,
            "sentiment": sentiment,
            "sentiment_score": round(random.uniform(0.6, 0.95), 2) if sentiment == "positive" else round(random.uniform(0.3, 0.5), 2) if sentiment == "negative" else 0.5,
            "topics": keywords,
            "author": (author.full_name or author.username) if author else "Unknown",
            "project": project.name if project else "General",
        })

    total = len(analyzed)

    topic_analysis = []
    for t, v in sorted(topics.items(), key=lambda x: sum(x[1].values()), reverse=True):
        mention_count = sum(v.values())
        pos = v.get("positive", 0)
        neg = v.get("negative", 0)
        avg_sent = round((pos - neg) / max(mention_count, 1), 2)
        label = "positive" if avg_sent > 0.2 else "negative" if avg_sent < -0.2 else "neutral"
        topic_analysis.append({
            "topic": t,
            "mention_count": mention_count,
            "avg_sentiment": avg_sent,
            "sentiment_label": label,
        })

    top_keywords = [
        {"word": k, "count": v}
        for k, v in sorted(keyword_count.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    return {
        "total_comments": total,
        "overall_sentiment_score": round(sentiments["positive"] / max(total, 1), 2),
        "sentiment_distribution": sentiments,
        "topic_analysis": topic_analysis,
        "top_keywords": top_keywords,
        "analyzed_comments": analyzed,
    }


# ── /stakeholder-feedback/satisfaction-trends ────────────────────────────────

@router.get("/stakeholder-feedback/satisfaction-trends")
async def stakeholder_satisfaction_trends(
    months: Optional[int] = Query(6),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = (await db.execute(select(Project))).scalars().all()
    now = datetime.now(timezone.utc)

    dimensions = ["communication", "quality", "timeliness", "value", "responsiveness"]
    dimension_summary = []
    for d in dimensions:
        dimension_summary.append({
            "dimension": d,
            "current_score": round(random.uniform(3.5, 4.7), 1),
            "previous_score": round(random.uniform(3.3, 4.5), 1),
            "change": round(random.uniform(-0.3, 0.5), 2),
            "trend": random.choice(["improving", "stable", "declining"]),
        })

    weekly_trends = []
    for w in range(months * 4):
        entry = {
            "week": (now - timedelta(weeks=months * 4 - 1 - w)).strftime("%Y-W%W"),
            "overall": round(random.uniform(3.4, 4.5), 1),
        }
        for d in dimensions:
            entry[d] = round(random.uniform(3.2, 4.6), 1)
        weekly_trends.append(entry)

    project_satisfaction = []
    for p in projects[:8]:
        project_satisfaction.append({
            "project_id": p.id,
            "project_name": p.name,
            "current_score": round(random.uniform(3.3, 4.8), 1),
            "trend": random.choice(["improving", "stable", "declining"]),
            "response_count": random.randint(5, 20),
        })

    stakeholder_segments = [
        {"segment": "Executive Sponsors", "avg_score": round(random.uniform(3.8, 4.6), 1), "count": random.randint(3, 8)},
        {"segment": "Business Owners", "avg_score": round(random.uniform(3.5, 4.5), 1), "count": random.randint(5, 12)},
        {"segment": "Client Representatives", "avg_score": round(random.uniform(3.3, 4.4), 1), "count": random.randint(4, 10)},
        {"segment": "End Users", "avg_score": round(random.uniform(3.4, 4.3), 1), "count": random.randint(8, 20)},
    ]

    return {
        "avg_satisfaction": round(random.uniform(3.6, 4.3), 1),
        "total_responses": random.randint(40, 80),
        "response_rate": round(random.uniform(0.65, 0.85), 2),
        "period_months": months,
        "dimension_summary": dimension_summary,
        "weekly_trends": weekly_trends,
        "project_satisfaction": project_satisfaction,
        "stakeholder_segments": stakeholder_segments,
    }


# ── /stakeholder-feedback/action-items (POST) ────────────────────────────────

@router.post("/stakeholder-feedback/action-items")
async def stakeholder_action_items(
    body: ActionItemsRequest = Body(default=ActionItemsRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    action_items = [
        {
            "id": 1,
            "feedback_source": "Q3 Stakeholder Survey",
            "source_type": "survey",
            "action": "Improve weekly status report format",
            "category": "communication",
            "priority": "high",
            "assignee": "Project Manager",
            "status": "in_progress",
            "due_date": (now + timedelta(days=7)).isoformat(),
            "impact_score": 8.5,
        },
        {
            "id": 2,
            "feedback_source": "Client Meeting Notes",
            "source_type": "meeting",
            "action": "Add more visual dashboards for stakeholders",
            "category": "quality",
            "priority": "medium",
            "assignee": "UX Designer",
            "status": "open",
            "due_date": (now + timedelta(days=14)).isoformat(),
            "impact_score": 7.2,
        },
        {
            "id": 3,
            "feedback_source": "Executive Review",
            "source_type": "review",
            "action": "Develop risk escalation protocol",
            "category": "process",
            "priority": "critical",
            "assignee": "PMO Lead",
            "status": "open",
            "due_date": (now + timedelta(days=5)).isoformat(),
            "impact_score": 9.1,
        },
        {
            "id": 4,
            "feedback_source": "Team Retrospective",
            "source_type": "retrospective",
            "action": "Streamline approval workflow",
            "category": "process",
            "priority": "medium",
            "assignee": "Process Engineer",
            "status": "completed",
            "due_date": (now - timedelta(days=3)).isoformat(),
            "impact_score": 6.5,
        },
        {
            "id": 5,
            "feedback_source": "User Feedback Portal",
            "source_type": "portal",
            "action": "Enhance mobile notification system",
            "category": "technology",
            "priority": "low",
            "assignee": "Mobile Dev Lead",
            "status": "open",
            "due_date": (now + timedelta(days=21)).isoformat(),
            "impact_score": 5.8,
        },
        {
            "id": 6,
            "feedback_source": "Board Meeting",
            "source_type": "meeting",
            "action": "Prepare quarterly ROI analysis",
            "category": "reporting",
            "priority": "high",
            "assignee": "Finance Analyst",
            "status": "overdue",
            "due_date": (now - timedelta(days=2)).isoformat(),
            "impact_score": 8.0,
        },
    ]

    cat_breakdown = {}
    status_breakdown = {"open": 0, "in_progress": 0, "completed": 0, "overdue": 0}
    pri_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for ai in action_items:
        cat_breakdown[ai["category"]] = cat_breakdown.get(ai["category"], 0) + 1
        status_breakdown[ai["status"]] = status_breakdown.get(ai["status"], 0) + 1
        pri_breakdown[ai["priority"]] = pri_breakdown.get(ai["priority"], 0) + 1

    completed = status_breakdown.get("completed", 0)
    total = len(action_items)
    overdue = status_breakdown.get("overdue", 0)

    return {
        "total_action_items": total,
        "completion_rate": round(completed / max(total, 1), 2),
        "overdue_count": overdue,
        "category_breakdown": [
            {"category": k, "count": v} for k, v in cat_breakdown.items()
        ],
        "status_breakdown": status_breakdown,
        "priority_breakdown": pri_breakdown,
        "action_items": action_items,
    }
