"""
Alert Integration Service - Connects alerts to existing Phase 1 & 2 features.

Integrates:
- Phase 1: Sentiment Analysis → Morale/confidence alerts
- Phase 2: Communication Analysis → Conflict alerts
- Task System → Delay/scope alerts
- Budget System → Overrun alerts
- Team System → Workload/burnout alerts

This service acts as a bridge between the alerting system and existing project data.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

import logging

logger = logging.getLogger(__name__)


class AlertIntegrationService:
    """
    Monitors project data from all existing features and triggers alerts.
    
    Integration Points:
    - StakeholderFeedback (Phase 1) → Sentiment trends
    - SentimentScore (Phase 1) → Mood indicators
    - CommunicationMessage (Phase 2) → Interaction quality
    - CollaborationMetrics (Phase 2) → Team health
    - ConflictAlert (Phase 2) → Escalation signals
    - Task (Core) → Progress, delays, workload
    - Project (Core) → Budget, timeline
    """

    def __init__(self):
        self.sentiment_threshold = -0.3  # Below this = alert
        self.sentiment_drop_threshold = -0.2  # Drop rate = alert
        self.conflict_threshold = 5  # More than 5 in a week
        self.low_collaboration_threshold = 4.0  # Out of 10
        self.task_delay_days = 2  # Alert if behind by 2+ days
        self.budget_threshold = 0.85  # Alert at 85% of budget

    # ============================================================================
    # PHASE 1 INTEGRATION: Sentiment Analysis
    # ============================================================================

    def check_sentiment_alerts(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Monitor sentiment from Phase 1 Sentiment Analysis feature.
        
        Checks:
        1. Current sentiment score below threshold
        2. Sentiment dropping trend (negative momentum)
        3. Feedback sentiment declining
        
        Returns alerts if conditions met.
        """
        try:
            from app.models.models import SentimentScore, StakeholderFeedback

            alerts = []

            # 1. Get latest sentiment scores
            latest_sentiments = session.query(
                SentimentScore.user_id,
                SentimentScore.sentiment_score,
                SentimentScore.created_at
            ).filter(
                SentimentScore.project_id == project_id
            ).order_by(
                SentimentScore.user_id,
                SentimentScore.created_at.desc()
            ).all()

            if not latest_sentiments:
                return []

            # Group by user and get current vs. previous
            user_sentiments = {}
            for user_id, score, created_at in latest_sentiments:
                if user_id not in user_sentiments:
                    user_sentiments[user_id] = []
                user_sentiments[user_id].append((score, created_at))

            # Check for sentiment issues
            for user_id, scores in user_sentiments.items():
                if len(scores) >= 2:
                    current_score = scores[0][0]
                    previous_score = scores[1][0]
                    current_date = scores[0][1]

                    # Alert: Current sentiment very low
                    if current_score < self.sentiment_threshold:
                        alerts.append({
                            "alert_type": "low_sentiment",
                            "priority": "high" if current_score < -0.5 else "medium",
                            "user_id": user_id,
                            "entity_type": "user",
                            "entity_id": user_id,
                            "title": "Team Member Low Sentiment",
                            "description": f"Sentiment score: {current_score:.2f} (low)",
                            "risk_level": "high",
                            "confidence_score": 0.85,
                            "predicted_issue": f"Team member may have morale issues",
                            "risk_factors": {
                                "current_sentiment": current_score,
                                "threshold": self.sentiment_threshold,
                                "days_low": 1
                            },
                            "recommended_actions": [
                                "Schedule one-on-one check-in",
                                "Review recent workload and stress",
                                "Offer support or career development"
                            ]
                        })

                    # Alert: Sentiment dropping (negative trend)
                    if current_score < previous_score and (previous_score - current_score) > self.sentiment_drop_threshold:
                        alerts.append({
                            "alert_type": "sentiment_declining",
                            "priority": "medium",
                            "user_id": user_id,
                            "entity_type": "user",
                            "entity_id": user_id,
                            "title": "Team Member Sentiment Declining",
                            "description": f"Sentiment dropped from {previous_score:.2f} to {current_score:.2f}",
                            "risk_level": "medium",
                            "confidence_score": 0.75,
                            "predicted_issue": "Sentiment trend is negative - possible burnout or dissatisfaction",
                            "risk_factors": {
                                "decline_rate": previous_score - current_score,
                                "current_value": current_score,
                                "trend": "negative"
                            },
                            "recommended_actions": [
                                "Check recent project changes",
                                "Gather feedback on what's causing decline",
                                "Consider workload adjustment"
                            ]
                        })

            return alerts

        except Exception as e:
            logger.error(f"Error checking sentiment alerts: {e}")
            return []

    # ============================================================================
    # PHASE 2 INTEGRATION: Communication Analysis
    # ============================================================================

    def check_communication_alerts(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Monitor communication health from Phase 2 Communication Analysis.
        
        Checks:
        1. Conflict frequency (too many conflicts in recent period)
        2. Team stress index (collaboration metrics declining)
        3. Unresolved conflicts (age of unresolved issues)
        
        Returns alerts if conditions met.
        """
        try:
            from app.models.models import ConflictAlert, CollaborationMetrics

            alerts = []

            # 1. Check for high conflict frequency
            week_ago = datetime.utcnow() - timedelta(days=7)
            conflict_count = session.query(
                func.count(ConflictAlert.id)
            ).filter(
                ConflictAlert.project_id == project_id,
                ConflictAlert.created_at >= week_ago
            ).scalar() or 0

            if conflict_count > self.conflict_threshold:
                alerts.append({
                    "alert_type": "conflict_escalation",
                    "priority": "high" if conflict_count > 8 else "medium",
                    "entity_type": "project",
                    "entity_id": project_id,
                    "title": "High Conflict Frequency Detected",
                    "description": f"Team experienced {conflict_count} conflicts in the past week",
                    "risk_level": "high",
                    "confidence_score": 0.8,
                    "predicted_issue": "Team tension is escalating - intervention needed",
                    "risk_factors": {
                        "conflicts_per_week": conflict_count,
                        "threshold": self.conflict_threshold,
                        "severity_index": min(10, conflict_count / 2)
                    },
                    "recommended_actions": [
                        "Schedule team meeting to address tensions",
                        "Mediate between conflicting parties",
                        "Review communication norms and expectations",
                        "Consider team building activities"
                    ]
                })

            # 2. Check collaboration metrics
            latest_collab = session.query(
                CollaborationMetrics
            ).filter(
                CollaborationMetrics.project_id == project_id
            ).order_by(
                CollaborationMetrics.created_at.desc()
            ).first()

            if latest_collab:
                team_stress = latest_collab.team_stress_index or 0

                if team_stress > 7.0:
                    alerts.append({
                        "alert_type": "team_stress",
                        "priority": "high",
                        "entity_type": "project",
                        "entity_id": project_id,
                        "title": "High Team Stress Detected",
                        "description": f"Team stress index: {team_stress:.1f}/10 (elevated)",
                        "risk_level": "high",
                        "confidence_score": 0.85,
                        "predicted_issue": "Team morale and productivity at risk due to stress",
                        "risk_factors": {
                            "stress_index": team_stress,
                            "high_threshold": 7.0,
                            "status": "critical" if team_stress > 8 else "elevated"
                        },
                        "recommended_actions": [
                            "Reduce workload intensity",
                            "Increase recovery time between sprints",
                            "Provide wellness resources",
                            "Encourage time off"
                        ]
                    })

            # 3. Check for unresolved conflicts
            unresolved = session.query(
                ConflictAlert
            ).filter(
                ConflictAlert.project_id == project_id,
                ConflictAlert.resolved.is_(False)
            ).order_by(
                ConflictAlert.created_at.asc()
            ).all()

            if unresolved:
                oldest = unresolved[0]
                days_unresolved = (datetime.utcnow() - oldest.created_at).days

                if days_unresolved > 7:
                    alerts.append({
                        "alert_type": "unresolved_conflict",
                        "priority": "high",
                        "entity_type": "project",
                        "entity_id": project_id,
                        "title": f"Unresolved Conflict ({days_unresolved} days old)",
                        "description": f"{len(unresolved)} active unresolved conflicts",
                        "risk_level": "high",
                        "confidence_score": 0.9,
                        "predicted_issue": "Long-standing unresolved conflicts damage team trust",
                        "risk_factors": {
                            "unresolved_count": len(unresolved),
                            "oldest_age_days": days_unresolved,
                            "avg_age_days": sum((datetime.utcnow() - c.created_at).days for c in unresolved) // len(unresolved)
                        },
                        "recommended_actions": [
                            "Schedule conflict resolution sessions",
                            "Bring in mediator if needed",
                            "Document issues and action plans",
                            "Follow up weekly until resolved"
                        ]
                    })

            return alerts

        except Exception as e:
            logger.error(f"Error checking communication alerts: {e}")
            return []

    # ============================================================================
    # TASK & PROJECT INTEGRATION
    # ============================================================================

    def check_task_delays(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Monitor task progress from Task system.
        
        Predicts delays based on:
        - Current progress vs. time remaining
        - Velocity trend
        - Blocking dependencies
        """
        try:
            from app.models.models import Task

            alerts = []

            # Get in-progress and todo tasks with due dates
            tasks = session.query(Task).filter(
                Task.project_id == project_id,
                Task.status.in_(['todo', 'in_progress']),
                Task.due_date.isnot(None)
            ).all()

            for task in tasks:
                days_until_due = (task.due_date - datetime.utcnow()).days
                progress = getattr(task, 'progress', 0) or 0
                remaining_work = 100 - progress

                # Estimate completion time
                if progress > 0:
                    estimated_completion_days = (remaining_work * days_until_due) / max(progress, 1)
                else:
                    estimated_completion_days = remaining_work / 15  # Default 15% per day

                if estimated_completion_days > days_until_due:
                    delay_days = int(estimated_completion_days - days_until_due)
                    priority = "critical" if delay_days > 5 else "high" if delay_days > 2 else "medium"

                    alerts.append({
                        "alert_type": "task_delay",
                        "priority": priority,
                        "entity_type": "task",
                        "entity_id": task.id,
                        "title": f"Task Delay Risk: {task.name}",
                        "description": f"Task will be ~{delay_days} days late at current velocity",
                        "risk_level": "high",
                        "confidence_score": 0.85,
                        "predicted_issue": f"Task '{task.name}' will miss deadline by approximately {delay_days} days",
                        "risk_factors": {
                            "current_progress_percent": progress,
                            "days_until_due": days_until_due,
                            "estimated_completion_days": estimated_completion_days,
                            "predicted_delay_days": delay_days
                        },
                        "recommended_actions": [
                            "Allocate additional resources to task",
                            "Review and remove blocking dependencies",
                            "Re-scope task to reduce scope",
                            "Extend deadline if possible",
                            "Identify and remove impediments"
                        ]
                    })

            return alerts

        except Exception as e:
            logger.error(f"Error checking task delays: {e}")
            return []

    def check_scope_creep(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Detect scope creep by monitoring task creation rate.
        
        Compares recent task creation speed to baseline.
        """
        try:
            from app.models.models import Task

            alerts = []

            # Compare task creation: this week vs. previous weeks
            now = datetime.utcnow()
            this_week_start = now - timedelta(days=now.weekday())
            last_week_start = this_week_start - timedelta(days=7)
            avg_week_start = this_week_start - timedelta(days=28)

            this_week_tasks = session.query(func.count(Task.id)).filter(
                Task.project_id == project_id,
                Task.created_at >= this_week_start
            ).scalar() or 0

            last_week_tasks = session.query(func.count(Task.id)).filter(
                Task.project_id == project_id,
                Task.created_at >= last_week_start,
                Task.created_at < this_week_start
            ).scalar() or 0

            avg_weekly_tasks = session.query(func.count(Task.id)).filter(
                Task.project_id == project_id,
                Task.created_at >= avg_week_start
            ).scalar() or 0
            
            if avg_weekly_tasks > 0:
                avg_weekly_tasks = avg_weekly_tasks / 4

            # Check for acceleration
            if last_week_tasks > 0:
                growth_rate = this_week_tasks / last_week_tasks
            else:
                growth_rate = 2.0 if this_week_tasks > 0 else 0

            if growth_rate > 1.25 and this_week_tasks > 3:
                alerts.append({
                    "alert_type": "scope_creep",
                    "priority": "medium",
                    "entity_type": "project",
                    "entity_id": project_id,
                    "title": "Scope Creep Detected",
                    "description": f"Task creation rate up {(growth_rate-1)*100:.0f}% vs. last week",
                    "risk_level": "medium",
                    "confidence_score": 0.80,
                    "predicted_issue": f"Scope is expanding faster than planned (25%+ growth)",
                    "risk_factors": {
                        "this_week_tasks": this_week_tasks,
                        "last_week_tasks": last_week_tasks,
                        "growth_rate": round(growth_rate, 2),
                        "avg_weekly_baseline": round(avg_weekly_tasks, 1)
                    },
                    "recommended_actions": [
                        "Review new tasks for priority alignment",
                        "Consider deferring lower-priority items",
                        "Adjust timeline to account for additional work",
                        "Reduce scope in non-critical areas"
                    ]
                })

            return alerts

        except Exception as e:
            logger.error(f"Error checking scope creep: {e}")
            return []

    def check_budget_overrun(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Monitor budget health from Project system.
        
        Predicts overruns based on burn rate and remaining budget.
        """
        try:
            from app.models.models import Project

            alerts = []

            project = session.query(Project).filter(
                Project.id == project_id
            ).first()

            if not project:
                return []

            budget = getattr(project, 'budget', 0) or 0
            spent = getattr(project, 'spent', 0) or 0

            if budget > 0:
                spent_percent = spent / budget

                if spent_percent >= self.budget_threshold:
                    remaining = budget - spent
                    alert_priority = "critical" if spent_percent > 0.95 else "high"

                    alerts.append({
                        "alert_type": "budget_overrun",
                        "priority": alert_priority,
                        "entity_type": "project",
                        "entity_id": project_id,
                        "title": "Budget Alert",
                        "description": f"Project at {spent_percent*100:.0f}% of budget",
                        "risk_level": "high",
                        "confidence_score": 0.95,
                        "predicted_issue": f"Remaining budget: ${remaining:,.0f}",
                        "risk_factors": {
                            "budget_total": budget,
                            "amount_spent": spent,
                            "percent_spent": round(spent_percent, 2),
                            "remaining": remaining
                        },
                        "recommended_actions": [
                            "Request budget increase",
                            "Reduce scope to match budget",
                            "Find cost efficiencies",
                            "Pause non-critical work"
                        ]
                    })

            return alerts

        except Exception as e:
            logger.error(f"Error checking budget: {e}")
            return []

    def check_team_workload(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Monitor team member workload distribution.
        
        Alerts on:
        - High variance in task distribution
        - Individual overload (3x+ average)
        """
        try:
            from app.models.models import Task

            alerts = []

            # Count active tasks per user
            task_counts = session.query(
                Task.assigned_to,
                func.count(Task.id).label('task_count')
            ).filter(
                Task.project_id == project_id,
                Task.status.in_(['todo', 'in_progress'])
            ).group_by(
                Task.assigned_to
            ).all()

            if not task_counts or len(task_counts) < 2:
                return []

            counts = [count for _, count in task_counts]
            avg_tasks = sum(counts) / len(counts)
            max_tasks = max(counts)
            min_tasks = min(counts)

            # Check for severe imbalance
            if max_tasks > avg_tasks * 3:
                overloaded_user = [user for user, count in task_counts if count == max_tasks][0]

                alerts.append({
                    "alert_type": "team_workload_imbalance",
                    "priority": "high",
                    "entity_type": "team",
                    "entity_id": project_id,
                    "title": "Team Workload Imbalance",
                    "description": f"One member has {max_tasks} tasks vs. avg of {avg_tasks:.0f}",
                    "risk_level": "high",
                    "confidence_score": 0.85,
                    "predicted_issue": f"Team member {overloaded_user} is overloaded - burnout risk",
                    "risk_factors": {
                        "overloaded_user_tasks": max_tasks,
                        "average_tasks": round(avg_tasks, 1),
                        "imbalance_ratio": round(max_tasks / avg_tasks, 2),
                        "team_size": len(counts)
                    },
                    "recommended_actions": [
                        "Redistribute tasks to underutilized team members",
                        "Reassign lower-priority items",
                        "Provide support or pair programming",
                        "Adjust timeline to reduce pressure"
                    ]
                })

            return alerts

        except Exception as e:
            logger.error(f"Error checking team workload: {e}")
            return []

    # ============================================================================
    # UNIFIED MONITORING
    # ============================================================================

    def run_integrated_checks(self, session: Session, project_id: int) -> List[Dict[str, Any]]:
        """
        Run all integration checks and collect alerts.
        
        This is the main entry point that triggers all monitoring:
        - Phase 1 sentiment checks
        - Phase 2 communication checks
        - Task delay detection
        - Budget monitoring
        - Team workload analysis
        - Scope creep detection
        
        Returns: List of alert dictionaries ready for Alert model creation
        """
        all_alerts = []

        # Phase 1: Sentiment Analysis
        sentiment_alerts = self.check_sentiment_alerts(session, project_id)
        all_alerts.extend(sentiment_alerts)
        logger.info(f"Sentiment checks for project {project_id}: {len(sentiment_alerts)} alerts")

        # Phase 2: Communication Analysis
        communication_alerts = self.check_communication_alerts(session, project_id)
        all_alerts.extend(communication_alerts)
        logger.info(f"Communication checks for project {project_id}: {len(communication_alerts)} alerts")

        # Task System
        task_delay_alerts = self.check_task_delays(session, project_id)
        all_alerts.extend(task_delay_alerts)
        logger.info(f"Task delay checks for project {project_id}: {len(task_delay_alerts)} alerts")

        scope_alerts = self.check_scope_creep(session, project_id)
        all_alerts.extend(scope_alerts)
        logger.info(f"Scope creep checks for project {project_id}: {len(scope_alerts)} alerts")

        # Budget System
        budget_alerts = self.check_budget_overrun(session, project_id)
        all_alerts.extend(budget_alerts)
        logger.info(f"Budget checks for project {project_id}: {len(budget_alerts)} alerts")

        # Team System
        workload_alerts = self.check_team_workload(session, project_id)
        all_alerts.extend(workload_alerts)
        logger.info(f"Team workload checks for project {project_id}: {len(workload_alerts)} alerts")

        logger.info(f"Total integrated alerts for project {project_id}: {len(all_alerts)}")
        return all_alerts


class BackgroundAlertMonitor:
    """
    Scheduler for continuous monitoring via background tasks.
    
    Runs regularly (e.g., every 30 minutes) to:
    1. Check all projects for alert conditions
    2. Create alert records
    3. Apply user preferences
    4. Batch and deliver notifications
    """

    def __init__(self):
        self.integration_service = AlertIntegrationService()

    async def monitor_all_projects(self, session: Session):
        """
        Monitor all active projects for alert conditions.
        
        Should be called periodically by APScheduler/Celery.
        """
        try:
            from app.models.models import Project, Alert, AlertTemplate

            # Get all active projects
            projects = session.query(Project).filter(
                Project.status != 'archived'
            ).all()

            logger.info(f"Starting alert monitoring for {len(projects)} projects")

            for project in projects:
                try:
                    # Run integrated checks
                    alerts = self.integration_service.run_integrated_checks(
                        session, 
                        project.id
                    )

                    # Create alert records
                    for alert_data in alerts:
                        # Get template for this alert type
                        template = session.query(AlertTemplate).filter(
                            AlertTemplate.name.ilike(f"%{alert_data['alert_type']}%")
                        ).first()

                        # Create alert record
                        alert = Alert(
                            project_id=project.id,
                            template_id=template.id if template else None,
                            recipient_id=project.owner_id,  # Or distribute to team
                            alert_type=alert_data['alert_type'],
                            title=alert_data['title'],
                            description=alert_data['description'],
                            priority=alert_data['priority'],
                            urgency_score=float(alert_data.get('confidence_score', 0.5)),
                            is_predictive=True,
                            prediction_confidence=float(alert_data.get('confidence_score', 0.8)),
                            predicted_issue=alert_data.get('predicted_issue', ''),
                            context_data=alert_data,
                            entity_type=alert_data.get('entity_type', 'project'),
                            entity_id=alert_data.get('entity_id', project.id),
                            delivery_status='pending'
                        )
                        session.add(alert)

                    session.commit()
                    logger.info(f"Created {len(alerts)} alerts for project {project.id}")

                except Exception as e:
                    logger.error(f"Error monitoring project {project.id}: {e}")
                    session.rollback()
                    continue

        except Exception as e:
            logger.error(f"Error in background monitoring: {e}")

    async def monitor_project(self, session: Session, project_id: int):
        """
        Monitor a single project (useful for on-demand checks).
        """
        try:
            from app.models.models import Alert, AlertTemplate

            alerts = self.integration_service.run_integrated_checks(session, project_id)

            for alert_data in alerts:
                template = session.query(AlertTemplate).filter(
                    AlertTemplate.name.ilike(f"%{alert_data['alert_type']}%")
                ).first()

                alert = Alert(
                    project_id=project_id,
                    template_id=template.id if template else None,
                    alert_type=alert_data['alert_type'],
                    title=alert_data['title'],
                    description=alert_data['description'],
                    priority=alert_data['priority'],
                    urgency_score=float(alert_data.get('confidence_score', 0.5)),
                    is_predictive=True,
                    prediction_confidence=float(alert_data.get('confidence_score', 0.8)),
                    predicted_issue=alert_data.get('predicted_issue', ''),
                    context_data=alert_data,
                    entity_type=alert_data.get('entity_type', 'project'),
                    entity_id=alert_data.get('entity_id', project_id),
                    delivery_status='pending'
                )
                session.add(alert)

            session.commit()
            logger.info(f"Created {len(alerts)} alerts for project {project_id}")

        except Exception as e:
            logger.error(f"Error monitoring project {project_id}: {e}")
            session.rollback()
