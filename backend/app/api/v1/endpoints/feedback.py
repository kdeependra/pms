"""
Sentiment Analysis & Stakeholder Feedback API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from typing import List, Optional
from datetime import datetime, timedelta
from collections import Counter
import numpy as np

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import (
    Survey, SurveyQuestion, SurveyResponseData, StakeholderFeedback,
    StakeholderSatisfaction, FeedbackActionItem, Project, User
)
from app.schemas.schemas import (
    SurveyCreate, SurveyUpdate, SurveyResponse, SurveyQuestionCreate,
    SurveyResponseResponse,
    FeedbackCreate, FeedbackUpdate, FeedbackResponse, FeedbackAnalyticsResponse,
    ActionItemCreate, ActionItemUpdate, ActionItemResponse,
    StakeholderSatisfactionResponse, SentimentAnalysisSummary
)
from ai_services.sentiment_analysis_service import sentiment_analyzer, survey_analyzer

router = APIRouter()


# ==================== Survey Endpoints ====================

@router.post("/surveys", response_model=SurveyResponse, status_code=status.HTTP_201_CREATED)
async def create_survey(
    survey: SurveyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new survey"""
    # Verify project exists and user has access
    project_result = await db.execute(
        select(Project).where(Project.id == survey.project_id)
    )
    project = project_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    db_survey = Survey(
        **survey.dict(),
        created_by=current_user['id']
    )
    db.add(db_survey)
    await db.commit()
    await db.refresh(db_survey)
    
    return db_survey


@router.get("/surveys/{project_id}", response_model=List[SurveyResponse])
async def get_project_surveys(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None)
):
    """Get surveys for a project"""
    query = select(Survey).where(Survey.project_id == project_id)
    
    if status_filter:
        query = query.where(Survey.status == status_filter)
    
    result = await db.execute(query.order_by(desc(Survey.created_at)))
    surveys = result.scalars().all()
    
    return surveys


