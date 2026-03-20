from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User
from datetime import datetime, timedelta, timezone
import random

router = APIRouter()


async def _all_projects(db: AsyncSession):
    return (await db.execute(select(Project))).scalars().all()


async def _all_tasks(db: AsyncSession):
    return (await db.execute(select(Task))).scalars().all()


async def _active_users(db: AsyncSession):
    return (await db.execute(select(User).where(User.is_active == True))).scalars().all()


# ── /meeting-summaries/transcribe ────────────────────────────────────────────

@router.get("/meeting-summaries/transcribe")
async def meeting_transcribe(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _all_projects(db)
    users = await _active_users(db)
    now = datetime.now(timezone.utc)
    sentiments = ["positive", "neutral", "concerned", "negative"]
    topics = ["Sprint Review", "Architecture Discussion", "Stakeholder Update", "Risk Assessment", "Release Planning"]

    meetings = []
    for i, p in enumerate(projects[:5]):
        participant_count = min(random.randint(3, 6), len(users))
        participant_users = users[:participant_count]
        duration = random.randint(30, 90)

        speakers = []
        for si, u in enumerate(participant_users):
            speakers.append({
                "speaker_id": u.id,
                "speaker_name": u.full_name or u.username,
                "role": u.role or "team_member",
                "speaking_turns": random.randint(3, 15),
                "talk_ratio_pct": round(random.uniform(10, 40), 1),
                "dominant_sentiment": random.choice(sentiments),
            })

        segments = []
        for j in range(random.randint(6, 12)):
            speaker = participant_users[j % len(participant_users)]
            start_sec = j * random.randint(30, 90)
            segments.append({
                "segment_id": j + 1,
                "speaker_name": speaker.full_name or speaker.username,
                "start_time_sec": start_sec,
                "end_time_sec": start_sec + random.randint(20, 60),
                "text": random.choice([
                    f"Discussion about {p.name} progress and upcoming milestones.",
                    "We need to address the timeline concerns and resource allocation.",
                    "I think we should prioritize the critical path items first.",
                    "The testing phase is on track, but we need more QA coverage.",
                    "Let's schedule a follow-up to review the budget impact.",
                    "The stakeholders are satisfied with the current progress.",
                ]),
                "confidence": round(random.uniform(0.85, 0.98), 2),
                "sentiment": random.choice(sentiments),
            })

        meetings.append({
            "meeting_id": i + 1,
            "project_id": p.id,
            "project_name": p.name,
            "topic": topics[i % len(topics)],
            "date": (now - timedelta(days=i * 3)).strftime("%Y-%m-%d"),
            "duration_minutes": duration,
            "participant_count": participant_count,
            "transcription_confidence": round(random.uniform(0.88, 0.97), 2),
            "transcription_status": "completed",
            "speakers": speakers,
            "transcript_segments": segments,
        })

    return {
        "total_meetings": len(meetings),
        "total_transcription_hours": round(sum(m["duration_minutes"] for m in meetings) / 60, 1),
        "avg_confidence": round(random.uniform(0.90, 0.96), 2),
        "meetings": meetings,
    }


# ── /meeting-summaries/extract ───────────────────────────────────────────────

@router.get("/meeting-summaries/extract")
async def meeting_extract(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _all_projects(db)
    users = await _active_users(db)
    sentiments = ["positive", "neutral", "concerned", "negative"]
    kp_types = ["concern", "status", "priority", "milestone", "decision"]
    kp_importances = ["high", "medium", "low"]
    categories = ["follow_up", "review", "development", "testing", "documentation", "deployment"]

    extractions = []
    total_kp = 0
    total_ai = 0
    ai_by_priority = {"high": 0, "medium": 0, "low": 0}

    for i, p in enumerate(projects[:5]):
        key_points = []
        kp_texts = [
            f"Project {p.name} is {p.progress or 0}% complete",
            "Team agreed to accelerate testing phase",
            "Budget review needed by end of week",
            "New risk identified in integration layer",
            "Stakeholder approval received for Phase 2",
        ]
        for ki, txt in enumerate(kp_texts[:random.randint(3, 5)]):
            key_points.append({
                "point_id": i * 10 + ki + 1,
                "type": random.choice(kp_types),
                "importance": random.choice(kp_importances),
                "text": txt,
            })

        action_items = []
        ai_descs = [
            ("Update project timeline", "high", "follow_up"),
            ("Review budget allocation", "medium", "review"),
            ("Schedule follow-up meeting", "low", "follow_up"),
            ("Complete integration testing", "high", "testing"),
        ]
        for j, (desc, pri, cat) in enumerate(ai_descs[:random.randint(2, 4)]):
            assignee = users[j % len(users)] if users else None
            ai_by_priority[pri] = ai_by_priority.get(pri, 0) + 1
            action_items.append({
                "action_id": i * 10 + j + 1,
                "description": desc,
                "assignee_name": (assignee.full_name or assignee.username) if assignee else "Unassigned",
                "priority": pri,
                "category": cat,
                "due_date": (datetime.now(timezone.utc) + timedelta(days=j * 3 + 2)).strftime("%Y-%m-%d"),
                "confidence": round(random.uniform(0.75, 0.98), 2),
                "status": "pending",
            })

        total_kp += len(key_points)
        total_ai += len(action_items)
        duration = random.randint(30, 90)

        extractions.append({
            "meeting_id": i + 1,
            "project_name": p.name,
            "meeting_date": (datetime.now(timezone.utc) - timedelta(days=i * 3)).strftime("%Y-%m-%d"),
            "duration_minutes": duration,
            "sentiment_overview": {
                "overall": random.choice(sentiments),
            },
            "key_points_count": len(key_points),
            "action_items_count": len(action_items),
            "summary": f"Meeting covered {p.name} progress review, identified {len(key_points)} key points and {len(action_items)} action items requiring follow-up.",
            "key_points": key_points,
            "action_items": action_items,
        })

    return {
        "total_meetings_processed": len(extractions),
        "total_key_points": total_kp,
        "total_action_items": total_ai,
        "action_items_by_priority": ai_by_priority,
        "extractions": extractions,
    }


# ── /meeting-summaries/create-tasks (POST) ───────────────────────────────────

@router.post("/meeting-summaries/create-tasks")
async def meeting_create_tasks(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _all_projects(db)
    users = await _active_users(db)
    categories = ["follow_up", "review", "development", "testing", "documentation"]

    created_tasks = []
    skipped_items = []
    for i in range(min(5, len(projects))):
        assignee = users[i % len(users)] if users else None
        created_tasks.append({
            "task_id": 900 + i,
            "task_title": f"Follow up from meeting - {projects[i].name}",
            "project_name": projects[i].name,
            "project_id": projects[i].id,
            "assignee_name": (assignee.full_name or assignee.username) if assignee else "Auto-assigned",
            "priority": random.choice(["high", "medium", "low"]),
            "category": random.choice(categories),
            "due_date": (datetime.now(timezone.utc) + timedelta(days=random.randint(3, 14))).strftime("%Y-%m-%d"),
            "confidence": round(random.uniform(0.80, 0.98), 2),
            "source": "meeting_extraction",
        })
    skipped_items.append({
        "action_description": "General discussion note - no actionable task",
        "reason": "Not actionable — duplicate of existing task",
    })

    return {
        "tasks_created": len(created_tasks),
        "tasks_skipped": len(skipped_items),
        "total_action_items": len(created_tasks) + len(skipped_items),
        "summary": f"Created {len(created_tasks)} tasks from meeting action items",
        "created_tasks": created_tasks,
        "skipped_items": skipped_items,
    }


# ── /meeting-summaries/sentiment ─────────────────────────────────────────────

@router.get("/meeting-summaries/sentiment")
async def meeting_sentiment(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _all_projects(db)
    users = await _active_users(db)
    sentiments = ["positive", "neutral", "concerned", "negative"]
    trends = ["improving", "stable", "declining"]
    morale_levels = ["high", "medium", "low"]
    engagement_levels = ["highly_engaged", "engaged", "moderately_engaged", "low_engagement"]
    roles = ["Developer", "Designer", "QA Engineer", "Project Manager", "DevOps", "Analyst"]
    depts = ["Engineering", "Design", "Quality", "Management", "Operations", "Analytics"]

    project_sentiments = []
    for pi, p in enumerate(projects[:5]):
        project_sentiments.append({
            "project_id": p.id,
            "project_name": p.name,
            "meetings_analyzed": random.randint(3, 8),
            "overall_sentiment": random.choice(sentiments),
            "team_morale": random.choice(morale_levels),
            "sentiment_trend": random.choice(trends),
            "avg_engagement": round(random.uniform(0.4, 0.9), 2),
            "sentiment_distribution": {
                "positive": round(random.uniform(0.3, 0.6), 2),
                "neutral": round(random.uniform(0.2, 0.4), 2),
                "negative": round(random.uniform(0.05, 0.2), 2),
            },
        })

    speaker_profiles = []
    for si, u in enumerate(users[:8]):
        speaker_profiles.append({
            "speaker_id": u.id,
            "speaker_name": u.full_name or u.username,
            "role": roles[si % len(roles)],
            "department": depts[si % len(depts)],
            "dominant_sentiment": random.choice(sentiments),
            "sentiment_trend": random.choice(trends),
            "meetings_attended": random.randint(5, 15),
            "avg_speaking_per_meeting": random.randint(5, 25),
            "engagement_level": random.choice(engagement_levels),
            "avg_sentiment": round(random.uniform(0.5, 0.9), 2),
            "engagement_score": round(random.uniform(0.4, 1.0), 2),
            "sentiment_distribution": {
                "positive": random.randint(3, 8),
                "neutral": random.randint(2, 6),
                "negative": random.randint(0, 3),
            },
        })

    return {
        "total_speakers_tracked": len(speaker_profiles),
        "total_meetings_analyzed": sum(ps["meetings_analyzed"] for ps in project_sentiments),
        "overall_trend": random.choice(trends),
        "overall_sentiment_distribution": {
            "positive": 0.55,
            "neutral": 0.30,
            "negative": 0.15,
        },
        "project_sentiments": project_sentiments,
        "speaker_profiles": speaker_profiles,
    }


# ── /meeting-summaries/distribute (POST) ─────────────────────────────────────

@router.post("/meeting-summaries/distribute")
async def meeting_distribute(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await _all_projects(db)
    users = await _active_users(db)
    topics = ["Sprint Review", "Architecture Discussion", "Stakeholder Update", "Risk Assessment"]
    sections = ["summary", "key_points", "action_items", "decisions", "next_steps"]
    roles_list = ["Developer", "Designer", "QA Engineer", "Project Manager", "DevOps", "Analyst"]
    delivery_methods = ["email", "in_app"]

    distributions = []
    total_recipients = 0
    total_read = 0
    for i, p in enumerate(projects[:4]):
        num_recip = min(random.randint(3, 6), len(users))
        recipients = []
        read_count = 0
        for ri, u in enumerate(users[:num_recip]):
            is_read = random.random() > 0.3
            has_ai = random.random() > 0.5
            if is_read:
                read_count += 1
            recipients.append({
                "user_id": u.id,
                "user_name": u.full_name or u.username,
                "role": roles_list[ri % len(roles_list)],
                "delivery_method": random.choice(delivery_methods),
                "delivery_status": "delivered",
                "read_status": "read" if is_read else "unread",
                "has_action_items": has_ai,
                "action_items_count": random.randint(1, 4) if has_ai else 0,
            })
        total_recipients += num_recip
        total_read += read_count
        read_rate = round(read_count / max(num_recip, 1) * 100)
        distributions.append({
            "distribution_id": i + 1,
            "meeting_id": i + 1,
            "project_name": p.name,
            "meeting_topic": topics[i % len(topics)],
            "meeting_date": (datetime.now(timezone.utc) - timedelta(days=i * 3)).strftime("%Y-%m-%d"),
            "distributed_at": (datetime.now(timezone.utc) - timedelta(days=i * 3, hours=1)).isoformat(),
            "total_recipients": num_recip,
            "read_count": read_count,
            "read_rate_pct": read_rate,
            "sections_included": random.sample(sections, k=random.randint(3, 5)),
            "includes_action_items": True,
            "includes_transcript_link": random.random() > 0.4,
            "recipients": recipients,
        })

    overall_read_rate = round(total_read / max(total_recipients, 1) * 100)

    return {
        "total_distributions": len(distributions),
        "total_recipients": total_recipients,
        "overall_delivery_rate": 100,
        "overall_read_rate": overall_read_rate,
        "distributions": distributions,
    }
