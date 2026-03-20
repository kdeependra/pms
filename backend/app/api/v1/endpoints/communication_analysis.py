"""
Communication Analysis Endpoints
Handles email, chat, and message sentiment analysis with conflict detection
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List
import json

from app.core.database import get_db
from app.models.models import (
    CommunicationMessage, CollaborationMetrics, ConflictAlert, User, Project
)
from app.schemas.schemas import (
    CommunicationMessageCreate, CommunicationMessageResponse,
    CommunicationAnalyticsRequest, CommunicationAnalyticsResponse,
    ConflictAlertResponse, CollaborationMetricsResponse,
    ConflictDetectionRequest, ConflictDetectionResponse
)
from ai_services.sentiment_analysis_service import SentimentAnalyzer

router = APIRouter()
sentiment_analyzer = SentimentAnalyzer()


# ==================== Communication Message Endpoints ====================

@router.post("/messages", response_model=CommunicationMessageResponse)
async def submit_communication_message(
    message: CommunicationMessageCreate,
    db: Session = Depends(get_db)
):
    """
    Submit a communication message (email, chat, etc.) for analysis.
    Automatically analyzes sentiment and detects conflicts.
    """
    try:
        # Analyze sentiment
        sentiment_result = sentiment_analyzer.analyze_sentiment(message.content)
        
        # Extract topics and action items
        topics = sentiment_analyzer.extract_key_topics([message.content], top_n=3)
        action_items = sentiment_analyzer.generate_action_items(message.content)
        
        # Detect conflict indicators
        conflict_score = 0.0
        conflict_type = None
        contains_conflict = False
        
        if sentiment_result['sentiment_category'] in ['very_negative', 'negative']:
            conflict_score = 0.7 if 'very_negative' else 0.5
            contains_conflict = True
            conflict_type = "sentiment_based"
        
        # Check for conflict keywords
        conflict_keywords = ['disagree', 'not acceptable', 'unacceptable', 'serious concern', 
                           'major issue', 'critical problem', 'stop', 'delay', 'blocker']
        text_lower = message.content.lower()
        for keyword in conflict_keywords:
            if keyword in text_lower:
                conflict_score = min(1.0, conflict_score + 0.15)
                contains_conflict = True
                conflict_type = "escalation"
        
        # Determine tone
        tone = "professional"
        if "!" in message.content:
            tone = "urgent" if conflict_score > 0.5 else "enthusiastic"
        if "?" in message.content:
            tone = "questioning"
        if sentiment_result['sentiment_category'] == 'very_positive':
            tone = "supportive"
        
        # Create message record
        db_message = CommunicationMessage(
            project_id=message.project_id,
            sender_id=message.sender_id,
            recipient_ids=message.recipient_ids,
            message_type=message.message_type,
            channel=message.channel,
            subject=message.subject,
            content=message.content,
            sentiment_score=sentiment_result['sentiment_score'],
            sentiment_category=sentiment_result['sentiment_category'],
            confidence=sentiment_result['confidence'],
            tone=tone,
            mentions=json.dumps({}),
            key_topics=json.dumps(topics),
            action_items=json.dumps(action_items),
            contains_conflict=contains_conflict,
            conflict_score=conflict_score,
            conflict_type=conflict_type
        )
        
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        # If conflict detected, create alert
        if contains_conflict and conflict_score > 0.6:
            conflict_alert = ConflictAlert(
                project_id=message.project_id,
                severity="high" if conflict_score > 0.8 else "medium",
                type=conflict_type or "concern",
                involved_users=message.recipient_ids.get('users', []) if message.recipient_ids else [],
                message_id=db_message.id,
                confidence_score=conflict_score,
                status="open"
            )
            db.add(conflict_alert)
            db.commit()
        
        return db_message
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error analyzing message: {str(e)}")


@router.get("/messages/{project_id}", response_model=List[CommunicationMessageResponse])
async def get_project_messages(
    project_id: int,
    message_type: Optional[str] = None,
    channel: Optional[str] = None,
    sentiment_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get communication messages for a project with optional filters"""
    query = db.query(CommunicationMessage).filter(
        CommunicationMessage.project_id == project_id
    )
    
    if message_type:
        query = query.filter(CommunicationMessage.message_type == message_type)
    
    if channel:
        query = query.filter(CommunicationMessage.channel == channel)
    
    if sentiment_filter:
        query = query.filter(CommunicationMessage.sentiment_category == sentiment_filter)
    
    messages = query.order_by(CommunicationMessage.created_at.desc()).limit(limit).all()
    return messages


