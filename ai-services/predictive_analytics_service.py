"""
Predictive Analytics Service for Intelligent Alerts
Analyzes project data to predict potential issues and generate proactive alerts
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

import json


class PredictiveAnalyzer:
    """Analyzes project and team data to predict potential issues"""
    
    def __init__(self):
        self.prediction_models = {
            'task_delay': self._analyze_task_delays,
            'budget_overrun': self._analyze_budget_risks,
            'conflict_escalation': self._analyze_conflict_risks,
            'scope_creep': self._analyze_scope_creep,
            'team_risk': self._analyze_team_risks,
        }
    
    def analyze_all_risks(self, session: Session, project_id: int) -> List[Dict]:
        """
        Comprehensive risk analysis for a project
        Returns list of predictive insights
        """
        try:
            insights = []
            
            # Analyze each risk type
            for risk_type, analyzer_func in self.prediction_models.items():
                try:
                    risk_data = analyzer_func(session, project_id)
                    if risk_data:
                        insights.extend(risk_data)
                except Exception as e:
                    print(f"Error analyzing {risk_type}: {str(e)}")
            
            return insights
        except Exception as e:
            print(f"Error in comprehensive risk analysis: {str(e)}")
            return []
    
    def _analyze_task_delays(self, session: Session, project_id: int) -> List[Dict]:
        """
        Predict task delays based on:
        - Current progress vs. timeline
        - Historical task velocity
        - Dependencies and blockers
        """
        try:
            from app.models.models import Task, Project
            
            insights = []
            project = session.query(Project).filter(Project.id == project_id).first()
            
            if not project:
                return []
            
            # Get all active tasks
            tasks = session.query(Task).filter(
                Task.project_id == project_id,
                Task.status.in_(['todo', 'in_progress'])
            ).all()
            
            for task in tasks:
                if not task.due_date:
                    continue
                
                # Calculate delay risk
                today = datetime.utcnow()
                days_until_due = (task.due_date - today).days
                
                # Estimate completion based on progress
                if task.status == 'in_progress':
                    # If task is in progress, analyze velocity
                    progress_percent = getattr(task, 'progress', 0)
                    estimated_completion_days = (100 - progress_percent) / max(15, progress_percent) if progress_percent > 0 else 10
                    
                    confidence = 0.75
                    risk_level = 'low'
                    
                    if estimated_completion_days > days_until_due:
                        # Task will be late
                        delay_days = int(estimated_completion_days - days_until_due)
                        risk_level = 'critical' if delay_days > 5 else 'high' if delay_days > 2 else 'medium'
                        confidence = 0.85
                        
                        insights.append({
                            'insight_type': 'task_delay',
                            'entity_type': 'task',
                            'entity_id': task.id,
                            'entity_name': task.title,
                            'risk_level': risk_level,
                            'confidence_score': confidence,
                            'predicted_issue': f'Task "{task.title}" will be approximately {delay_days} days late',
                            'risk_factors': [
                                {'factor': 'low_progress_velocity', 'weight': 0.4},
                                {'factor': 'approaching_deadline', 'weight': 0.3},
                                {'factor': 'task_complexity', 'weight': 0.3}
                            ],
                            'recommended_actions': [
                                'Allocate additional resources to this task',
                                'Review blocking dependencies',
                                'Consider breaking task into smaller chunks',
                                'Notify stakeholders of potential delay'
                            ],
                            'expected_occurrence': task.due_date
                        })
                elif task.status == 'todo' and days_until_due < 3:
                    # Task not started but due soon
                    insights.append({
                        'insight_type': 'task_delay',
                        'entity_type': 'task',
                        'entity_id': task.id,
                        'entity_name': task.title,
                        'risk_level': 'high',
                        'confidence_score': 0.9,
                        'predicted_issue': f'Task "{task.title}" is not started and due in {days_until_due} days',
                        'risk_factors': [
                            {'factor': 'not_started', 'weight': 0.6},
                            {'factor': 'imminent_deadline', 'weight': 0.4}
                        ],
                        'recommended_actions': [
                            'Start task immediately',
                            'Allocate resources urgently',
                            'Review task requirements for quick completion'
                        ],
                        'expected_occurrence': task.due_date
                    })
            
            return insights
        except Exception as e:
            print(f"Error analyzing task delays: {str(e)}")
            return []
    
    def _analyze_budget_risks(self, session: Session, project_id: int) -> List[Dict]:
        """
        Predict budget overruns based on:
        - Current spending vs. timeline
        - Historical burn rate
        - Resource costs
        """
        try:
            from app.models.models import Project, Task
            
            insights = []
            project = session.query(Project).filter(Project.id == project_id).first()
            
            if not project or not project.budget:
                return []
            
            # Calculate spending patterns
            budget_remaining = project.budget - (project.actual_cost or 0)
            time_elapsed = (datetime.utcnow() - project.created_at).days + 1
            
            if time_elapsed > 0:
                daily_burn_rate = (project.actual_cost or 0) / time_elapsed
                
                # Project completion date
                project_duration = (project.end_date - project.created_at).days if project.end_date else 30
                days_remaining = max(1, (project.end_date - datetime.utcnow()).days) if project.end_date else 10
                
                # Estimate final cost
                estimated_final_cost = (project.actual_cost or 0) + (daily_burn_rate * days_remaining)
                
                if estimated_final_cost > project.budget:
                    overrun_amount = estimated_final_cost - project.budget
                    overrun_percent = (overrun_amount / project.budget) * 100
                    
                    risk_level = 'critical' if overrun_percent > 20 else 'high' if overrun_percent > 10 else 'medium'
                    
                    insights.append({
                        'insight_type': 'budget_overrun',
                        'entity_type': 'project',
                        'entity_id': project_id,
                        'entity_name': f"Project {project.id}",
                        'risk_level': risk_level,
                        'confidence_score': 0.8,
                        'predicted_issue': f'Budget will exceed by ${overrun_amount:,.0f} ({overrun_percent:.1f}%) at current burn rate',
                        'risk_factors': [
                            {'factor': 'high_burn_rate', 'weight': 0.5},
                            {'factor': 'budget_allocated', 'weight': 0.3},
                            {'factor': 'timeline_pressure', 'weight': 0.2}
                        ],
                        'recommended_actions': [
                            'Review and optimize resource allocation',
                            'Identify cost-saving opportunities',
                            'Consider timeline extension to reduce daily burn',
                            'Request budget approval for overrun or reduce scope'
                        ],
                        'expected_occurrence': project.end_date or datetime.utcnow() + timedelta(days=10)
                    })
                elif budget_remaining < budget_remaining * 0.2:  # Less than 20% remaining
                    insights.append({
                        'insight_type': 'budget_overrun',
                        'entity_type': 'project',
                        'entity_id': project_id,
                        'entity_name': f"Project {project.id}",
                        'risk_level': 'medium',
                        'confidence_score': 0.75,
                        'predicted_issue': f'Budget approaching limit with only ${budget_remaining:,.0f} ({(budget_remaining/project.budget)*100:.1f}%) remaining',
                        'risk_factors': [
                            {'factor': 'limited_budget_buffer', 'weight': 0.6},
                            {'factor': 'active_spending', 'weight': 0.4}
                        ],
                        'recommended_actions': [
                            'Monitor spending closely',
                            'Hold contingency budget',
                            'Plan for controlled completion within budget'
                        ],
                        'expected_occurrence': datetime.utcnow() + timedelta(days=5)
                    })
            
            return insights
        except Exception as e:
            print(f"Error analyzing budget risks: {str(e)}")
            return []
    
    def _analyze_conflict_risks(self, session: Session, project_id: int) -> List[Dict]:
        """
        Predict conflict escalation based on:
        - Communication sentiment trends
        - Conflict history
        - Team dynamics from sentiment analysis
        """
        try:
            from app.models.models import CommunicationMessage, ConflictAlert
            
            insights = []
            
            # Get recent conflicts
            recent_conflicts = session.query(ConflictAlert).filter(
                ConflictAlert.project_id == project_id,
                ConflictAlert.created_at >= datetime.utcnow() - timedelta(days=7)
            ).all()
            
            conflict_count = len(recent_conflicts)
            
            if conflict_count > 3:
                # Escalating conflict trend
                insights.append({
                    'insight_type': 'conflict_escalation',
                    'entity_type': 'project',
                    'entity_id': project_id,
                    'entity_name': f"Project {project_id}",
                    'risk_level': 'high' if conflict_count > 5 else 'medium',
                    'confidence_score': 0.8,
                    'predicted_issue': f'Multiple conflicts detected ({conflict_count} in past week). Risk of escalation.',
                    'risk_factors': [
                        {'factor': 'conflict_frequency', 'weight': 0.5},
                        {'factor': 'team_tension', 'weight': 0.3},
                        {'factor': 'unresolved_issues', 'weight': 0.2}
                    ],
                    'recommended_actions': [
                        'Schedule team meeting to address underlying issues',
                        'Facilitate mediation between conflicted parties',
                        'Review project pressures and deadlines',
                        'Improve communication channels and protocols'
                    ],
                    'expected_occurrence': datetime.utcnow() + timedelta(days=3)
                })
            
            # Analyze communication sentiment
            negative_messages = session.query(CommunicationMessage).filter(
                CommunicationMessage.project_id == project_id,
                CommunicationMessage.sentiment_category.in_(['negative', 'very_negative']),
                CommunicationMessage.created_at >= datetime.utcnow() - timedelta(days=3)
            ).count()
            
            if negative_messages > 10:
                insights.append({
                    'insight_type': 'conflict_escalation',
                    'entity_type': 'project',
                    'entity_id': project_id,
                    'entity_name': f"Project {project_id}",
                    'risk_level': 'medium',
                    'confidence_score': 0.75,
                    'predicted_issue': f'High volume of negative sentiment ({negative_messages} messages) suggests building conflict',
                    'risk_factors': [
                        {'factor': 'negative_sentiment_spike', 'weight': 0.5},
                        {'factor': 'team_morale', 'weight': 0.5}
                    ],
                    'recommended_actions': [
                        'Address team concerns promptly',
                        'Increase transparency about project status',
                        'Consider team morale activities',
                        'Review and adjust project pressures'
                    ],
                    'expected_occurrence': datetime.utcnow() + timedelta(days=2)
                })
            
            return insights
        except Exception as e:
            print(f"Error analyzing conflict risks: {str(e)}")
            return []
    
    def _analyze_scope_creep(self, session: Session, project_id: int) -> List[Dict]:
        """
        Predict scope creep based on:
        - Task growth trends
        - Feature requests accumulation
        - Timeline vs. effort tracking
        """
        try:
            from app.models.models import Task, Project
            
            insights = []
            project = session.query(Project).filter(Project.id == project_id).first()
            
            if not project:
                return []
            
            # Count tasks created over time
            week_ago = datetime.utcnow() - timedelta(days=7)
            tasks_last_week = session.query(Task).filter(
                Task.project_id == project_id,
                Task.created_at >= week_ago
            ).count()
            
            total_tasks = session.query(Task).filter(
                Task.project_id == project_id
            ).count()
            
            # New tasks as percentage of total
            if total_tasks > 0:
                new_task_percent = (tasks_last_week / total_tasks) * 100
                
                if new_task_percent > 20:  # More than 20% new tasks in last week
                    insights.append({
                        'insight_type': 'scope_creep',
                        'entity_type': 'project',
                        'entity_id': project_id,
                        'entity_name': f"Project {project.id}",
                        'risk_level': 'high' if new_task_percent > 30 else 'medium',
                        'confidence_score': 0.8,
                        'predicted_issue': f'Scope creep detected: {tasks_last_week} new tasks added ({new_task_percent:.1f}%) in past week',
                        'risk_factors': [
                            {'factor': 'task_addition_rate', 'weight': 0.6},
                            {'factor': 'timeline_impact', 'weight': 0.3},
                            {'factor': 'resource_strain', 'weight': 0.1}
                        ],
                        'recommended_actions': [
                            'Review new tasks for necessity and priority',
                            'Establish change control process',
                            'Evaluate impact on timeline and resources',
                            'Consider moving low-priority items to future release'
                        ],
                        'expected_occurrence': datetime.utcnow() + timedelta(days=7)
                    })
            
            return insights
        except Exception as e:
            print(f"Error analyzing scope creep: {str(e)}")
            return []
    
    def _analyze_team_risks(self, session: Session, project_id: int) -> List[Dict]:
        """
        Predict team-related risks based on:
        - Team member workload
        - Participation patterns
        - Key person dependencies
        """
        try:
            from app.models.models import Task, CollaborationMetrics
            
            insights = []
            
            # Analyze workload distribution
            task_assignments = session.query(Task.assignee_id, func.count(Task.id)).filter(
                Task.project_id == project_id,
                Task.status.in_(['todo', 'in_progress'])
            ).group_by(Task.assignee_id).all()
            
            if task_assignments:
                assignment_counts = [count for _, count in task_assignments]
                avg_tasks = np.mean(assignment_counts)
                max_tasks = np.max(assignment_counts)
                
                # Check for overloaded team members
                if max_tasks > avg_tasks * 2:
                    insights.append({
                        'insight_type': 'team_risk',
                        'entity_type': 'project',
                        'entity_id': project_id,
                        'entity_name': f"Project {project_id}",
                        'risk_level': 'high',
                        'confidence_score': 0.85,
                        'predicted_issue': f'Unbalanced workload detected: one team member has {int(max_tasks)} tasks (avg: {avg_tasks:.1f})',
                        'risk_factors': [
                            {'factor': 'workload_imbalance', 'weight': 0.6},
                            {'factor': 'team_member_burnout', 'weight': 0.3},
                            {'factor': 'single_point_of_failure', 'weight': 0.1}
                        ],
                        'recommended_actions': [
                            'Redistribute tasks to balance workload',
                            'Provide support to overloaded team member',
                            'Cross-train team members for knowledge sharing',
                            'Monitor team member morale and engagement'
                        ],
                        'expected_occurrence': datetime.utcnow() + timedelta(days=3)
                    })
            
            return insights
        except Exception as e:
            print(f"Error analyzing team risks: {str(e)}")
            return []
    
    def calculate_urgency_score(self, insight: Dict) -> float:
        """
        Calculate alert urgency score (0.0-1.0) based on:
        - Risk level
        - Confidence
        - Time to occurrence
        """
        risk_scores = {
            'low': 0.2,
            'medium': 0.5,
            'high': 0.8,
            'critical': 1.0
        }
        
        base_score = risk_scores.get(insight['risk_level'], 0.5)
        confidence_multiplier = insight.get('confidence_score', 0.75)
        
        # Adjust for time urgency
        if insight.get('expected_occurrence'):
            days_until = (insight['expected_occurrence'] - datetime.utcnow()).days
            if days_until < 1:
                time_multiplier = 1.2
            elif days_until < 3:
                time_multiplier = 1.1
            else:
                time_multiplier = 1.0
        else:
            time_multiplier = 1.0
        
        urgency = min(1.0, (base_score * confidence_multiplier * time_multiplier))
        return urgency


class SmartBatchingOptimizer:
    """Machine learning-based alert batching optimization"""
    
    def __init__(self):
        self.batching_history = []  # Track past batching decisions
    
    def calculate_batching_score(self, alerts: List[Dict]) -> float:
        """
        Calculate how good a batch is (0.0-1.0)
        Higher score = better batch (related alerts)
        """
        if len(alerts) < 2:
            return 0.5
        
        # Batch quality factors
        same_type_score = self._calculate_type_similarity(alerts)
        time_proximity_score = self._calculate_time_proximity(alerts)
        context_relevance_score = self._calculate_context_relevance(alerts)
        
        # Weighted average
        batching_score = (
            same_type_score * 0.4 +
            time_proximity_score * 0.3 +
            context_relevance_score * 0.3
        )
        
        return min(1.0, batching_score)
    
    def _calculate_type_similarity(self, alerts: List[Dict]) -> float:
        """Score how similar the alert types are"""
        if len(alerts) < 2:
            return 1.0
        
        types = set(alert.get('alert_type') for alert in alerts)
        # More similar types = higher score
        return 1.0 - (len(types) / len(alerts))
    
    def _calculate_time_proximity(self, alerts: List[Dict]) -> float:
        """Score how close the alerts were created"""
        if len(alerts) < 2:
            return 1.0
        
        created_times = [alert.get('created_at') or datetime.utcnow() for alert in alerts]
        time_range = (max(created_times) - min(created_times)).total_seconds()
        
        # Alerts within 5 minutes = score 1.0
        # Alerts within 1 hour = score 0.5
        # Alerts within 1 day = score 0.2
        if time_range < 300:
            return 1.0
        elif time_range < 3600:
            return 0.5
        elif time_range < 86400:
            return 0.2
        else:
            return 0.0
    
    def _calculate_context_relevance(self, alerts: List[Dict]) -> float:
        """Score how related the contexts are"""
        if len(alerts) < 2:
            return 1.0
        
        # Same entity type and project = high relevance
        entity_types = set(alert.get('entity_type') for alert in alerts)
        entity_ids = set(alert.get('entity_id') for alert in alerts)
        
        if len(entity_types) == 1 and len(entity_ids) == 1:
            return 1.0  # All same entity
        elif len(entity_types) == 1:
            return 0.7  # Same type, different entities
        else:
            return 0.3  # Different types
    
    def suggest_batching_strategy(self, alerts: List[Dict], user_preferences: Dict) -> Tuple[str, float]:
        """
        Suggest optimal batching strategy
        Returns (strategy, estimated_reduction_percent)
        """
        if len(alerts) < 2:
            return ('no_batch', 0.0)
        
        strategy = 'smart_batch'
        
        # Check if all same type
        types = set(alert.get('alert_type') for alert in alerts)
        if len(types) == 1:
            strategy = 'same_type'
            est_reduction = min(50.0, len(alerts) * 10.0)  # Up to 50% reduction
        else:
            # Contextual batching
            batching_score = self.calculate_batching_score(alerts)
            est_reduction = batching_score * 40.0  # Up to 40% reduction
        
        # Respect user preferences
        if not user_preferences.get('batching_enabled', True):
            return ('no_batch', 0.0)
        
        return (strategy, est_reduction)
