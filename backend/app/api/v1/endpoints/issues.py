from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import Issue, IssueComment, IssueAttachment, Project, Task
from app.schemas.schemas import (
    IssueCreate, IssueUpdate, IssueResponse,
    IssueCommentCreate, IssueCommentResponse
)

router = APIRouter()


# Issues
@router.post("/", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
async def create_issue(
    issue: IssueCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new issue"""
    # Verify project exists
    project_query = select(Project).where(Project.id == issue.project_id)
    result = await db.execute(project_query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Verify task exists if provided
    if issue.task_id:
        task_query = select(Task).where(Task.id == issue.task_id)
        result = await db.execute(task_query)
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
    
    db_issue = Issue(
        **issue.dict(),
        reported_by=current_user.id,
        status="open"
    )
    
    # Set SLA due date based on severity (simple logic)
    from datetime import timedelta
    sla_days = {
        "critical": 1,
        "high": 3,
        "medium": 7,
        "low": 14
    }
    db_issue.sla_due_date = datetime.now(timezone.utc) + timedelta(days=sla_days.get(issue.severity.value, 7))
    
    db.add(db_issue)
    await db.commit()
    await db.refresh(db_issue)
    return db_issue


@router.get("/", response_model=List[IssueResponse])
async def get_issues(
    project_id: int = Query(None),
    task_id: int = Query(None),
    status: str = Query(None),
    severity: str = Query(None),
    assigned_to: int = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get issues with filters"""
    query = select(Issue)
    
    if project_id:
        query = query.where(Issue.project_id == project_id)
    if task_id:
        query = query.where(Issue.task_id == task_id)
    if status:
        query = query.where(Issue.status == status)
    if severity:
        query = query.where(Issue.severity == severity)
    if assigned_to:
        query = query.where(Issue.assigned_to == assigned_to)
    
    query = query.order_by(Issue.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    issues = result.scalars().all()
    
    # Update days_open for each issue
    from datetime import timezone
    for issue in issues:
        if issue.status not in ["resolved", "closed"]:
            created = issue.created_at if issue.created_at.tzinfo else issue.created_at.replace(tzinfo=timezone.utc)
            issue.days_open = (datetime.now(timezone.utc) - created).days
    
    return issues


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    issue_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific issue"""
    query = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(query)
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )
    
    # Update days_open
    if issue.status not in ["resolved", "closed"]:
        issue.days_open = (datetime.now() - issue.created_at).days
    
    return issue


@router.put("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    issue_id: int,
    issue_update: IssueUpdate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Update an issue"""
    query = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(query)
    db_issue = result.scalar_one_or_none()
    
    if not db_issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )
    
    # Update fields
    update_data = issue_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_issue, key, value)
    
    # Set resolution date if status changed to resolved
    if 'status' in update_data and update_data['status'] in ['resolved', 'closed']:
        if not db_issue.resolution_date:
            db_issue.resolution_date = datetime.now()
    
    # Update SLA status
    if db_issue.sla_due_date:
        now = datetime.now()
        if now > db_issue.sla_due_date and db_issue.status not in ["resolved", "closed"]:
            db_issue.sla_status = "breached"
        elif now > db_issue.sla_due_date - timedelta(days=1):
            db_issue.sla_status = "at_risk"
        else:
            db_issue.sla_status = "on_track"
    
    await db.commit()
    await db.refresh(db_issue)
    return db_issue


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(
    issue_id: int,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete an issue"""
    query = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(query)
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )
    
    await db.delete(issue)
    await db.commit()


# Issue Comments
@router.post("/{issue_id}/comments", response_model=IssueCommentResponse, status_code=status.HTTP_201_CREATED)
async def create_issue_comment(
    issue_id: int,
    comment: IssueCommentCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Add a comment to an issue"""
    # Verify issue exists
    issue_query = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(issue_query)
    issue = result.scalar_one_or_none()
    
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found"
        )
    
    db_comment = IssueComment(
        issue_id=issue_id,
        author_id=current_user.id,
        **comment.dict()
    )
    
    db.add(db_comment)
    await db.commit()
    await db.refresh(db_comment)
    return db_comment


@router.get("/{issue_id}/comments", response_model=List[IssueCommentResponse])
async def get_issue_comments(
    issue_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all comments for an issue"""
    query = select(IssueComment).where(IssueComment.issue_id == issue_id).order_by(IssueComment.created_at)
    result = await db.execute(query)
    comments = result.scalars().all()
    return comments


# Issue Analytics
@router.get("/analytics/summary")
async def get_issue_analytics(
    project_id: int = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get issue analytics summary"""
    query = select(Issue)
    
    if project_id:
        query = query.where(Issue.project_id == project_id)
    
    result = await db.execute(query)
    issues = result.scalars().all()
    
    # Calculate metrics
    total_issues = len(issues)
    open_issues = len([i for i in issues if i.status in ["open", "in_progress"]])
    resolved_issues = len([i for i in issues if i.status == "resolved"])
    closed_issues = len([i for i in issues if i.status == "closed"])
    critical_issues = len([i for i in issues if i.severity == "critical" and i.status not in ["resolved", "closed"]])
    breached_sla = len([i for i in issues if i.sla_status == "breached"])
    
    # Average resolution time
    resolved = [i for i in issues if i.resolution_date and i.created_at]
    avg_resolution_days = 0
    if resolved:
        resolution_times = [(i.resolution_date - i.created_at).days for i in resolved]
        avg_resolution_days = sum(resolution_times) / len(resolution_times)
    
    # By category
    category_breakdown = {}
    for issue in issues:
        cat = issue.category.value
        if cat not in category_breakdown:
            category_breakdown[cat] = 0
        category_breakdown[cat] += 1

    # By severity
    severity_breakdown = {}
    for issue in issues:
        sev = issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity)
        severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

    # Aging buckets (for open/in_progress issues)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    aging = {"< 7 days": 0, "7-14 days": 0, "14-30 days": 0, "30+ days": 0}
    for issue in issues:
        if issue.status in ("open", "in_progress") and issue.created_at:
            created = issue.created_at if issue.created_at.tzinfo else issue.created_at.replace(tzinfo=timezone.utc)
            days_open = (now - created).days
            if days_open < 7:
                aging["< 7 days"] += 1
            elif days_open < 14:
                aging["7-14 days"] += 1
            elif days_open < 30:
                aging["14-30 days"] += 1
            else:
                aging["30+ days"] += 1

    return {
        "total": total_issues,
        "open": open_issues,
        "resolved": resolved_issues,
        "closed": closed_issues,
        "critical": critical_issues,
        "breached_sla": breached_sla,
        "avg_resolution_days": round(avg_resolution_days, 2),
        "category_breakdown": category_breakdown,
        "severity_breakdown": severity_breakdown,
        "aging": aging,
    }
