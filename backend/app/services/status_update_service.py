"""
Phase 4: Automated Status Updates Service
Handles daily/weekly status generation, progress calculation, recommendations, and escalations
"""

from datetime import datetime, timedelta, time as datetime_time
from typing import Optional, List, Dict, Any
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import logging

from app.models.models import (
    Project, Task, StatusUpdate, StatusUpdateTemplate, ProgressUpdate,
    StatusRecommendation, EscalationAlert, NotificationLog, UpdateFrequency,
    User, Alert, AlertTemplate, TimeLog
)

logger = logging.getLogger(__name__)


class ProgressCalculator:
    """Calculates project progress using multiple methods"""
    
    @staticmethod
    def calculate_task_progress(session: Session, project_id: int) -> Dict[str, Any]:
        """Calculate progress from task completion"""
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        
        if not tasks:
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "in_progress_tasks": 0,
                "blocked_tasks": 0,
                "task_progress": 0,
                "task_completion_rate": 0
            }
        
        completed = sum(1 for t in tasks if t.status == "done")
        in_progress = sum(1 for t in tasks if t.status == "in_progress")
        blocked = sum(1 for t in tasks if t.status == "blocked")
        
        # Simple completion rate
        completion_rate = (completed / len(tasks)) * 100 if tasks else 0
        
        # Weighted progress by priority
        weighted_progress = 0
        priority_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        total_weight = sum(priority_weights.get(t.priority, 1) for t in tasks)
        
        for task in tasks:
            weight = priority_weights.get(task.priority, 1)
            if task.status == "done":
                weighted_progress += weight * 100
            elif task.status == "in_progress":
                weighted_progress += weight * (task.progress or 0)
        
        if total_weight > 0:
            weighted_progress = (weighted_progress / total_weight)
        
        return {
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "blocked_tasks": blocked,
            "task_progress": int(completion_rate),
            "weighted_progress": round(weighted_progress, 1),
            "task_completion_rate": int(completion_rate)
        }
    
    @staticmethod
    def calculate_estimated_progress(session: Session, project_id: int) -> float:
        """Calculate progress from hours logged vs estimated"""
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        
        total_estimated = sum(t.estimated_hours or 0 for t in tasks)
        total_logged = 0
        
        for task in tasks:
            logs = session.query(TimeLog).filter(TimeLog.task_id == task.id).all()
            total_logged += sum(log.hours for log in logs)
        
        if total_estimated > 0:
            return min(100, (total_logged / total_estimated) * 100)
        return 0
    
    @staticmethod
    def calculate_timeline_progress(session: Session, project_id: int) -> Dict[str, Any]:
        """Calculate progress based on schedule adherence"""
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project or not project.start_date or not project.end_date:
            return {"schedule_variance": 0, "days_elapsed": 0, "days_remaining": 0}
        
        now = datetime.utcnow()
        days_elapsed = (now - project.start_date).days
        total_duration = (project.end_date - project.start_date).days
        schedule_progress = (days_elapsed / total_duration * 100) if total_duration > 0 else 0
        
        # Compare with task progress
        task_data = ProgressCalculator.calculate_task_progress(session, project_id)
        schedule_variance = task_data["task_progress"] - schedule_progress
        
        days_remaining = (project.end_date - now).days
        
        return {
            "schedule_variance": round(schedule_variance, 1),
            "days_elapsed": days_elapsed,
            "days_remaining": max(0, days_remaining),
            "scheduled_progress": round(schedule_progress, 1),
            "actual_progress": task_data["task_progress"]
        }
    
    @staticmethod
    def calculate_budget_progress(session: Session, project_id: int) -> Dict[str, Any]:
        """Calculate budget variance"""
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project or not project.budget:
            return {"budget_variance": 0, "budget_spent": 0, "budget_remaining": 0}
        
        spent_percentage = (project.actual_cost / project.budget * 100) if project.budget > 0 else 0
        
        # Get task progress to determine expected spend
        task_data = ProgressCalculator.calculate_task_progress(session, project_id)
        expected_spend_percentage = task_data["task_progress"]
        
        budget_variance = spent_percentage - expected_spend_percentage
        
        return {
            "budget_variance": round(budget_variance, 1),
            "budget_spent": project.actual_cost,
            "budget_remaining": project.budget - project.actual_cost,
            "spent_percentage": round(spent_percentage, 1),
            "expected_percentage": round(expected_spend_percentage, 1)
        }
    
    @staticmethod
    def update_progress_record(session: Session, project_id: int):
        """Update ProgressUpdate record in database"""
        progress_record = session.query(ProgressUpdate).filter(
            ProgressUpdate.project_id == project_id
        ).first()
        
        if not progress_record:
            progress_record = ProgressUpdate(project_id=project_id)
            session.add(progress_record)
        
        # Calculate all metrics
        task_data = ProgressCalculator.calculate_task_progress(session, project_id)
        timeline_data = ProgressCalculator.calculate_timeline_progress(session, project_id)
        budget_data = ProgressCalculator.calculate_budget_progress(session, project_id)
        hours_estimated = ProgressCalculator.calculate_estimated_hours(session, project_id)
        
        # Update record
        progress_record.total_tasks = task_data["total_tasks"]
        progress_record.completed_tasks = task_data["completed_tasks"]
        progress_record.in_progress_tasks = task_data["in_progress_tasks"]
        progress_record.blocked_tasks = task_data["blocked_tasks"]
        progress_record.weighted_progress = task_data["weighted_progress"]
        progress_record.calculated_progress = ProgressCalculator.calculate_estimated_progress(session, project_id)
        
        progress_record.tasks_on_schedule = task_data["total_tasks"] - task_data["blocked_tasks"]
        progress_record.tasks_at_risk = max(0, sum(1 for t in session.query(Task).filter(
            Task.project_id == project_id,
            Task.progress < 50,
            Task.due_date <= datetime.utcnow() + timedelta(days=7)
        ).all()))
        progress_record.tasks_overdue = sum(1 for t in session.query(Task).filter(
            Task.project_id == project_id,
            Task.status != "done",
            Task.due_date <= datetime.utcnow()
        ).all())
        
        progress_record.hours_estimated = hours_estimated["estimated"]
        progress_record.hours_logged = hours_estimated["logged"]
        progress_record.hours_remaining = hours_estimated["remaining"]
        
        progress_record.last_updated = datetime.utcnow()
        
        session.commit()
        return progress_record
    
    @staticmethod
    def calculate_estimated_hours(session: Session, project_id: int) -> Dict[str, float]:
        """Calculate estimated vs logged hours"""
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        
        total_estimated = sum(t.estimated_hours or 0 for t in tasks)
        total_logged = 0
        
        for task in tasks:
            logs = session.query(TimeLog).filter(TimeLog.task_id == task.id).all()
            total_logged += sum(log.hours or 0 for log in logs)
        
        total_remaining = max(0, total_estimated - total_logged)
        
        return {
            "estimated": total_estimated,
            "logged": total_logged,
            "remaining": total_remaining
        }