@router.get("/messages/{message_id}/details", response_model=CommunicationMessageResponse)
async def get_message_details(
    message_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific message"""
    message = db.query(CommunicationMessage).filter(
        CommunicationMessage.id == message_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    return message


# ==================== Communication Analytics Endpoints ====================

@router.post("/analytics", response_model=CommunicationAnalyticsResponse)
async def get_communication_analytics(
    request: CommunicationAnalyticsRequest,
    db: Session = Depends(get_db)
):
    """
    Get comprehensive communication analysis for a project
    Including sentiment trends, conflict metrics, and collaboration health
    """
    try:
        # Query messages for the period
        messages = db.query(CommunicationMessage).filter(
            CommunicationMessage.project_id == request.project_id,
            CommunicationMessage.created_at >= request.start_date,
            CommunicationMessage.created_at <= request.end_date
        )
        
        if request.message_type:
            messages = messages.filter(CommunicationMessage.message_type == request.message_type)
        
        if request.channel:
            messages = messages.filter(CommunicationMessage.channel == request.channel)
        
        messages = messages.all()
        
        if not messages:
            return CommunicationAnalyticsResponse(
                project_id=request.project_id,
                period=f"{request.start_date.date()} to {request.end_date.date()}",
                total_messages=0,
                message_breakdown={},
                avg_sentiment=0.0,
                sentiment_distribution={},
                conflict_alerts=0,
                critical_conflicts=0,
                resolved_conflicts=0,
                active_participants=0,
                most_active_users=[],
                top_topics=[],
                avg_response_time=0.0,
                collaboration_score=0.0,
                recommendations=[]
            )
        
        # Calculate metrics
        total_messages = len(messages)
        
        # Message breakdown by type
        message_breakdown = {}
        for msg in messages:
            msg.message_type = msg.message_type or "unknown"
            message_breakdown[msg.message_type] = message_breakdown.get(msg.message_type, 0) + 1
        
        # Sentiment analysis
        sentiments = [msg.sentiment_score for msg in messages if msg.sentiment_score is not None]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
        
        sentiment_distribution = {
            'very_positive': sum(1 for msg in messages if msg.sentiment_category == 'very_positive'),
            'positive': sum(1 for msg in messages if msg.sentiment_category == 'positive'),
            'neutral': sum(1 for msg in messages if msg.sentiment_category == 'neutral'),
            'negative': sum(1 for msg in messages if msg.sentiment_category == 'negative'),
            'very_negative': sum(1 for msg in messages if msg.sentiment_category == 'very_negative')
        }
        
        # Conflict metrics
        conflict_messages = [msg for msg in messages if msg.contains_conflict]
        conflict_alerts_count = db.query(ConflictAlert).filter(
            ConflictAlert.project_id == request.project_id,
            ConflictAlert.created_at >= request.start_date,
            ConflictAlert.created_at <= request.end_date
        ).count()
        
        critical_conflicts = sum(1 for msg in conflict_messages if msg.conflict_score > 0.8)
        
        # Active participants
        senders = set(msg.sender_id for msg in messages)
        active_participants = len(senders)
        
        # Most active users
        sender_counts = {}
        for msg in messages:
            sender_counts[msg.sender_id] = sender_counts.get(msg.sender_id, 0) + 1
        
        most_active_users = []
        for user_id, count in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                most_active_users.append({
                    "user_id": user_id,
                    "user_name": user.full_name or user.username,
                    "message_count": count
                })
        
        # Top topics
        all_topics = {}
        for msg in messages:
            if msg.key_topics:
                try:
                    topics = json.loads(msg.key_topics) if isinstance(msg.key_topics, str) else msg.key_topics
                    for topic in topics:
                        topic_name = topic if isinstance(topic, str) else topic.get('topic', 'unknown')
                        all_topics[topic_name] = all_topics.get(topic_name, 0) + 1
                except:
                    pass
        
        top_topics = [
            {"topic": topic, "count": count, "sentiment": "neutral"}
            for topic, count in sorted(all_topics.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # Response time metrics
        response_times = [msg.response_time_minutes for msg in messages if msg.response_time_minutes]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
        
        # Collaboration score (0-1)
        collaboration_score = min(1.0, (active_participants / 10) * (1 - (conflict_alerts_count / max(total_messages, 1) * 0.5)))
        
        # Recommendations
        recommendations = []
        if conflict_alerts_count > 5:
            recommendations.append(f"High conflict rate detected ({conflict_alerts_count} alerts). Consider team meeting to address tensions.")
        if sentiment_distribution['negative'] + sentiment_distribution['very_negative'] > total_messages * 0.3:
            recommendations.append("Negative sentiment is high. Review recent discussions and provide support.")
        if active_participants < 3:
            recommendations.append(f"Low participation. Only {active_participants} team members are engaged.")
        if collaboration_score < 0.5:
            recommendations.append("Collaboration health is low. Encourage more team interaction.")
        if not recommendations:
            recommendations.append("Team communication is healthy. Continue current collaboration practices.")
        
        return CommunicationAnalyticsResponse(
            project_id=request.project_id,
            period=f"{request.start_date.date()} to {request.end_date.date()}",
            total_messages=total_messages,
            message_breakdown=message_breakdown,
            avg_sentiment=avg_sentiment,
            sentiment_distribution=sentiment_distribution,
            conflict_alerts=conflict_alerts_count,
            critical_conflicts=critical_conflicts,
            resolved_conflicts=db.query(ConflictAlert).filter(
                ConflictAlert.project_id == request.project_id,
                ConflictAlert.status == "resolved"
            ).count(),
            active_participants=active_participants,
            most_active_users=most_active_users,
            top_topics=top_topics,
            avg_response_time=avg_response_time,
            collaboration_score=collaboration_score,
            recommendations=recommendations
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating analytics: {str(e)}")


# ==================== Conflict Detection Endpoints ====================

@router.post("/detect-conflict", response_model=ConflictDetectionResponse)
async def detect_conflict(
    request: ConflictDetectionRequest,
    db: Session = Depends(get_db)
):
    """
    Analyze a message for potential conflicts and escalation risks
    """
    try:
        sentiment_result = sentiment_analyzer.analyze_sentiment(request.text)
        
        # Calculate conflict score
        conflict_score = 0.0
        conflict_type = None
        affected_users = []
        
        # Sentiment-based conflict detection
        if sentiment_result['sentiment_category'] in ['very_negative', 'negative']:
            conflict_score = 0.7 if sentiment_result['sentiment_category'] == 'very_negative' else 0.5
            conflict_type = "sentiment_based"
        
        # Keyword-based conflict detection
        conflict_keywords = {
            'disagreement': ['disagree', 'don\'t agree', 'not acceptable'],
            'escalation': ['urgent', 'critical', 'emergency', 'immediately'],
            'complaint': ['complaint', 'unhappy', 'dissatisfied', 'not satisfied'],
            'concern': ['concern', 'worried', 'problem', 'issue']
        }
        
        for ctype, keywords in conflict_keywords.items():
            for keyword in keywords:
                if keyword.lower() in request.text.lower():
                    conflict_score = min(1.0, conflict_score + 0.2)
                    if not conflict_type:
                        conflict_type = ctype
        
        recommended_action = "Monitor situation"
        if conflict_score > 0.8:
            recommended_action = "Escalate to manager immediately"
        elif conflict_score > 0.6:
            recommended_action = "Team lead should review and consider mediation"
        elif conflict_score > 0.4:
            recommended_action = "Document and monitor for escalation"
        
        return ConflictDetectionResponse(
            contains_conflict=conflict_score > 0.4,
            conflict_score=conflict_score,
            conflict_type=conflict_type,
            affected_users=affected_users,
            recommended_action=recommended_action,
            confidence=sentiment_result['confidence']
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting conflict: {str(e)}")


@router.get("/conflicts/{project_id}", response_model=List[ConflictAlertResponse])
async def get_project_conflicts(
    project_id: int,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get conflict alerts for a project"""
    query = db.query(ConflictAlert).filter(ConflictAlert.project_id == project_id)
    
    if status:
        query = query.filter(ConflictAlert.status == status)
    
    if severity:
        query = query.filter(ConflictAlert.severity == severity)
    
    alerts = query.order_by(ConflictAlert.created_at.desc()).limit(limit).all()
    return alerts


@router.put("/conflicts/{conflict_id}")
async def update_conflict_status(
    conflict_id: int,
    status: str,
    resolution_notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Update conflict alert status and resolution"""
    alert = db.query(ConflictAlert).filter(ConflictAlert.id == conflict_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Conflict alert not found")
    
    alert.status = status
    if resolution_notes:
        alert.resolution_notes = resolution_notes
    
    if status == "resolved":
        alert.resolved_at = datetime.utcnow()
    
    db.commit()
    db.refresh(alert)
    
    return {"message": "Conflict status updated", "alert": alert}


# ==================== Collaboration Metrics Endpoints ====================

@router.get("/collaboration-metrics/{project_id}/{team_member_id}")
async def get_collaboration_metrics(
    project_id: int,
    team_member_id: int,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get collaboration metrics for a team member"""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    metrics = db.query(CollaborationMetrics).filter(
        CollaborationMetrics.project_id == project_id,
        CollaborationMetrics.team_member_id == team_member_id,
        CollaborationMetrics.period_date >= start_date
    ).order_by(CollaborationMetrics.period_date.desc()).all()
    
    if not metrics:
        raise HTTPException(status_code=404, detail="No collaboration metrics found")
    
    return metrics


@router.post("/collaboration-metrics")
async def create_collaboration_metrics(
    project_id: int,
    team_member_id: int,
    db: Session = Depends(get_db)
):
    """
    Generate collaboration metrics for a team member based on their messages
    """
    try:
        # Get messages from today
        today = datetime.utcnow().date()
        messages = db.query(CommunicationMessage).filter(
            CommunicationMessage.project_id == project_id,
            CommunicationMessage.sender_id == team_member_id,
            db.func.date(CommunicationMessage.created_at) == today
        ).all()
        
        if not messages:
            raise HTTPException(status_code=400, detail="No messages found for this period")
        
        # Calculate metrics
        messages_sent = len(messages)
        avg_message_length = sum(len(msg.content.split()) for msg in messages) / messages_sent
        
        sentiments = [msg.sentiment_score for msg in messages if msg.sentiment_score]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0
        
        positive = sum(1 for msg in messages if msg.sentiment_category in ['positive', 'very_positive'])
        negative = sum(1 for msg in messages if msg.sentiment_category in ['negative', 'very_negative'])
        neutral = messages_sent - positive - negative
        
        collaboration_score = min(1.0, (messages_sent / 10) * (1 + avg_sentiment) / 2)
        
        metrics = CollaborationMetrics(
            project_id=project_id,
            team_member_id=team_member_id,
            period_date=datetime.utcnow(),
            period_type="daily",
            messages_sent=messages_sent,
            messages_received=0,
            avg_message_length=avg_message_length,
            avg_response_time=0.0,
            messages_with_response=0,
            response_rate=0.0,
            collaboration_score=collaboration_score,
            avg_sentiment=avg_sentiment,
            positive_messages=positive,
            negative_messages=negative,
            neutral_messages=neutral
        )
        
        db.add(metrics)
        db.commit()
        db.refresh(metrics)
        
        return metrics
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating metrics: {str(e)}")
