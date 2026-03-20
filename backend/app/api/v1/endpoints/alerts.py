"""
Intelligent Alerts & Status Updates API Endpoints
Handles alert management, delivery, preferences, and predictive insights
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Optional, List
import json

from app.core.database import get_db
from app.models.models import (
    Alert, AlertTemplate, AlertPreference, AlertDeliveryLog, AlertBatch,
    PredictiveInsight, User, Project
)
from app.schemas.schemas import (
    AlertCreate, AlertResponse, AlertPreferenceCreate, AlertPreferenceResponse,
    PredictiveInsightResponse, AlertBatchResponse
)
from ai_services.predictive_analytics_service import PredictiveAnalyzer, SmartBatchingOptimizer

router = APIRouter()
predictive_analyzer = PredictiveAnalyzer()
batching_optimizer = SmartBatchingOptimizer()


# ==================== Alert Template Endpoints ====================

@router.post("/templates")
async def create_alert_template(
    template_data: dict,
    db: Session = Depends(get_db)
):
    """Create a new alert template"""
    try:
        template = AlertTemplate(
            name=template_data.get('name'),
            category=template_data.get('category'),
            description=template_data.get('description'),
            default_priority=template_data.get('default_priority', 'medium'),
            prediction_type=template_data.get('prediction_type'),
            email_subject=template_data.get('email_subject'),
            email_body=template_data.get('email_body'),
            in_app_title=template_data.get('in_app_title'),
            in_app_message=template_data.get('in_app_message'),
            allowed_channels=template_data.get('allowed_channels', ['email', 'inapp'])
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        return template
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error creating template: {str(e)}")


@router.get("/templates/{category}")
async def get_templates_by_category(
    category: str,
    db: Session = Depends(get_db)
):
    """Get alert templates by category"""
    templates = db.query(AlertTemplate).filter(
        AlertTemplate.category == category,
        AlertTemplate.enabled_by_default == True
    ).all()
    return templates


# ==================== Alert Management Endpoints ====================

@router.post("/alerts/{project_id}/predict")
async def predict_project_risks(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Analyze project for potential risks and create predictive alerts
    Runs in background
    """
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Run analysis in background
        background_tasks.add_task(
            _process_predictive_insights,
            project_id=project_id,
            db=db
        )
        
        return {"message": "Predictive analysis started", "project_id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting analysis: {str(e)}")


def _process_predictive_insights(project_id: int, db: Session):
    """Background task to process predictions and create alerts"""
    try:
        # Get all risks
        insights = predictive_analyzer.analyze_all_risks(db, project_id)
        
        # Get project members who should receive alerts
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return
        
        # Create alerts for each insight
        for insight in insights:
            # Find appropriate template
            template = db.query(AlertTemplate).filter(
                AlertTemplate.category == insight['insight_type']
            ).first()
            
            if not template:
                continue
            
            # Create predictive insight record
            pred_insight = PredictiveInsight(
                project_id=project_id,
                insight_type=insight['insight_type'],
                risk_level=insight['risk_level'],
                confidence_score=insight['confidence_score'],
                entity_type=insight.get('entity_type'),
                entity_id=insight.get('entity_id'),
                predicted_issue=insight['predicted_issue'],
                risk_factors=json.dumps(insight.get('risk_factors', [])),
                recommended_actions=json.dumps(insight.get('recommended_actions', [])),
                expected_occurrence=insight.get('expected_occurrence')
            )
            
            db.add(pred_insight)
            db.commit()
            
            # Calculate urgency
            urgency_score = predictive_analyzer.calculate_urgency_score(insight)
            
            # Create alerts for project members
            members = [project.owner_id]  # At minimum, notify project owner
            
            for member_id in members:
                try:
                    alert = Alert(
                        project_id=project_id,
                        template_id=template.id,
                        alert_type=insight['insight_type'],
                        entity_type=insight.get('entity_type'),
                        entity_id=insight.get('entity_id'),
                        title=template.in_app_title,
                        description=insight['predicted_issue'],
                        context_data=json.dumps(insight),
                        priority=insight['risk_level'],
                        urgency_score=urgency_score,
                        recipient_id=member_id,
                        is_predictive=True,
                        prediction_confidence=insight['confidence_score'],
                        predicted_issue=insight.get('predicted_issue')
                    )
                    
                    db.add(alert)
                except Exception as e:
                    print(f"Error creating alert: {str(e)}")
            
            db.commit()
            
    except Exception as e:
        print(f"Error processing predictive insights: {str(e)}")