class StatusDetector:
    """Detects project status and health from metrics"""
    
    STATUS_RULES = {
        "on_track": {
            "progress_variance": (-10, 10),  # +/- 10% acceptable
            "budget_variance": (-15, 15),
            "overdue_tasks": (0, 3),
            "blocked_tasks": 0
        },
        "at_risk": {
            "progress_variance": (-30, -10),  # Behind schedule
            "budget_variance": (-30, 30),     # Over/under budget
            "overdue_tasks": (1, 5),
            "blocked_tasks": (1, 3)
        },
        "off_track": {
            "progress_variance": (-100, -30),  # Significantly behind
            "budget_variance": (20, 100),      # Over budget
            "overdue_tasks": (5, 100),
            "blocked_tasks": (3, 100)
        },
        "blocked": {
            "blocked_tasks": (10, 100)  # Many blocked tasks
        },
        "completed": {}
    }
    
    @staticmethod
    def detect_status(session: Session, project_id: int) -> tuple:
        """Detect project status and health level"""
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            return "unknown", "gray"
        
        if project.status == "completed":
            return "completed", "green"
        
        progress_update = session.query(ProgressUpdate).filter(
            ProgressUpdate.project_id == project_id
        ).first()
        
        if not progress_update:
            return "unknown", "gray"
        
        # Calculate current metrics
        timeline_data = ProgressCalculator.calculate_timeline_progress(session, project_id)
        budget_data = ProgressCalculator.calculate_budget_progress(session, project_id)
        task_progress = ProgressCalculator.calculate_task_progress(session, project_id)
        
        progress_variance = task_progress["task_progress"] - timeline_data["scheduled_progress"]
        
        # Determine status (check rules in order)
        detected_status = "on_track"
        
        if task_progress["blocked_tasks"] >= 10:
            detected_status = "blocked"
        elif (progress_variance < -30 or 
              budget_data["budget_variance"] > 20 or 
              progress_update.tasks_overdue > 5):
            detected_status = "off_track"
        elif (progress_variance < -10 or 
              abs(budget_data["budget_variance"]) > 15 or 
              progress_update.tasks_at_risk > 3):
            detected_status = "at_risk"
        
        # Determine health color
        health_colors = {
            "on_track": "green",
            "at_risk": "yellow",
            "off_track": "red",
            "blocked": "red",
            "completed": "green",
            "unknown": "gray"
        }
        
        return detected_status, health_colors.get(detected_status, "gray")
    
    @staticmethod
    def generate_health_summary(session: Session, project_id: int) -> Dict[str, Any]:
        """Generate detailed health summary"""
        status, health = StatusDetector.detect_status(session, project_id)
        progress_update = session.query(ProgressUpdate).filter(
            ProgressUpdate.project_id == project_id
        ).first()
        
        summary = {
            "status": status,
            "health": health,
            "overall_progress": progress_update.weighted_progress if progress_update else 0,
            "on_time": True,
            "on_budget": True,
            "key_metrics": {}
        }
        
        if progress_update:
            timeline_data = ProgressCalculator.calculate_timeline_progress(session, project_id)
            budget_data = ProgressCalculator.calculate_budget_progress(session, project_id)
            
            summary["on_time"] = timeline_data["schedule_variance"] >= -10
            summary["on_budget"] = budget_data["budget_variance"] <= 20
            
            summary["key_metrics"] = {
                "progress": progress_update.weighted_progress,
                "schedule_variance": timeline_data["schedule_variance"],
                "budget_variance": budget_data["budget_variance"],
                "overdue_tasks": progress_update.tasks_overdue,
                "blocked_tasks": progress_update.blocked_tasks,
                "hours_logged": progress_update.hours_logged
            }
        
        return summary


