from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, users, projects, tasks, risks, ai_predictions, 
    milestones, workflows, resources, budget, issues, documents, views, baselines, exports, ivalua, retention, rbac,
    portfolio, dashboard, dashboards, reports,
    ai_scheduling, ai_task_priority, ai_meeting_summaries, ai_task_extraction,
    ai_smart_search, ai_sentiment, ai_stakeholder_feedback,
    workflow_optimization, scenarios, raid,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(risks.router, prefix="/risks", tags=["Risks"])
api_router.include_router(milestones.router, prefix="/milestones", tags=["Milestones"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(resources.router, prefix="/resources", tags=["Resource Management"])
api_router.include_router(budget.router, prefix="/budget", tags=["Budget & Financial Management"])
api_router.include_router(issues.router, prefix="/issues", tags=["Issue Management"])
api_router.include_router(documents.router, prefix="/documents", tags=["Document Management"])
api_router.include_router(views.router, prefix="/views", tags=["Kanban & Gantt Views"])
api_router.include_router(baselines.router, prefix="/baselines", tags=["Baselines"])
api_router.include_router(exports.router, prefix="/exports", tags=["Export"])
api_router.include_router(ivalua.router, prefix="/ivalua", tags=["Ivalua Procurement"])
api_router.include_router(retention.router, prefix="/retention", tags=["Document Retention"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["RBAC"])
api_router.include_router(ai_predictions.router, prefix="/ai", tags=["AI Predictions"])
api_router.include_router(ai_scheduling.router, prefix="/ai", tags=["AI Scheduling"])
api_router.include_router(ai_task_priority.router, prefix="/ai", tags=["AI Task Priority"])
api_router.include_router(ai_meeting_summaries.router, prefix="/ai", tags=["AI Meeting Summaries"])
api_router.include_router(ai_task_extraction.router, prefix="/ai", tags=["AI Task Extraction"])
api_router.include_router(ai_smart_search.router, prefix="/ai", tags=["AI Smart Search"])
api_router.include_router(ai_sentiment.router, prefix="/ai", tags=["AI Sentiment"])
api_router.include_router(ai_stakeholder_feedback.router, prefix="/ai", tags=["AI Stakeholder Feedback"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["Role-Based Dashboards"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(workflow_optimization.router, prefix="/workflow-optimization", tags=["Workflow Optimization"])
api_router.include_router(scenarios.router, prefix="/scenarios", tags=["Scenarios"])
api_router.include_router(raid.router, prefix="/raid", tags=["RAID Log"])