@router.get("/alerts/{project_id}", response_model=List[AlertResponse])
async def get_project_alerts(
    project_id: int,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    alert_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get project alerts with optional filters"""
    query = db.query(Alert).filter(Alert.project_id == project_id)
    
    if status:
        query = query.filter(Alert.delivery_status == status)
    
    if priority:
        priority_order = ['low', 'medium', 'high', 'critical']
        if priority in priority_order:
            query = query.filter(Alert.priority.in_(priority_order[priority_order.index(priority):]))
    
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    
    alerts = query.order_by(Alert.urgency_score.desc()).limit(limit).all()
    return alerts


@router.get("/alerts/user/{user_id}/inbox", response_model=List[AlertResponse])
async def get_user_alert_inbox(
    user_id: int,
    include_opened: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get alerts for current user"""
    query = db.query(Alert).filter(
        Alert.recipient_id == user_id,
        Alert.delivery_status.in_(['sent', 'opened']) if not include_opened else True
    )
    
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    return alerts


@router.put("/alerts/{alert_id}/mark-read")
async def mark_alert_as_read(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Mark alert as opened/read"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.delivery_status = "opened"
    alert.opened_at = datetime.utcnow()
    
    db.commit()
    return {"message": "Alert marked as read", "alert_id": alert_id}


@router.delete("/alerts/{alert_id}/archive")
async def archive_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Archive alert (soft delete)"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.delivery_status = "archived"
    alert.archived_at = datetime.utcnow()
    
    db.commit()
    return {"message": "Alert archived"}


# ==================== Alert Preferences Endpoints ====================

@router.post("/preferences/{user_id}")
async def upsert_user_preferences(
    user_id: int,
    preferences: dict,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create or update user alert preferences"""
    try:
        # Check for existing preference
        existing = db.query(AlertPreference).filter(
            AlertPreference.user_id == user_id,
            AlertPreference.project_id == project_id
        ).first()
        
        if existing:
            # Update
            for key, value in preferences.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            # Create new
            pref = AlertPreference(
                user_id=user_id,
                project_id=project_id,
                **preferences
            )
            db.add(pref)
        
        db.commit()
        return {"message": "Preferences saved", "user_id": user_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error saving preferences: {str(e)}")


@router.get("/preferences/{user_id}")
async def get_user_preferences(
    user_id: int,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get user alert preferences"""
    query = db.query(AlertPreference).filter(AlertPreference.user_id == user_id)
    
    if project_id:
        # Try project-specific, fallback to global
        pref = query.filter(AlertPreference.project_id == project_id).first()
        if not pref:
            pref = query.filter(AlertPreference.project_id == None).first()
    else:
        pref = query.filter(AlertPreference.project_id == None).first()
    
    if not pref:
        # Return defaults
        return {
            "email_enabled": True,
            "sms_enabled": False,
            "inapp_enabled": True,
            "teams_enabled": False,
            "batching_enabled": True,
            "quiet_hours_enabled": True,
            "quiet_hours_start": 22,
            "quiet_hours_end": 8
        }
    
    return pref


# ==================== Predictive Insights Endpoints ====================

@router.get("/insights/{project_id}", response_model=List[PredictiveInsightResponse])
async def get_project_insights(
    project_id: int,
    insight_type: Optional[str] = None,
    risk_level: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get predictive insights for project"""
    query = db.query(PredictiveInsight).filter(PredictiveInsight.project_id == project_id)
    
    if insight_type:
        query = query.filter(PredictiveInsight.insight_type == insight_type)
    
    if risk_level:
        query = query.filter(PredictiveInsight.risk_level == risk_level)
    
    insights = query.order_by(PredictiveInsight.prediction_date.desc()).limit(limit).all()
    return insights


@router.post("/insights/{insight_id}/validate")
async def validate_prediction(
    insight_id: int,
    occurred: bool,
    db: Session = Depends(get_db)
):
    """Validate if prediction came true (for ML training)"""
    insight = db.query(PredictiveInsight).filter(PredictiveInsight.id == insight_id).first()
    
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    
    insight.actual_issue_occurred = occurred
    insight.actual_occurrence_date = datetime.utcnow() if occurred else None
    
    db.commit()
    return {"message": "Prediction validated", "insight_id": insight_id}


# ==================== Delivery & Batching Endpoints ====================

@router.post("/batch/{project_id}/optimize")
async def optimize_alert_batching(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Analyze pending alerts and create optimal batches
    Uses ML-based batching strategy
    """
    try:
        # Get pending alerts
        pending_alerts = db.query(Alert).filter(
            Alert.project_id == project_id,
            Alert.delivery_status == "pending",
            Alert.should_batch == True
        ).all()
        
        if not pending_alerts:
            return {"message": "No alerts to batch", "batches_created": 0}
        
        # Group alerts by recipient
        alerts_by_recipient = {}
        for alert in pending_alerts:
            if alert.recipient_id not in alerts_by_recipient:
                alerts_by_recipient[alert.recipient_id] = []
            alerts_by_recipient[alert.recipient_id].append(alert)
        
        batches_created = 0
        
        # Create batches for each recipient
        for recipient_id, recipient_alerts in alerts_by_recipient.items():
            if len(recipient_alerts) < 2:
                continue  # Don't batch single alerts
            
            # Get user preferences
            user_pref = db.query(AlertPreference).filter(
                AlertPreference.user_id == recipient_id,
                AlertPreference.project_id == project_id
            ).first()
            
            prefs = user_pref.__dict__ if user_pref else {}
            
            # Determine batching strategy
            strategy, reduction = batching_optimizer.suggest_batching_strategy(
                [alert.__dict__ for alert in recipient_alerts],
                prefs
            )
            
            if strategy == 'no_batch':
                continue
            
            # Create batch
            batch = AlertBatch(
                project_id=project_id,
                recipient_id=recipient_id,
                batch_type=strategy,
                status="pending",
                alert_count=len(recipient_alerts),
                alert_ids=json.dumps([a.id for a in recipient_alerts]),
                ml_recommendation=strategy,
                batching_score=batching_optimizer.calculate_batching_score(
                    [a.__dict__ for a in recipient_alerts]
                ),
                estimated_reduction=reduction
            )
            
            db.add(batch)
            db.flush()
            
            # Update alerts with batch ID
            for alert in recipient_alerts:
                alert.batch_id = batch.id
            
            batches_created += 1
        
        db.commit()
        
        # Schedule batch delivery
        background_tasks.add_task(_deliver_batched_alerts, project_id=project_id)
        
        return {"message": f"Created {batches_created} batches", "batches_created": batches_created}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error optimizing batches: {str(e)}")


def _deliver_batched_alerts(project_id: int):
    """Background task to deliver batched alerts"""
    # This would handle actual email/Teams/SMS delivery
    # For now, just mark as scheduled
    pass


@router.get("/delivery-logs/{alert_id}")
async def get_alert_delivery_logs(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Get delivery logs for an alert"""
    logs = db.query(AlertDeliveryLog).filter(
        AlertDeliveryLog.alert_id == alert_id
    ).order_by(AlertDeliveryLog.created_at.desc()).all()
    
    return logs


# ==================== Analytics & Reporting Endpoints ====================

@router.get("/analytics/{project_id}/summary")
async def get_alert_analytics(
    project_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """Get alert analytics for project"""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Alert counts
    total_alerts = db.query(Alert).filter(
        Alert.project_id == project_id,
        Alert.created_at >= start_date
    ).count()
    
    by_priority = db.query(
        Alert.priority,
        func.count(Alert.id)
    ).filter(
        Alert.project_id == project_id,
        Alert.created_at >= start_date
    ).group_by(Alert.priority).all()
    
    by_type = db.query(
        Alert.alert_type,
        func.count(Alert.id)
    ).filter(
        Alert.project_id == project_id,
        Alert.created_at >= start_date
    ).group_by(Alert.alert_type).all()
    
    # Delivery metrics
    sent_alerts = db.query(Alert).filter(
        Alert.project_id == project_id,
        Alert.created_at >= start_date,
        Alert.sent_at != None
    ).count()
    
    opened_alerts = db.query(Alert).filter(
        Alert.project_id == project_id,
        Alert.created_at >= start_date,
        Alert.opened_at != None
    ).count()
    
    return {
        "period_days": days,
        "total_alerts": total_alerts,
        "sent_alerts": sent_alerts,
        "opened_alerts": opened_alerts,
        "open_rate": (opened_alerts / max(sent_alerts, 1)) * 100,
        "by_priority": [{"priority": p, "count": c} for p, c in by_priority],
        "by_type": [{"type": t, "count": c} for t, c in by_type],
        "predictive_alerts": db.query(Alert).filter(
            Alert.project_id == project_id,
            Alert.is_predictive == True,
            Alert.created_at >= start_date
        ).count(),
        "batched_alerts": db.query(func.count(Alert.id)).filter(
            Alert.project_id == project_id,
            Alert.batch_id != None,
            Alert.created_at >= start_date
        ).scalar() or 0
    }


@router.get("/quiet-hours/{user_id}")
async def check_quiet_hours(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Check if user is in quiet hours"""
    pref = db.query(AlertPreference).filter(
        AlertPreference.user_id == user_id,
        AlertPreference.project_id == None
    ).first()
    
    if not pref or not pref.quiet_hours_enabled:
        return {"in_quiet_hours": False}
    
    # Get current hour in user's timezone (simplified)
    current_hour = datetime.utcnow().hour
    
    # Check if in quiet hours
    if pref.quiet_hours_start <= pref.quiet_hours_end:
        in_quiet_hours = pref.quiet_hours_start <= current_hour <= pref.quiet_hours_end
    else:  # Spans midnight
        in_quiet_hours = current_hour >= pref.quiet_hours_start or current_hour <= pref.quiet_hours_end
    
    return {
        "in_quiet_hours": in_quiet_hours,
        "quiet_hours_start": pref.quiet_hours_start,
        "quiet_hours_end": pref.quiet_hours_end,
        "current_hour": current_hour
    }


# ==================== Scheduler & Integration Endpoints ====================

@router.post("/scheduler/start")
async def start_alert_scheduler(
    check_interval_minutes: int = 30,
    db: Session = Depends(get_db)
):
    """
    Start the background alert monitoring scheduler.
    
    The scheduler runs periodic checks that:
    - Monitor sentiment trends (Phase 1 integration)
    - Monitor team communication (Phase 2 integration)
    - Check task delays and scope creep
    - Monitor budget health
    - Analyze team workload balance
    
    When alerts are detected, they're automatically created.
    """
    try:
        from app.services.scheduler import start_scheduler
        
        success = start_scheduler(check_interval_minutes=check_interval_minutes)
        
        if success:
            return {
                "message": "Alert scheduler started successfully",
                "check_interval_minutes": check_interval_minutes,
                "status": "running"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to start scheduler")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scheduler/stop")
async def stop_alert_scheduler(db: Session = Depends(get_db)):
    """
    Stop the background alert monitoring scheduler.
    
    Stops all background checks. Alerts will no longer be created
    automatically until scheduler is restarted.
    """
    try:
        from app.services.scheduler import stop_scheduler
        
        success = stop_scheduler()
        
        if success:
            return {
                "message": "Alert scheduler stopped successfully",
                "status": "stopped"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to stop scheduler")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/status")
async def get_scheduler_status(db: Session = Depends(get_db)):
    """
    Get current scheduler status and job information.
    
    Returns:
    - status: running/stopped/not_initialized
    - running: bool
    - job_count: number of scheduled jobs
    - jobs: list of scheduled jobs with next run times
    """
    try:
        from app.services.scheduler import get_scheduler_status
        
        return get_scheduler_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-project/{project_id}")
async def manually_check_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Manually trigger alert checks for a single project.
    
    Useful for immediate checks without waiting for scheduler.
    Runs in background and creates alerts based on findings.
    
    Checks:
    - Sentiment trends (Phase 1)
    - Communication quality (Phase 2)
    - Task delays
    - Budget status
    - Team workload
    - Scope creep
    """
    try:
        from app.services.alert_integration_service import BackgroundAlertMonitor
        
        # Run monitoring in background
        background_tasks.add_task(
            _background_check_project,
            project_id=project_id,
            db=db
        )
        
        return {
            "message": f"Alert checks initiated for project {project_id}",
            "project_id": project_id,
            "status": "processing"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _background_check_project(project_id: int, db: Session):
    """Background task for project monitoring."""
    try:
        from app.services.alert_integration_service import BackgroundAlertMonitor
        
        monitor = BackgroundAlertMonitor()
        await monitor.monitor_project(db, project_id)
    except Exception as e:
        logger = __import__('logging').getLogger(__name__)
        logger.error(f"Error checking project {project_id}: {e}")


@router.get("/integration-health/{project_id}")
async def get_integration_health(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Get integration health metrics for a project.
    
    Shows:
    - Last check time
    - Recent alerts by category
    - Data availability from Phase 1 & 2
    - Outstanding issues
    """
    try:
        # Get recent alerts
        recent_alerts = db.query(Alert).filter(
            Alert.project_id == project_id,
            Alert.created_at >= datetime.utcnow() - timedelta(days=7)
        ).count()
        
        # Check for Phase 1 data availability
        has_sentiment = False
        try:
            from app.models.models import SentimentScore
            has_sentiment = db.query(SentimentScore).filter(
                SentimentScore.project_id == project_id
            ).first() is not None
        except:
            pass
        
        # Check for Phase 2 data availability
        has_communication = False
        try:
            from app.models.models import CommunicationMessage
            has_communication = db.query(CommunicationMessage).filter(
                CommunicationMessage.project_id == project_id
            ).first() is not None
        except:
            pass
        
        return {
            "project_id": project_id,
            "recent_alerts_7days": recent_alerts,
            "phase1_sentiment_available": has_sentiment,
            "phase2_communication_available": has_communication,
            "integration_status": "healthy" if (has_sentiment or has_communication) else "partial",
            "last_check": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
