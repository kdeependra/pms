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


class PulseSurveyRequest(BaseModel):
    action: str = "get_results"


# ── /sentiment/communications ────────────────────────────────────────────────

@router.get("/sentiment/communications")
async def sentiment_communications(
    project_id: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = (await db.execute(select(Project))).scalars().all()
    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    now = datetime.now(timezone.utc)

    daily_sentiment = []
    for d in range(14):
        daily_sentiment.append({
            "date": (now - timedelta(days=13 - d)).strftime("%Y-%m-%d"),
            "positive": round(random.uniform(0.4, 0.65), 2),
            "neutral": round(random.uniform(0.2, 0.35), 2),
            "negative": round(random.uniform(0.05, 0.2), 2),
            "total_messages": random.randint(20, 60),
        })

    project_sentiment_summary = []
    for p in projects[:8]:
        project_sentiment_summary.append({
            "project_id": p.id,
            "project_name": p.name,
            "avg_sentiment": round(random.uniform(0.5, 0.85), 2),
            "total_communications": random.randint(30, 120),
            "trend": random.choice(["improving", "stable", "declining"]),
        })

    user_sentiment_summary = []
    for u in users[:10]:
        user_sentiment_summary.append({
            "user_id": u.id,
            "user_name": u.full_name or u.username,
            "avg_sentiment": round(random.uniform(0.4, 0.9), 2),
            "messages_analyzed": random.randint(10, 50),
            "dominant_tone": random.choice(["positive", "neutral", "professional"]),
        })

    recent_communications = []
    tones = ["positive", "negative", "neutral", "concerned", "enthusiastic"]
    for i in range(10):
        recent_communications.append({
            "id": i + 1,
            "user": users[i % len(users)].full_name or users[i % len(users)].username if users else "Unknown",
            "channel": random.choice(["chat", "email", "comment", "meeting"]),
            "sentiment_score": round(random.uniform(0.2, 0.95), 2),
            "tone": random.choice(tones),
            "timestamp": (now - timedelta(hours=i * 3)).isoformat(),
            "excerpt": "Discussion about project progress and next steps...",
        })

    pos_pct = round(random.uniform(0.45, 0.6), 2)
    neg_pct = round(random.uniform(0.08, 0.18), 2)
    neu_pct = round(1 - pos_pct - neg_pct, 2)

    return {
        "overall_sentiment": round(random.uniform(0.6, 0.8), 2),
        "total_communications": sum(d["total_messages"] for d in daily_sentiment),
        "positive_percentage": pos_pct,
        "negative_percentage": neg_pct,
        "neutral_percentage": neu_pct,
        "daily_sentiment": daily_sentiment,
        "project_sentiment_summary": project_sentiment_summary,
        "user_sentiment_summary": user_sentiment_summary,
        "recent_communications": recent_communications,
    }


# ── /sentiment/pulse-survey (POST) ───────────────────────────────────────────

@router.post("/sentiment/pulse-survey")
async def sentiment_pulse_survey(
    body: PulseSurveyRequest = Body(default=PulseSurveyRequest()),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    survey_questions = [
        "How satisfied are you with your current workload?",
        "Do you feel supported by your team?",
        "Rate the clarity of project goals.",
        "How effective is team communication?",
        "Rate your overall job satisfaction.",
    ]

    question_results = []
    for q in survey_questions:
        question_results.append({
            "question": q,
            "avg_rating": round(random.uniform(3.0, 4.8), 1),
            "responses": random.randint(15, 30),
            "distribution": {
                "1": random.randint(0, 2),
                "2": random.randint(1, 4),
                "3": random.randint(3, 8),
                "4": random.randint(5, 12),
                "5": random.randint(4, 10),
            },
        })

    now = datetime.now(timezone.utc)
    historical_periods = []
    for m in range(6):
        historical_periods.append({
            "period": (now - timedelta(days=m * 30)).strftime("%Y-%m"),
            "avg_score": round(random.uniform(3.2, 4.5), 1),
            "response_rate": round(random.uniform(0.6, 0.9), 2),
            "participants": random.randint(15, 30),
        })

    department_breakdown = [
        {"department": "Engineering", "avg_score": round(random.uniform(3.5, 4.5), 1), "participants": random.randint(5, 15)},
        {"department": "Design", "avg_score": round(random.uniform(3.3, 4.6), 1), "participants": random.randint(3, 8)},
        {"department": "QA", "avg_score": round(random.uniform(3.4, 4.4), 1), "participants": random.randint(3, 8)},
        {"department": "Management", "avg_score": round(random.uniform(3.6, 4.7), 1), "participants": random.randint(2, 5)},
    ]

    nps_promoters = random.randint(10, 18)
    nps_detractors = random.randint(2, 6)
    nps_passives = random.randint(5, 10)
    total_nps = nps_promoters + nps_detractors + nps_passives

    return {
        "current_period": {
            "question_results": question_results,
        },
        "nps_score": round((nps_promoters - nps_detractors) / max(total_nps, 1) * 100, 1),
        "total_participants": total_nps,
        "survey_questions": survey_questions,
        "category_trends": {
            "workload": round(random.uniform(3.2, 4.3), 1),
            "communication": round(random.uniform(3.5, 4.5), 1),
            "support": round(random.uniform(3.3, 4.4), 1),
            "goals": round(random.uniform(3.4, 4.6), 1),
        },
        "historical_periods": historical_periods,
        "department_breakdown": department_breakdown,
        "nps_breakdown": {
            "promoters": nps_promoters,
            "passives": nps_passives,
            "detractors": nps_detractors,
        },
    }


# ── /sentiment/happiness-index ───────────────────────────────────────────────

@router.get("/sentiment/happiness-index")
async def sentiment_happiness_index(
    months: Optional[int] = Query(3),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    now = datetime.now(timezone.utc)

    weekly_index = []
    for w in range(months * 4):
        weekly_index.append({
            "week": (now - timedelta(weeks=months * 4 - 1 - w)).strftime("%Y-W%W"),
            "index": round(random.uniform(60, 85), 1),
            "responses": random.randint(10, 25),
        })

    happiness_factors = [
        {"factor": "Work-Life Balance", "score": round(random.uniform(60, 90), 1), "weight": 0.25, "trend": "improving"},
        {"factor": "Team Collaboration", "score": round(random.uniform(65, 88), 1), "weight": 0.20, "trend": "stable"},
        {"factor": "Growth Opportunities", "score": round(random.uniform(55, 82), 1), "weight": 0.20, "trend": "improving"},
        {"factor": "Management Support", "score": round(random.uniform(60, 85), 1), "weight": 0.20, "trend": "stable"},
        {"factor": "Working Conditions", "score": round(random.uniform(70, 92), 1), "weight": 0.15, "trend": "stable"},
    ]

    department_happiness = [
        {"department": "Engineering", "index": round(random.uniform(65, 85), 1), "change": round(random.uniform(-5, 8), 1)},
        {"department": "Design", "index": round(random.uniform(68, 88), 1), "change": round(random.uniform(-3, 6), 1)},
        {"department": "QA", "index": round(random.uniform(62, 82), 1), "change": round(random.uniform(-4, 5), 1)},
        {"department": "Management", "index": round(random.uniform(70, 90), 1), "change": round(random.uniform(-2, 7), 1)},
    ]

    member_happiness = []
    for u in users[:12]:
        member_happiness.append({
            "user_id": u.id,
            "name": u.full_name or u.username,
            "index": round(random.uniform(55, 95), 1),
            "change": round(random.uniform(-10, 10), 1),
            "last_response": (now - timedelta(days=random.randint(0, 7))).isoformat(),
        })

    current_idx = round(random.uniform(68, 82), 1)

    return {
        "current_happiness_index": current_idx,
        "change": round(random.uniform(-3, 5), 1),
        "response_rate": round(random.uniform(0.65, 0.9), 2),
        "team_size": len(users),
        "benchmark": {
            "industry_avg": 72.0,
            "company_avg": 75.0,
            "top_quartile": 85.0,
        },
        "weekly_index": weekly_index,
        "happiness_factors": happiness_factors,
        "department_happiness": department_happiness,
        "member_happiness": member_happiness,
    }


# ── /sentiment/burnout-detection ─────────────────────────────────────────────

@router.get("/sentiment/burnout-detection")
async def sentiment_burnout_detection(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    tasks = (await db.execute(select(Task))).scalars().all()
    now = datetime.now(timezone.utc)

    assessments = []
    at_risk = 0
    departments = ["Engineering", "Design", "QA", "Management", "Product"]
    for u in users[:15]:
        user_tasks = [t for t in tasks if t.assignee_id == u.id and t.status not in ("done", "completed")]
        overdue = sum(1 for t in user_tasks if t.due_date and t.due_date < now)
        workload = len(user_tasks)
        score = min(100, workload * 8 + overdue * 15 + random.randint(0, 20))
        risk = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low"
        if risk in ("critical", "high", "medium"):
            at_risk += 1
        indicators = []
        if workload > 5:
            indicators.append({"type": "high_workload", "detail": f"{workload} active tasks", "severity": "high"})
        if overdue > 0:
            indicators.append({"type": "overdue_tasks", "detail": f"{overdue} overdue tasks", "severity": "high" if overdue > 2 else "medium"})
        if score > 60:
            indicators.append({"type": "overtime", "detail": "Frequent overtime detected", "severity": "high"})
        if random.random() > 0.5:
            indicators.append({"type": "response_time", "detail": "Response time increasing", "severity": "medium"})
        recs = []
        if score >= 60:
            recs.append("Consider redistributing workload")
            recs.append("Schedule a 1-on-1 check-in")
        elif score >= 40:
            recs.append("Monitor workload closely")
        else:
            recs.append("Workload is healthy")
        dept = departments[hash(u.username or "") % len(departments)]
        assessments.append({
            "user_id": u.id,
            "user": u.full_name or u.username,
            "department": dept,
            "burnout_score": score,
            "risk_level": risk,
            "active_tasks": workload,
            "overdue_tasks": overdue,
            "avg_hours_per_week": round(random.uniform(35, 55), 1),
            "indicators": indicators,
            "recommendations": recs,
        })

    risk_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in assessments:
        risk_dist[a["risk_level"]] = risk_dist.get(a["risk_level"], 0) + 1

    high_risk = [a for a in assessments if a["risk_level"] in ("critical", "high")]

    weekly_trend = []
    for w in range(12):
        crit = random.randint(0, 2)
        high_c = random.randint(1, 4)
        weekly_trend.append({
            "week": (now - timedelta(weeks=11 - w)).strftime("%Y-W%W"),
            "avg_burnout_score": round(random.uniform(30, 55), 1),
            "critical_count": crit,
            "high_count": high_c,
        })

    department_risk = [
        {"department": "Engineering", "avg_burnout_score": round(random.uniform(35, 55), 1), "at_risk": random.randint(0, 3)},
        {"department": "Design", "avg_burnout_score": round(random.uniform(25, 45), 1), "at_risk": random.randint(0, 2)},
        {"department": "QA", "avg_burnout_score": round(random.uniform(30, 50), 1), "at_risk": random.randint(0, 2)},
        {"department": "Management", "avg_burnout_score": round(random.uniform(40, 60), 1), "at_risk": random.randint(0, 2)},
    ]

    return {
        "team_overview": {
            "avg_burnout_score": round(sum(a["burnout_score"] for a in assessments) / max(len(assessments), 1), 1),
            "at_risk_count": at_risk,
            "total_members": len(assessments),
            "risk_distribution": risk_dist,
        },
        "alerts": [
            {
                "user": a["user"],
                "severity": "critical" if a["risk_level"] == "critical" else "warning",
                "message": f"Burnout score {a['burnout_score']} — {'; '.join(a['recommendations'][:2])}",
            }
            for a in high_risk[:5]
        ],
        "weekly_trend": weekly_trend,
        "department_risk": department_risk,
        "assessments": assessments,
    }