class StatusUpdateGenerator:
    """Generates automated status updates"""
    
    @staticmethod
    def should_generate_update(session: Session, project_id: int, template: StatusUpdateTemplate) -> bool:
        """Check if update should be generated based on schedule"""
        now = datetime.utcnow()
        
        # Check last update time
        last_update = session.query(StatusUpdate).filter(
            StatusUpdate.project_id == project_id,
            StatusUpdate.is_published == True
        ).order_by(StatusUpdate.published_at.desc()).first()
        
        if not last_update:
            return True
        
        # Calculate days since last update
        days_since = (now - last_update.published_at).days if last_update.published_at else 0
        
        # Based on frequency
        frequency_days = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30
        }
        
        required_days = frequency_days.get(template.frequency, 7)
        return days_since >= required_days
    
    @staticmethod
    def generate_update(session: Session, project_id: int, template: Optional[StatusUpdateTemplate] = None) -> StatusUpdate:
        """Generate a new status update"""
        
        # Update progress record first
        ProgressCalculator.update_progress_record(session, project_id)
        
        # Detect status and health
        status, health = StatusDetector.detect_status(session, project_id)
        health_summary = StatusDetector.generate_health_summary(session, project_id)
        
        # Get progress data
        progress_data = session.query(ProgressUpdate).filter(
            ProgressUpdate.project_id == project_id
        ).first()
        
        # Create update
        update = StatusUpdate(
            project_id=project_id,
            template_id=template.id if template else None,
            status=status,
            health=health,
            overall_progress=int(progress_data.weighted_progress) if progress_data else 0,
            task_progress=progress_data.total_tasks if progress_data else 0,
            generated_by="automated"
        )
        
        # Generate summary
        summary_parts = []
        
        if progress_data:
            timeline_data = ProgressCalculator.calculate_timeline_progress(session, project_id)
            budget_data = ProgressCalculator.calculate_budget_progress(session, project_id)
            
            update.schedule_variance = timeline_data["schedule_variance"]
            update.budget_variance = budget_data["budget_variance"]
            
            # Summary text
            summary_parts.append(f"Project Status: {status.replace('_', ' ').title()}")
            summary_parts.append(f"Overall Progress: {progress_data.weighted_progress}%")
            
            if progress_data.tasks_overdue > 0:
                summary_parts.append(f"⚠️ {progress_data.tasks_overdue} tasks are overdue")
            
            if budget_data["budget_variance"] > 15:
                summary_parts.append(f"💰 Budget concern: {budget_data['budget_variance']:.1f}% overspend")
            
            if progress_data.blocked_tasks > 0:
                summary_parts.append(f"🚫 {progress_data.blocked_tasks} tasks are blocked")
        
        update.summary = "\n".join(summary_parts)
        
        # Generate highlights and concerns
        highlights = []
        concerns = []
        
        if health == "green":
            highlights.append("Project tracking well overall")
        if progress_data and progress_data.completed_tasks > 0:
            highlights.append(f"{progress_data.completed_tasks} tasks completed this period")
        
        if status == "at_risk":
            concerns.append("Project trending toward risk")
        if status == "off_track":
            concerns.append("Project is significantly off track")
        if progress_data and progress_data.tasks_overdue > 0:
            concerns.append(f"{progress_data.tasks_overdue} overdue tasks need attention")
        
        update.highlights = json.dumps(highlights)
        update.concerns = json.dumps(concerns)
        
        session.add(update)
        session.commit()
        
        logger.info(f"Generated status update for project {project_id}: {status}")
        return update
    
    @staticmethod
    def batch_generate_updates(session: Session):
        """Generate updates for all active projects with templates"""
        templates = session.query(StatusUpdateTemplate).filter(
            StatusUpdateTemplate.is_active == True
        ).all()
        
        generated = 0
        for template in templates:
            project_ids = [template.project_id] if template.project_id else (
                session.query(Project.id).filter(Project.status.in_(["active", "planning"])).all()
            )
            
            for (project_id,) in project_ids:
                try:
                    if StatusUpdateGenerator.should_generate_update(session, project_id, template):
                        StatusUpdateGenerator.generate_update(session, project_id, template)
                        generated += 1
                except Exception as e:
                    logger.error(f"Failed to generate update for project {project_id}: {e}")
        
        return generated