@router.get("/surveys/{survey_id}/details", response_model=SurveyResponse)
async def get_survey_details(
    survey_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed survey information with all questions and responses"""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalars().first()
    
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    
    return survey


@router.put("/surveys/{survey_id}", response_model=SurveyResponse)
async def update_survey(
    survey_id: int,
    update_data: SurveyUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update survey"""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalars().first()
    
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(survey, field, value)
    
    survey.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(survey)
    
    return survey


@router.post("/surveys/{survey_id}/questions", status_code=status.HTTP_201_CREATED)
async def add_survey_question(
    survey_id: int,
    question: SurveyQuestionCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a question to a survey"""
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalars().first()
    
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    
    db_question = SurveyQuestion(**question.dict())
    db.add(db_question)
    await db.commit()
    await db.refresh(db_question)
    
    return db_question


# ==================== Survey Response Endpoints ====================

@router.post("/surveys/{survey_id}/responses", status_code=status.HTTP_201_CREATED)
async def submit_survey_response(
    survey_id: int,
    feedback_text: str,
    respondent_email: Optional[str] = None,
    respondent_name: Optional[str] = None,
    respondent_role: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Submit a survey response with sentiment analysis"""
    # Verify survey exists
    result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = result.scalars().first()
    
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    
    # Analyze sentiment
    sentiment_result = sentiment_analyzer.analyze_sentiment(feedback_text)
    
    # Generate action items
    action_items = sentiment_analyzer.generate_action_items(feedback_text)
    
    # Create response
    db_response = SurveyResponseData(
        survey_id=survey_id,
        feedback_text=feedback_text,
        respondent_email=respondent_email,
        respondent_name=respondent_name,
        respondent_role=respondent_role,
        sentiment_score=sentiment_result['sentiment_score'],
        sentiment_category=sentiment_result['sentiment_category'],
        action_items=[item['title'] for item in action_items]
    )
    
    db.add(db_response)
    await db.commit()
    await db.refresh(db_response)
    
    return {
        "response_id": db_response.id,
        "sentiment_score": sentiment_result['sentiment_score'],
        "sentiment_category": sentiment_result['sentiment_category'],
        "action_items": action_items
    }


@router.get("/surveys/{survey_id}/analytics")
async def get_survey_analytics(
    survey_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive survey analytics"""
    # Get all responses for the survey
    result = await db.execute(
        select(SurveyResponseData).where(SurveyResponseData.survey_id == survey_id)
    )
    responses = result.scalars().all()
    
    if not responses:
        return {
            "survey_id": survey_id,
            "total_responses": 0,
            "avg_rating": 0,
            "sentiment_distribution": {},
            "action_items": [],
            "top_topics": []
        }
    
    # Convert to dicts for analyzer
    response_dicts = [
        {
            "rating": 4.5,  # Default rating
            "feedback_text": r.feedback_text or ""
        }
        for r in responses
    ]
    
    # Get survey for base data
    survey_result = await db.execute(
        select(Survey).where(Survey.id == survey_id)
    )
    survey = survey_result.scalars().first()
    
    # Analyze survey responses
    analysis = survey_analyzer.analyze_survey_responses(response_dicts)
    
    # Calculate response rate if possible
    if survey and survey.target_audience:
        # This would require target audience count - simplified for now
        response_rate = (len(responses) / max(len(responses), 1)) * 100
    else:
        response_rate = 100.0
    
    analysis['response_rate'] = response_rate
    analysis['survey_id'] = survey_id
    
    return analysis


# ==================== Feedback Endpoints ====================

@router.post("/feedback", response_model=dict, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    feedback: FeedbackCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit stakeholder feedback with AI analysis"""
    # Verify project exists
    project_result = await db.execute(
        select(Project).where(Project.id == feedback.project_id)
    )
    project = project_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Analyze feedback sentiment
    sentiment_result = sentiment_analyzer.analyze_sentiment(feedback.content)
    
    # Extract topics
    topics = sentiment_analyzer.extract_key_topics([feedback.content], num_topics=3)
    topic_list = [t['topic'] for t in topics]
    
    # Generate action items
    action_items = sentiment_analyzer.generate_action_items(feedback.content)
    action_item_titles = [item['title'] for item in action_items]
    
    # Create feedback record
    db_feedback = StakeholderFeedback(
        **feedback.dict(),
        sentiment=sentiment_result['sentiment_category'],
        sentiment_score=sentiment_result['sentiment_score'],
        key_topics=topic_list,
        action_items=action_item_titles
    )
    
    db.add(db_feedback)
    await db.flush()  # To get the ID
    feedback_id = db_feedback.id
    
    # Create action items in database
    for action_item in action_items:
        db_action_item = FeedbackActionItem(
            feedback_id=feedback_id,
            project_id=feedback.project_id,
            title=action_item['title'],
            priority=action_item['urgency'],
            status='open'
        )
        if action_item.get('timeline'):
            try:
                days = int(''.join(filter(str.isdigit, action_item['timeline'])))
                db_action_item.due_date = datetime.utcnow() + timedelta(days=days)
            except:
                pass
        
        db.add(db_action_item)
    
    await db.commit()
    await db.refresh(db_feedback)
    
    return {
        "feedback_id": feedback_id,
        "sentiment": sentiment_result['sentiment_category'],
        "sentiment_score": sentiment_result['sentiment_score'],
        "key_topics": topic_list,
        "action_items": action_item_titles,
        "message": "Feedback submitted successfully"
    }


@router.get("/feedback/{project_id}")
async def get_project_feedback(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    feedback_type_filter: Optional[str] = Query(None)
):
    """Get feedback for a project"""
    query = select(StakeholderFeedback).where(
        StakeholderFeedback.project_id == project_id
    )
    
    if status_filter:
        query = query.where(StakeholderFeedback.status == status_filter)
    
    if feedback_type_filter:
        query = query.where(StakeholderFeedback.feedback_type == feedback_type_filter)
    
    result = await db.execute(
        query.order_by(desc(StakeholderFeedback.created_at))
    )
    feedback_list = result.scalars().all()
    
    return feedback_list


@router.get("/feedback/{feedback_id}/details")
async def get_feedback_details(
    feedback_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed feedback information"""
    result = await db.execute(
        select(StakeholderFeedback).where(StakeholderFeedback.id == feedback_id)
    )
    feedback = result.scalars().first()
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    # Get related action items
    action_items_result = await db.execute(
        select(FeedbackActionItem).where(FeedbackActionItem.feedback_id == feedback_id)
    )
    action_items = action_items_result.scalars().all()
    
    return {
        "feedback": feedback,
        "action_items": action_items
    }


@router.put("/feedback/{feedback_id}", response_model=dict)
async def update_feedback(
    feedback_id: int,
    update_data: FeedbackUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update feedback status and resolution"""
    result = await db.execute(
        select(StakeholderFeedback).where(StakeholderFeedback.id == feedback_id)
    )
    feedback = result.scalars().first()
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(feedback, field, value)
    
    feedback.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(feedback)
    
    return {"message": "Feedback updated successfully"}


@router.get("/feedback/{project_id}/analytics")
async def get_feedback_analytics(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30)
):
    """Get comprehensive feedback analytics"""
    # Get feedback from the period
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(StakeholderFeedback).where(
            and_(
                StakeholderFeedback.project_id == project_id,
                StakeholderFeedback.created_at >= cutoff_date
            )
        ).order_by(StakeholderFeedback.created_at)
    )
    feedback_list = result.scalars().all()
    
    if not feedback_list:
        return {
            "project_id": project_id,
            "total_feedback": 0,
            "open_feedback": 0,
            "resolved_feedback": 0,
            "avg_sentiment_score": 0,
            "sentiment_distribution": {},
            "top_topics": [],
            "feedback_by_type": {},
            "feedback_trend": [],
            "action_item_status": {}
        }
    
    # Calculate metrics
    total_feedback = len(feedback_list)
    open_count = sum(1 for f in feedback_list if f.status == "open")
    resolved_count = sum(1 for f in feedback_list if f.status == "resolved")
    
    # Sentiment analysis
    sentiments = [f.sentiment for f in feedback_list]
    sentiment_distribution = dict(Counter(sentiments))
    avg_sentiment = sum(f.sentiment_score for f in feedback_list) / total_feedback if total_feedback > 0 else 0
    
    # Topics
    all_topics = []
    for f in feedback_list:
        if f.key_topics:
            all_topics.extend(f.key_topics)
    topic_counter = Counter(all_topics)
    top_topics = [
        {"topic": topic, "count": count}
        for topic, count in topic_counter.most_common(5)
    ]
    
    # Feedback by type
    feedback_by_type = {}
    for f in feedback_list:
        ftype = f.feedback_type or "general"
        feedback_by_type[ftype] = feedback_by_type.get(ftype, 0) + 1
    
    # Trend data
    daily_totals = {}
    for f in feedback_list:
        date_key = f.created_at.date()
        if date_key not in daily_totals:
            daily_totals[date_key] = {"total": 0, "positive": 0}
        daily_totals[date_key]["total"] += 1
        if f.sentiment_score > 0.1:
            daily_totals[date_key]["positive"] += 1
    
    feedback_trend = [
        {
            "date": str(date),
            "total": data["total"],
            "positive": data["positive"]
        }
        for date, data in sorted(daily_totals.items())
    ]
    
    # Action item status
    action_items_result = await db.execute(
        select(FeedbackActionItem).where(
            and_(
                FeedbackActionItem.project_id == project_id,
                FeedbackActionItem.created_at >= cutoff_date
            )
        )
    )
    action_items = action_items_result.scalars().all()
    
    action_item_status = {
        "open": sum(1 for a in action_items if a.status == "open"),
        "in_progress": sum(1 for a in action_items if a.status == "in_progress"),
        "completed": sum(1 for a in action_items if a.status == "completed")
    }
    
    return {
        "project_id": project_id,
        "total_feedback": total_feedback,
        "open_feedback": open_count,
        "resolved_feedback": resolved_count,
        "avg_sentiment_score": float(avg_sentiment),
        "sentiment_distribution": sentiment_distribution,
        "top_topics": top_topics,
        "feedback_by_type": feedback_by_type,
        "feedback_trend": feedback_trend,
        "action_item_status": action_item_status
    }


# ==================== Action Item Endpoints ====================

@router.post("/action-items", response_model=ActionItemResponse, status_code=status.HTTP_201_CREATED)
async def create_action_item(
    action_item: ActionItemCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create an action item from feedback"""
    db_action_item = FeedbackActionItem(**action_item.dict())
    db.add(db_action_item)
    await db.commit()
    await db.refresh(db_action_item)
    
    return db_action_item


@router.get("/action-items/{project_id}")
async def get_project_action_items(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None)
):
    """Get action items for a project"""
    query = select(FeedbackActionItem).where(
        FeedbackActionItem.project_id == project_id
    )
    
    if status_filter:
        query = query.where(FeedbackActionItem.status == status_filter)
    
    result = await db.execute(
        query.order_by(desc(FeedbackActionItem.created_at))
    )
    action_items = result.scalars().all()
    
    return action_items


@router.put("/action-items/{action_item_id}", response_model=dict)
async def update_action_item(
    action_item_id: int,
    update_data: ActionItemUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update action item status"""
    result = await db.execute(
        select(FeedbackActionItem).where(FeedbackActionItem.id == action_item_id)
    )
    action_item = result.scalars().first()
    
    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")
    
    for field, value in update_data.dict(exclude_unset=True).items():
        if field == 'status' and value == 'completed':
            action_item.completed_at = datetime.utcnow()
        setattr(action_item, field, value)
    
    await db.commit()
    
    return {"message": "Action item updated successfully"}


# ==================== Sentiment Analysis Endpoints ====================

@router.post("/analyze-sentiment")
async def analyze_text_sentiment(
    text: str,
    current_user: dict = Depends(get_current_user)
):
    """Analyze sentiment of any text"""
    if not text or len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    sentiment_result = sentiment_analyzer.analyze_sentiment(text)
    
    return {
        "text": text[:100],
        "sentiment_score": sentiment_result['sentiment_score'],
        "sentiment_category": sentiment_result['sentiment_category'],
        "confidence": sentiment_result['confidence'],
        "methods": sentiment_result['methods']
    }


@router.post("/extract-topics")
async def extract_text_topics(
    text: str,
    num_topics: int = 5,
    current_user: dict = Depends(get_current_user)
):
    """Extract key topics from text"""
    if not text or len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    topics = sentiment_analyzer.extract_key_topics([text], num_topics=min(num_topics, 10))
    
    return {
        "num_topics": len(topics),
        "topics": topics
    }


@router.post("/generate-action-items")
async def generate_text_action_items(
    text: str,
    current_user: dict = Depends(get_current_user)
):
    """Generate action items from feedback text"""
    if not text or len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    action_items = sentiment_analyzer.generate_action_items(text)
    
    return {
        "action_items_count": len(action_items),
        "action_items": action_items
    }


# ==================== Communication Sentiment Analysis ====================

@router.get("/sentiment-communications/{project_id}")
async def analyze_communication_sentiment(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30)
):
    """Analyze sentiment in project communications"""
    # This would analyze emails, messages, and comments from the project
    # For now, return a template response
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Get feedback and survey responses as proxies for communications
    feedback_result = await db.execute(
        select(StakeholderFeedback).where(
            and_(
                StakeholderFeedback.project_id == project_id,
                StakeholderFeedback.created_at >= cutoff_date
            )
        )
    )
    feedback_list = feedback_result.scalars().all()
    
    if not feedback_list:
        return {
            "communication_type": "all",
            "total_communications": 0,
            "positive_percentage": 0,
            "neutral_percentage": 0,
            "negative_percentage": 0,
            "overall_sentiment": 0,
            "daily_sentiment": [],
            "sentiment_keywords": {}
        }
    
    # Count sentiments
    total = len(feedback_list)
    positive = sum(1 for f in feedback_list if f.sentiment_score > 0.1)
    neutral = sum(1 for f in feedback_list if -0.1 <= f.sentiment_score <= 0.1)
    negative = sum(1 for f in feedback_list if f.sentiment_score < -0.1)
    
    # Calculate overall sentiment
    overall = sum(f.sentiment_score for f in feedback_list) / total if total > 0 else 0
    
    # Daily trend
    daily_sentiment = {}
    for f in feedback_list:
        date_key = f.created_at.date()
        if date_key not in daily_sentiment:
            daily_sentiment[date_key] = {"scores": [], "count": 0}
        daily_sentiment[date_key]["scores"].append(f.sentiment_score)
        daily_sentiment[date_key]["count"] += 1
    
    daily_data = [
        {
            "date": str(date),
            "avg_sentiment": float(np.mean(data["scores"])),
            "count": data["count"]
        }
        for date, data in sorted(daily_sentiment.items())
    ]
    
    # Common positive/negative keywords
    all_content = " ".join(f.content for f in feedback_list if f.content)
    sentiment_result = sentiment_analyzer.analyze_sentiment(all_content)
    
    return {
        "communication_type": "all",
        "total_communications": total,
        "positive_percentage": (positive / total * 100) if total > 0 else 0,
        "neutral_percentage": (neutral / total * 100) if total > 0 else 0,
        "negative_percentage": (negative / total * 100) if total > 0 else 0,
        "overall_sentiment": float(overall),
        "daily_sentiment": daily_data,
        "sentiment_keywords": {}
    }
