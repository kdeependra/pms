"""
Phase 4: Escalation Management Service
Handles escalation workflows triggered by status issues
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.models import (
    EscalationAlert, StatusUpdate, Project, Task, NotificationLog, User,
    Alert, AlertTemplate, ProgressUpdate
)

logger = logging.getLogger(__name__)


class EscalationLevel:
    """Escalation severity levels"""
    LEVEL_1 = "level_1"      # Team lead
    LEVEL_2 = "level_2"      # Project manager
    LEVEL_3 = "level_3"      # Director
    EXECUTIVE = "executive"  # Executive sponsor


class EscalationReason:
    """Reasons for escalation"""
    DELAY_THRESHOLD = "delay_threshold_exceeded"
    BUDGET_WARNING = "budget_warning"
    RISK_IDENTIFIED = "risk_identified"
    BLOCKING_ISSUE = "blocking_issue"
    QUALITY_CONCERN = "quality_concern"
    RESOURCE_CRISIS = "resource_crisis"
    STAKEHOLDER_CONCERN = "stakeholder_concern"


class EscalationConfig:
    """Configuration for escalation thresholds"""
    
    THRESHOLDS = {
        "schedule_variance": -20,           # Days behind schedule to trigger
        "budget_variance": 25,              # Percentage over budget
        "blocked_tasks": 5,                 # Number of blocked tasks
        "overdue_tasks": 3,                 # Number of overdue tasks
        "consecutive_red": 2,               # Red status updates in a row
        "status_change_frequency": 5        # Status changes in a week
    }
    
    # Determine escalation level by severity
    SEVERITY_ESCALATION = {
        "low": EscalationLevel.LEVEL_1,
        "medium": EscalationLevel.LEVEL_2,
        "high": EscalationLevel.LEVEL_3,
        "critical": EscalationLevel.EXECUTIVE
    }


class EscalationDetector:
    """Identifies when escalations are needed"""
    
    @staticmethod
    def check_escalation_conditions(session: Session, project_id: int, status_update: StatusUpdate) -> Optional[Dict[str, Any]]:
        """Check if escalation is needed"""
        
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            return None
        
        progress = session.query(ProgressUpdate).filter(ProgressUpdate.project_id == project_id).first()
        if not progress:
            return None
        
        # Check various escalation conditions
        escalation_data = {
            "triggered_reasons": [],
            "severity": "low",
            "metrics": {}
        }
        
        # Check 1: Schedule Variance
        if status_update.schedule_variance and status_update.schedule_variance < EscalationConfig.THRESHOLDS["schedule_variance"]:
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.DELAY_THRESHOLD,
                "metric": f"Schedule variance: {status_update.schedule_variance:.1f} days",
                "severity": "high"
            })
            escalation_data["metrics"]["schedule_variance"] = status_update.schedule_variance
            escalation_data["severity"] = "high"
        
        # Check 2: Budget Variance
        if status_update.budget_variance and status_update.budget_variance > EscalationConfig.THRESHOLDS["budget_variance"]:
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.BUDGET_WARNING,
                "metric": f"Budget overspend: {status_update.budget_variance:.1f}%",
                "severity": "high"
            })
            escalation_data["metrics"]["budget_variance"] = status_update.budget_variance
            escalation_data["severity"] = "high"
        
        # Check 3: Blocked Tasks
        if progress.blocked_tasks >= EscalationConfig.THRESHOLDS["blocked_tasks"]:
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.BLOCKING_ISSUE,
                "metric": f"Blocked tasks: {progress.blocked_tasks}",
                "severity": "high"
            })
            escalation_data["metrics"]["blocked_tasks"] = progress.blocked_tasks
            if progress.blocked_tasks >= 10:
                escalation_data["severity"] = "critical"
        
        # Check 4: Overdue Tasks
        if progress.tasks_overdue >= EscalationConfig.THRESHOLDS["overdue_tasks"]:
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.BLOCKING_ISSUE,
                "metric": f"Overdue tasks: {progress.tasks_overdue}",
                "severity": "medium"
            })
            escalation_data["metrics"]["overdue_tasks"] = progress.tasks_overdue
            if escalation_data["severity"] != "critical":
                escalation_data["severity"] = "medium"
        
        # Check 5: Status Health Pattern
        if status_update.health == "red":
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.RISK_IDENTIFIED,
                "metric": f"Project health: RED",
                "severity": "high"
            })
            escalation_data["severity"] = "high"
        
        # Check 6: Consecutive Red Updates
        consecutive_red = session.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id,
            StatusUpdate.health == "red",
            StatusUpdate.generated_at > datetime.utcnow() - timedelta(weeks=1)
        ).count()
        
        if consecutive_red >= EscalationConfig.THRESHOLDS["consecutive_red"]:
            escalation_data["triggered_reasons"].append({
                "reason": EscalationReason.RISK_IDENTIFIED,
                "metric": f"Consecutive red updates: {consecutive_red}",
                "severity": "critical"
            })
            escalation_data["metrics"]["consecutive_red"] = consecutive_red
            escalation_data["severity"] = "critical"
        
        return escalation_data if escalation_data["triggered_reasons"] else None
    
    @staticmethod
    def should_escalate(session: Session, project_id: int) -> bool:
        """Check if project should be escalated"""
        
        # Get latest status update
        latest_update = session.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id,
            StatusUpdate.is_published == True
        ).order_by(StatusUpdate.published_at.desc()).first()
        
        if not latest_update:
            return False
        
        # Check if already escalated recently
        recent_escalation = session.query(EscalationAlert).filter(
            EscalationAlert.project_id == project_id,
            EscalationAlert.created_at > datetime.utcnow() - timedelta(days=1)
        ).first()
        
        if recent_escalation:
            return False
        
        # Check conditions
        escalation_data = EscalationDetector.check_escalation_conditions(session, project_id, latest_update)
        return escalation_data is not None


class EscalationManager:
    """Manages escalation creation and workflow"""
    
    @staticmethod
    def create_escalation(session: Session, project_id: int, 
                         status_update: StatusUpdate, 
                         escalation_data: Dict[str, Any]) -> EscalationAlert:
        """Create escalation alert"""
        
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        severity = escalation_data.get("severity", "medium")
        escalation_level = EscalationConfig.SEVERITY_ESCALATION.get(severity, EscalationLevel.LEVEL_2)
        
        # Determine escalation targets
        escalate_to_roles = []
        escalate_to_users = []
        
        if escalation_level == EscalationLevel.LEVEL_1:
            escalate_to_roles = ["project_manager"]
        elif escalation_level == EscalationLevel.LEVEL_2:
            escalate_to_roles = ["project_manager", "stakeholder"]
        elif escalation_level == EscalationLevel.LEVEL_3:
            escalate_to_roles = ["project_manager", "stakeholder"]
            # Add project owner
            if project.owner_id:
                escalate_to_users.append(project.owner_id)
        elif escalation_level == EscalationLevel.EXECUTIVE:
            escalate_to_roles = ["admin", "project_manager"]
            if project.owner_id:
                escalate_to_users.append(project.owner_id)
        
        # Prepare reasons
        escalation_reasons = []
        for reason_data in escalation_data.get("triggered_reasons", []):
            escalation_reasons.append(reason_data["reason"])
        
        primary_reason = escalation_reasons[0] if escalation_reasons else EscalationReason.RISK_IDENTIFIED
        
        # Recommended actions
        recommended_actions = []
        for reason_data in escalation_data.get("triggered_reasons", []):
            if reason_data["reason"] == EscalationReason.DELAY_THRESHOLD:
                recommended_actions.extend([
                    "Review critical path and adjust timeline",
                    "Allocate additional resources",
                    "Communicate with stakeholders"
                ])
            elif reason_data["reason"] == EscalationReason.BUDGET_WARNING:
                recommended_actions.extend([
                    "Conduct cost reduction review",
                    "Negotiate supplier contracts",
                    "Request budget review from sponsor"
                ])
            elif reason_data["reason"] == EscalationReason.BLOCKING_ISSUE:
                recommended_actions.extend([
                    "Identify and remove blockers",
                    "Escalate dependency issues",
                    "Reallocate resources"
                ])
        
        # Create escalation
        escalation = EscalationAlert(
            project_id=project_id,
            status_update_id=status_update.id,
            escalation_level=escalation_level,
            escalation_reason=primary_reason,
            severity=severity,
            escalate_to_roles=json.dumps(escalate_to_roles),
            escalate_to_users=json.dumps(escalate_to_users),
            description=f"Project escalation due to: {', '.join(escalation_reasons)}",
            current_metrics=json.dumps(escalation_data.get("metrics", {})),
            thresholds_exceeded=json.dumps([r["metric"] for r in escalation_data.get("triggered_reasons", [])]),
            recommended_actions=json.dumps(recommended_actions)
        )
        
        session.add(escalation)
        session.commit()
        
        logger.warning(f"Created escalation for project {project_id} at level {escalation_level}: {primary_reason}")
        return escalation
    
    @staticmethod
    def acknowledge_escalation(session: Session, escalation_id: int, user_id: int, notes: str = ""):
        """Mark escalation as acknowledged"""
        
        escalation = session.query(EscalationAlert).filter(EscalationAlert.id == escalation_id).first()
        if not escalation:
            raise ValueError(f"Escalation {escalation_id} not found")
        
        escalation.acknowledged_at = datetime.utcnow()
        escalation.acknowledged_by = user_id
        session.commit()
        
        logger.info(f"Escalation {escalation_id} acknowledged by user {user_id}")
    
    @staticmethod
    def resolve_escalation(session: Session, escalation_id: int, user_id: int, notes: str):
        """Mark escalation as resolved"""
        
        escalation = session.query(EscalationAlert).filter(EscalationAlert.id == escalation_id).first()
        if not escalation:
            raise ValueError(f"Escalation {escalation_id} not found")
        
        escalation.is_resolved = True
        escalation.resolved_at = datetime.utcnow()
        escalation.resolved_by = user_id
        escalation.resolution_notes = notes
        session.commit()
        
        logger.info(f"Escalation {escalation_id} resolved by user {user_id}")
    
    @staticmethod
    def batch_check_escalations(session: Session):
        """Check all active projects for escalations"""
        
        from app.models.models import Project
        
        projects = session.query(Project).filter(
            Project.status.in_(["active", "planning"])
        ).all()
        
        escalations_created = 0
        
        for project in projects:
            try:
                if EscalationDetector.should_escalate(session, project.id):
                    latest_update = session.query(StatusUpdate).filter(
                        StatusUpdate.project_id == project.id,
                        StatusUpdate.is_published == True
                    ).order_by(StatusUpdate.published_at.desc()).first()
                    
                    escalation_data = EscalationDetector.check_escalation_conditions(
                        session, project.id, latest_update
                    )
                    
                    if escalation_data:
                        EscalationManager.create_escalation(session, project.id, latest_update, escalation_data)
                        escalations_created += 1
                        
                        # Notify stakeholders
                        EscalationManager.notify_escalation(session, project.id, escalation_data)
            except Exception as e:
                logger.error(f"Error checking escalation for project {project.id}: {e}")
        
        return escalations_created
    
    @staticmethod
    def notify_escalation(session: Session, project_id: int, escalation_data: Dict[str, Any]):
        """Send notifications about escalation"""
        
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            return
        
        # Get latest escalation
        escalation = session.query(EscalationAlert).filter(
            EscalationAlert.project_id == project_id
        ).order_by(EscalationAlert.created_at.desc()).first()
        
        if not escalation:
            return
        
        # Get target users
        roles = json.loads(escalation.escalate_to_roles) if isinstance(escalation.escalate_to_roles, str) else escalation.escalate_to_roles
        user_ids = json.loads(escalation.escalate_to_users) if isinstance(escalation.escalate_to_users, str) else escalation.escalate_to_users
        
        recipients = []
        
        # Get users by role
        if roles:
            role_users = session.query(User).filter(User.role.in_(roles)).all()
            recipients.extend(role_users)
        
        # Get specific users
        if user_ids:
            specific_users = session.query(User).filter(User.id.in_(user_ids)).all()
            recipients.extend(specific_users)
        
        # Create notifications
        for recipient in set(recipients):
            notification = NotificationLog(
                escalation_alert_id=escalation.id,
                recipient_id=recipient.id,
                recipient_role=recipient.role,
                notification_type="escalation",
                channel="email",
                subject=f"🚨 ESCALATION: {project.name} - {escalation.escalation_reason}",
                content=escalation.description or "",
                delivery_status="pending"
            )
            session.add(notification)
        
        session.commit()
        logger.info(f"Sent {len(set(recipients))} escalation notifications for project {project_id}")


class BiDirectionalIntegration:
    """Handles bidirectional integration between Status Updates and Alerts"""
    
    @staticmethod
    def status_change_triggers_alert(session: Session, project_id: int, 
                                     old_status: str, new_status: str):
        """Create alert when status changes"""
        
        if old_status == new_status:
            return None
        
        # Create corresponding alert
        status_alert_map = {
            "on_track": "status_on_track",
            "at_risk": "status_at_risk",
            "off_track": "status_off_track",
            "blocked": "status_blocked"
        }
        
        alert_type = status_alert_map.get(new_status)
        if not alert_type:
            return None
        
        # Check if template exists
        template = session.query(AlertTemplate).filter(
            AlertTemplate.alert_type == alert_type
        ).first()
        
        if not template:
            # Create template if needed
            template = AlertTemplate(
                alert_type=alert_type,
                title=f"Project Status Changed: {new_status.replace('_', ' ').title()}",
                description=f"Project status has changed to {new_status}",
                default_priority="high" if new_status in ["at_risk", "off_track", "blocked"] else "medium"
            )
            session.add(template)
            session.commit()
        
        # Create alert
        from app.models.models import Alert
        
        alert = Alert(
            project_id=project_id,
            template_id=template.id,
            alert_type=alert_type,
            title=template.title,
            priority="high" if new_status in ["at_risk", "off_track", "blocked"] else "medium",
            urgency_score=0.8 if new_status == "off_track" else 0.6,
            description=f"Project status changed from {old_status} to {new_status}",
            entity_type="project",
            entity_id=project_id,
            is_predictive=False,
            delivery_status="pending"
        )
        
        session.add(alert)
        session.commit()
        
        logger.info(f"Created alert for project {project_id} status change: {old_status} -> {new_status}")
        return alert
    
    @staticmethod
    def alert_recommendations_sync(session: Session, project_id: int):
        """Sync relevant alerts to status recommendations"""
        
        # Get recent alerts for this project
        recent_alerts = session.query(Alert).filter(
            Alert.project_id == project_id,
            Alert.created_at > datetime.utcnow() - timedelta(days=7),
            Alert.alert_type.in_([
                "task_delay", "budget_overrun", "team_stress", 
                "scope_creep", "conflict_escalation"
            ])
        ).all()
        
        # Get latest status update
        status_update = session.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id
        ).order_by(StatusUpdate.generated_at.desc()).first()
        
        if not status_update or not recent_alerts:
            return 0
        
        # Create recommendations based on alerts
        from app.services.status_update_service import StatusRecommendationEngine
        
        for alert in recent_alerts:
            # Check if recommendation already exists
            existing = session.query(StatusRecommendation).filter(
                and_(
                    StatusRecommendation.project_id == project_id,
                    StatusRecommendation.status_update_id == status_update.id,
                    StatusRecommendation.description.like(f"%{alert.alert_type}%")
                )
            ).first()
            
            if existing:
                continue
            
            # Create recommendation from alert
            rec_type_map = {
                "task_delay": "timeline_adjustment",
                "budget_overrun": "risk_mitigation",
                "team_stress": "resource_reallocation",
                "scope_creep": "timeline_adjustment",
                "conflict_escalation": "resource_reallocation"
            }
            
            rec = StatusRecommendation(
                project_id=project_id,
                status_update_id=status_update.id,
                recommendation_type=rec_type_map.get(alert.alert_type, "risk_mitigation"),
                current_status=status_update.status,
                recommended_status=status_update.status,
                reason=f"Based on alert: {alert.description}",
                confidence=alert.urgency_score or 0.75,
                impact=alert.priority,
                suggested_actions=json.dumps([alert.description]),
                estimated_effort="medium"
            )
            
            session.add(rec)
        
        session.commit()
        logger.info(f"Synced {len(recent_alerts)} alerts to status recommendations")
        return len(recent_alerts)