class StatusRecommendationEngine:
    """Generates AI recommendations for status changes and actions"""
    
    @staticmethod
    def analyze_and_recommend(session: Session, project_id: int, status_update_id: int) -> List[StatusRecommendation]:
        """Analyze status and generate recommendations"""
        
        status_update = session.query(StatusUpdate).filter(StatusUpdate.id == status_update_id).first()
        if not status_update:
            return []
        
        recommendations = []
        
        # Get current metrics
        progress_data = session.query(ProgressUpdate).filter(
            ProgressUpdate.project_id == project_id
        ).first()
        
        timeline_data = ProgressCalculator.calculate_timeline_progress(session, project_id)
        budget_data = ProgressCalculator.calculate_budget_progress(session, project_id)
        
        # Recommendation 1: Schedule Risk
        if timeline_data["schedule_variance"] < -20:
            rec = StatusRecommendation(
                project_id=project_id,
                status_update_id=status_update_id,
                recommendation_type="timeline_adjustment",
                current_status=status_update.status,
                recommended_status="at_risk",
                reason=f"Project is {abs(timeline_data['schedule_variance']):.1f}% behind schedule. "
                       f"With {timeline_data['days_remaining']} days remaining, timeline adjustment may be needed.",
                confidence=0.85 if timeline_data["schedule_variance"] < -30 else 0.70,
                impact="high" if timeline_data["schedule_variance"] < -30 else "medium",
                suggested_actions=[
                    "Identify critical path tasks and prioritize completion",
                    "Allocate additional resources to high-risk activities",
                    "Review scope and consider de-prioritizing non-critical items",
                    "Communicate timeline concerns to stakeholders"
                ],
                estimated_effort="large"
            )
            session.add(rec)
            recommendations.append(rec)
        
        # Recommendation 2: Budget Risk
        if budget_data["budget_variance"] > 25:
            rec = StatusRecommendation(
                project_id=project_id,
                status_update_id=status_update_id,
                recommendation_type="risk_mitigation",
                current_status=status_update.status,
                recommended_status="at_risk",
                reason=f"Budget overspend of {budget_data['budget_variance']:.1f}%. "
                       f"${budget_data['budget_remaining']} of budget remains.",
                confidence=0.90,
                impact="high",
                suggested_actions=[
                    "Cost reduction review - identify efficiency improvements",
                    "Negotiate supplier contracts for cost savings",
                    "Replan resource utilization to optimize costs",
                    "Request budget increase or scope reduction from sponsor"
                ],
                estimated_effort="medium"
            )
            session.add(rec)
            recommendations.append(rec)
        
        # Recommendation 3: Resource Reallocation
        if progress_data and progress_data.blocked_tasks > 5:
            rec = StatusRecommendation(
                project_id=project_id,
                status_update_id=status_update_id,
                recommendation_type="resource_reallocation",
                current_status=status_update.status,
                recommended_status="at_risk",
                reason=f"{progress_data.blocked_tasks} tasks are blocked, preventing progress. "
                       f"Resource conflicts or dependencies may exist.",
                confidence=0.80,
                impact="high",
                suggested_actions=[
                    "Review blockers on each stuck task",
                    "Reassign resources from lower-priority tasks",
                    "Resolve dependency chains with other projects",
                    "Escalate resource conflicts to PMO"
                ],
                estimated_effort="medium"
            )
            session.add(rec)
            recommendations.append(rec)
        
        # Recommendation 4: Status Change
        if status_update.status == "off_track" and timeline_data["schedule_variance"] > -15:
            rec = StatusRecommendation(
                project_id=project_id,
                status_update_id=status_update_id,
                recommendation_type="status_change",
                current_status="off_track",
                recommended_status="at_risk",
                reason="Positive trend detected. With recent improvements, status may be downgraded to 'at_risk'.",
                confidence=0.75,
                impact="low",
                suggested_actions=[
                    "Acknowledge improvements to the team",
                    "Maintain current momentum by removing blockers",
                    "Continue monitoring closely"
                ],
                estimated_effort="small"
            )
            session.add(rec)
            recommendations.append(rec)
        
        session.commit()
        return recommendations


