"""
Phase 4: Automated Status Updates API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.schemas import ResponseSchema
from app.services.status_update_service import (
    StatusUpdateGenerator, ProgressCalculator, StatusDetector,
    StatusRecommendationEngine, StatusNotificationManager
)
from app.services.escalation_service import (
    EscalationManager, EscalationDetector, BiDirectionalIntegration
)
from app.models.models import (
    Project, StatusUpdate, StatusUpdateTemplate, ProgressUpdate,
    StatusRecommendation, EscalationAlert, NotificationLog, User
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/status-updates",
    tags=["Status Updates"]
)


# ==================== STATUS UPDATE ENDPOINTS ====================

@router.get("/{project_id}", response_model=ResponseSchema)
async def get_status_updates(
    project_id: int,
    limit: int = Query(10, ge=1, le=100),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get status updates for a project"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        updates = db.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id
        ).order_by(StatusUpdate.generated_at.desc()).offset(skip).limit(limit).all()
        
        return {
            "success": True,
            "data": [{
                "id": u.id,
                "status": u.status,
                "health": u.health,
                "overall_progress": u.overall_progress,
                "task_progress": u.task_progress,
                "summary": u.summary,
                "generated_at": u.generated_at,
                "is_published": u.is_published,
                "schedule_variance": u.schedule_variance,
                "budget_variance": u.budget_variance
            } for u in updates]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching status updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/latest", response_model=ResponseSchema)
async def get_latest_status_update(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get latest status update for a project"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        update = db.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id,
            StatusUpdate.is_published == True
        ).order_by(StatusUpdate.published_at.desc()).first()
        
        if not update:
            raise HTTPException(status_code=404, detail="No status updates found")
        
        return {
            "success": True,
            "data": {
                "id": update.id,
                "status": update.status,
                "health": update.health,
                "overall_progress": update.overall_progress,
                "summary": update.summary,
                "highlights": update.highlights,
                "concerns": update.concerns,
                "generated_at": update.generated_at,
                "published_at": update.published_at,
                "schedule_variance": update.schedule_variance,
                "budget_variance": update.budget_variance
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching latest status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/generate", response_model=ResponseSchema)
async def generate_status_update(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Manually trigger status update generation"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Generate update
        update = StatusUpdateGenerator.generate_update(db, project_id)
        
        # Generate recommendations
        recommendations = StatusRecommendationEngine.analyze_and_recommend(db, project_id, update.id)
        
        # Check for escalations
        if EscalationDetector.should_escalate(db, project_id):
            escalation_data = EscalationDetector.check_escalation_conditions(db, project_id, update)
            if escalation_data:
                escalation = EscalationManager.create_escalation(db, project_id, update, escalation_data)
                EscalationManager.notify_escalation(db, project_id, escalation_data)
        
        # Notify stakeholders
        NotificationManager.notify_stakeholders(db, update.id)
        
        return {
            "success": True,
            "message": "Status update generated successfully",
            "data": {
                "update_id": update.id,
                "status": update.status,
                "health": update.health,
                "progress": update.overall_progress,
                "recommendations_count": len(recommendations)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating status update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/publish/{update_id}", response_model=ResponseSchema)
async def publish_status_update(
    project_id: int,
    update_id: int,
    db: Session = Depends(get_db)
):
    """Publish a status update to stakeholders"""
    try:
        update = db.query(StatusUpdate).filter(
            StatusUpdate.id == update_id,
            StatusUpdate.project_id == project_id
        ).first()
        
        if not update:
            raise HTTPException(status_code=404, detail="Status update not found")
        
        # Notify stakeholders
        notification_count = StatusNotificationManager.notify_stakeholders(db, update_id)
        
        return {
            "success": True,
            "message": f"Status update published to {notification_count} stakeholders",
            "data": {"notifications_sent": notification_count}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing status update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PROGRESS ENDPOINTS ====================

@router.get("/{project_id}/progress", response_model=ResponseSchema)
async def get_project_progress(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed progress metrics"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Calculate progress using multiple methods
        task_progress = ProgressCalculator.calculate_task_progress(db, project_id)
        timeline_progress = ProgressCalculator.calculate_timeline_progress(db, project_id)
        budget_progress = ProgressCalculator.calculate_budget_progress(db, project_id)
        estimated_progress = ProgressCalculator.calculate_estimated_progress(db, project_id)
        
        return {
            "success": True,
            "data": {
                "task_progress": task_progress,
                "timeline_progress": timeline_progress,
                "budget_progress": budget_progress,
                "estimated_progress": round(estimated_progress, 1),
                "overall_progress": round((
                    task_progress.get("weighted_progress", 0) + 
                    estimated_progress + 
                    (100 - abs(timeline_progress.get("schedule_variance", 0)))
                ) / 3, 1)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching progress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RECOMMENDATIONS ENDPOINTS ====================

@router.get("/{project_id}/recommendations", response_model=ResponseSchema)
async def get_recommendations(
    project_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """Get status change recommendations"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        recommendations = db.query(StatusRecommendation).filter(
            StatusRecommendation.project_id == project_id,
            StatusRecommendation.is_accepted == False
        ).order_by(StatusRecommendation.created_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "data": [{
                "id": r.id,
                "recommendation_type": r.recommendation_type,
                "reason": r.reason,
                "confidence": r.confidence,
                "impact": r.impact,
                "suggested_actions": r.suggested_actions,
                "created_at": r.created_at
            } for r in recommendations]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/recommendations/{rec_id}/accept", response_model=ResponseSchema)
async def accept_recommendation(
    project_id: int,
    rec_id: int,
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """Accept a recommendation"""
    try:
        rec = db.query(StatusRecommendation).filter(
            StatusRecommendation.id == rec_id,
            StatusRecommendation.project_id == project_id
        ).first()
        
        if not rec:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        
        rec.is_accepted = True
        rec.accepted_by = user_id
        rec.accepted_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": "Recommendation accepted"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting recommendation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== ESCALATION ENDPOINTS ====================

@router.get("/{project_id}/escalations", response_model=ResponseSchema)
async def get_escalations(
    project_id: int,
    resolved: Optional[bool] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get escalation alerts for a project"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        query = db.query(EscalationAlert).filter(EscalationAlert.project_id == project_id)
        
        if resolved is not None:
            query = query.filter(EscalationAlert.is_resolved == resolved)
        
        escalations = query.order_by(EscalationAlert.created_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "data": [{
                "id": e.id,
                "escalation_level": e.escalation_level,
                "escalation_reason": e.escalation_reason,
                "severity": e.severity,
                "description": e.description,
                "is_resolved": e.is_resolved,
                "created_at": e.created_at,
                "acknowledged_at": e.acknowledged_at,
                "recommended_actions": e.recommended_actions
            } for e in escalations]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching escalations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/escalations/{esc_id}/acknowledge", response_model=ResponseSchema)
async def acknowledge_escalation(
    project_id: int,
    esc_id: int,
    user_id: int = None,
    db: Session = Depends(get_db)
):
    """Acknowledge an escalation"""
    try:
        escalation = db.query(EscalationAlert).filter(
            EscalationAlert.id == esc_id,
            EscalationAlert.project_id == project_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        EscalationManager.acknowledge_escalation(db, esc_id, user_id)
        
        return {
            "success": True,
            "message": "Escalation acknowledged"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging escalation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/escalations/{esc_id}/resolve", response_model=ResponseSchema)
async def resolve_escalation(
    project_id: int,
    esc_id: int,
    user_id: int = None,
    resolution_notes: str = "",
    db: Session = Depends(get_db)
):
    """Resolve an escalation"""
    try:
        escalation = db.query(EscalationAlert).filter(
            EscalationAlert.id == esc_id,
            EscalationAlert.project_id == project_id
        ).first()
        
        if not escalation:
            raise HTTPException(status_code=404, detail="Escalation not found")
        
        EscalationManager.resolve_escalation(db, esc_id, user_id, resolution_notes)
        
        return {
            "success": True,
            "message": "Escalation resolved"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving escalation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== TEMPLATES ENDPOINTS ====================

@router.get("/templates", response_model=ResponseSchema)
async def get_templates(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get status update templates"""
    try:
        query = db.query(StatusUpdateTemplate)
        
        if project_id:
            query = query.filter(StatusUpdateTemplate.project_id == project_id)
        
        templates = query.all()
        
        return {
            "success": True,
            "data": [{
                "id": t.id,
                "name": t.name,
                "frequency": t.frequency,
                "recipient_roles": t.recipient_roles,
                "is_active": t.is_active
            } for t in templates]
        }
    except Exception as e:
        logger.error(f"Error fetching templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates", response_model=ResponseSchema)
async def create_template(
    name: str,
    frequency: str,
    project_id: Optional[int] = None,
    day_of_week: Optional[str] = None,
    time_of_day: str = "09:00",
    recipient_roles: List[str] = None,
    db: Session = Depends(get_db)
):
    """Create a status update template"""
    try:
        template = StatusUpdateTemplate(
            name=name,
            frequency=frequency,
            project_id=project_id,
            day_of_week=day_of_week,
            time_of_day=time_of_day,
            recipient_roles=recipient_roles or ["project_manager", "stakeholder"],
            is_active=True
        )
        
        db.add(template)
        db.commit()
        
        return {
            "success": True,
            "message": "Template created successfully",
            "data": {"template_id": template.id}
        }
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SCHEDULER ENDPOINTS ====================

@router.post("/batch/generate", response_model=ResponseSchema)
async def batch_generate_updates(
    db: Session = Depends(get_db)
):
    """Batch generate status updates for all projects"""
    try:
        count = StatusUpdateGenerator.batch_generate_updates(db)
        
        return {
            "success": True,
            "message": f"Generated {count} status updates",
            "data": {"generated_count": count}
        }
    except Exception as e:
        logger.error(f"Error batch generating updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/check-escalations", response_model=ResponseSchema)
async def batch_check_escalations(
    db: Session = Depends(get_db)
):
    """Check all projects for escalation conditions"""
    try:
        count = EscalationManager.batch_check_escalations(db)
        
        return {
            "success": True,
            "message": f"Created {count} escalation alerts",
            "data": {"escalations_created": count}
        }
    except Exception as e:
        logger.error(f"Error batch checking escalations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== NOTIFICATIONS ENDPOINTS ====================

@router.get("/notifications", response_model=ResponseSchema)
async def get_notifications(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get notification logs for a user"""
    try:
        notifications = db.query(NotificationLog).filter(
            NotificationLog.recipient_id == user_id
        ).order_by(NotificationLog.scheduled_at.desc()).limit(limit).all()
        
        return {
            "success": True,
            "data": [{
                "id": n.id,
                "notification_type": n.notification_type,
                "subject": n.subject,
                "channel": n.channel,
                "delivery_status": n.delivery_status,
                "scheduled_at": n.scheduled_at,
                "opened_at": n.opened_at
            } for n in notifications]
        }
    except Exception as e:
        logger.error(f"Error fetching notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Simple alias for import in main app
NotificationManager = StatusNotificationManager