class StatusNotificationManager:
    """Manages notifications to stakeholders"""
    
    @staticmethod
    def notify_stakeholders(session: Session, status_update_id: int, template: Optional[StatusUpdateTemplate] = None):
        """Send notifications to relevant stakeholders"""
        
        status_update = session.query(StatusUpdate).filter(StatusUpdate.id == status_update_id).first()
        if not status_update:
            return 0
        
        # Get update frequency to check for escalation
        frequency_record = session.query(UpdateFrequency).filter(
            UpdateFrequency.project_id == status_update.project_id
        ).first()
        
        if not frequency_record:
            frequency_record = UpdateFrequency(project_id=status_update.project_id)
            session.add(frequency_record)
        
        # Determine recipients
        recipients = []
        
        if template:
            # Get users with specified roles
            recipient_roles = template.recipient_roles or ["project_manager", "stakeholder"]
            users = session.query(User).filter(User.role.in_(recipient_roles)).all()
            recipients.extend(users)
            
            # Add specific additional recipients
            if template.additional_recipients:
                additional_ids = json.loads(template.additional_recipients) if isinstance(template.additional_recipients, str) else template.additional_recipients
                additional_users = session.query(User).filter(User.id.in_(additional_ids)).all()
                recipients.extend(additional_users)
        else:
            # Default: notify project managers and stakeholders
            users = session.query(User).filter(User.role.in_(["project_manager", "stakeholder"])).all()
            recipients.extend(users)
        
        # Create notification logs
        notification_count = 0
        for recipient in set(recipients):  # Remove duplicates
            notification = NotificationLog(
                status_update_id=status_update_id,
                recipient_id=recipient.id,
                recipient_role=recipient.role,
                notification_type="status_update",
                channel="email",  # Default channel
                subject=f"Project Status Update: {status_update.project.name}",
                content=status_update.summary or "",
                delivery_status="pending"
            )
            session.add(notification)
            notification_count += 1
        
        status_update.is_published = True
        status_update.published_at = datetime.utcnow()
        session.commit()
        
        logger.info(f"Created {notification_count} notifications for status update {status_update_id}")
        return notification_count

