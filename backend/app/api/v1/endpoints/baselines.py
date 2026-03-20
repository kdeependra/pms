from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.models import ProjectBaseline, TaskBaseline, MilestoneBaseline, Task, Milestone
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.post("/projects/{project_id}/baselines")
async def create_baseline(
    project_id: int,
    name: str,
    description: str = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new project baseline snapshot.
    Captures current state of all tasks and milestones.
    """
    # Create baseline record
    baseline = ProjectBaseline(
        project_id=project_id,
        name=name,
        description=description,
        created_by=current_user.id,
        is_active=True
    )
    db.add(baseline)
    await db.flush()
    
    # Capture all tasks for this project
    result = await db.execute(
        select(Task).where(Task.project_id == project_id)
    )
    tasks = result.scalars().all()
    
    for task in tasks:
        t_start = task.created_at
        t_end = task.due_date
        t_dur = (t_end.date() - t_start.date()).days if t_end and t_start else None
        task_baseline = TaskBaseline(
            baseline_id=baseline.id,
            task_id=task.id,
            baseline_start_date=t_start,
            baseline_end_date=t_end,
            baseline_duration=t_dur,
            baseline_estimated_hours=task.estimated_hours,
            baseline_status=task.status,
            baseline_progress=task.progress
        )
        db.add(task_baseline)
    
    # Capture all milestones for this project
    result = await db.execute(
        select(Milestone).where(Milestone.project_id == project_id)
    )
    milestones = result.scalars().all()
    
    for milestone in milestones:
        milestone_baseline = MilestoneBaseline(
            baseline_id=baseline.id,
            milestone_id=milestone.id,
            baseline_due_date=milestone.target_date,
            baseline_status=milestone.status
        )
        db.add(milestone_baseline)
    
    await db.commit()
    await db.refresh(baseline)
    
    return {
        "id": baseline.id,
        "project_id": baseline.project_id,
        "name": baseline.name,
        "description": baseline.description,
        "baseline_date": baseline.baseline_date,
        "created_at": baseline.created_at,
        "task_count": len(tasks),
        "milestone_count": len(milestones)
    }


@router.get("/projects/{project_id}/baselines")
async def get_project_baselines(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all baselines for a project."""
    result = await db.execute(
        select(ProjectBaseline)
        .where(ProjectBaseline.project_id == project_id)
        .order_by(ProjectBaseline.created_at.desc())
    )
    baselines = result.scalars().all()
    
    return [
        {
            "id": b.id,
            "project_id": b.project_id,
            "name": b.name,
            "description": b.description,
            "baseline_date": b.baseline_date,
            "is_active": b.is_active,
            "created_at": b.created_at
        }
        for b in baselines
    ]


@router.get("/baselines/{baseline_id}/comparison")
async def compare_with_baseline(
    baseline_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compare current project state with baseline.
    Returns variance analysis for tasks and milestones.
    """
    # Get baseline
    result = await db.execute(
        select(ProjectBaseline).where(ProjectBaseline.id == baseline_id)
    )
    baseline = result.scalar_one_or_none()
    
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    
    # Get task baselines with current task data
    result = await db.execute(
        select(TaskBaseline, Task)
        .join(Task, TaskBaseline.task_id == Task.id)
        .where(TaskBaseline.baseline_id == baseline_id)
    )
    task_comparisons = result.all()
    
    task_variance = []
    for task_baseline, current_task in task_comparisons:
        # Calculate variances
        cur_start = current_task.created_at
        cur_end = current_task.due_date
        cur_dur = (cur_end.date() - cur_start.date()).days if cur_end and cur_start else None

        start_variance = None
        if task_baseline.baseline_start_date and cur_start:
            start_variance = (cur_start - task_baseline.baseline_start_date).days
        
        end_variance = None
        if task_baseline.baseline_end_date and cur_end:
            end_variance = (cur_end - task_baseline.baseline_end_date).days
        
        duration_variance = None
        if task_baseline.baseline_duration and cur_dur:
            duration_variance = cur_dur - task_baseline.baseline_duration
        
        progress_variance = current_task.progress - task_baseline.baseline_progress
        
        task_variance.append({
            "task_id": current_task.id,
            "task_name": current_task.title,
            "baseline": {
                "start_date": task_baseline.baseline_start_date,
                "end_date": task_baseline.baseline_end_date,
                "duration": task_baseline.baseline_duration,
                "status": task_baseline.baseline_status,
                "progress": task_baseline.baseline_progress
            },
            "current": {
                "start_date": cur_start,
                "end_date": cur_end,
                "duration": cur_dur,
                "status": current_task.status,
                "progress": current_task.progress
            },
            "variance": {
                "start_days": start_variance,
                "end_days": end_variance,
                "duration_days": duration_variance,
                "progress_percent": progress_variance,
                "is_delayed": end_variance > 0 if end_variance else False
            }
        })
    
    # Get milestone baselines with current milestone data
    result = await db.execute(
        select(MilestoneBaseline, Milestone)
        .join(Milestone, MilestoneBaseline.milestone_id == Milestone.id)
        .where(MilestoneBaseline.baseline_id == baseline_id)
    )
    milestone_comparisons = result.all()
    
    milestone_variance = []
    for milestone_baseline, current_milestone in milestone_comparisons:
        due_date_variance = None
        if milestone_baseline.baseline_due_date and current_milestone.target_date:
            due_date_variance = (current_milestone.target_date - milestone_baseline.baseline_due_date).days
        
        milestone_variance.append({
            "milestone_id": current_milestone.id,
            "milestone_name": current_milestone.name,
            "baseline": {
                "due_date": milestone_baseline.baseline_due_date,
                "status": milestone_baseline.baseline_status
            },
            "current": {
                "due_date": current_milestone.target_date,
                "status": current_milestone.status
            },
            "variance": {
                "days": due_date_variance,
                "is_delayed": due_date_variance > 0 if due_date_variance else False
            }
        })
    
    # Calculate summary statistics
    delayed_tasks = sum(1 for t in task_variance if t["variance"].get("is_delayed"))
    delayed_milestones = sum(1 for m in milestone_variance if m["variance"].get("is_delayed"))
    
    return {
        "baseline": {
            "id": baseline.id,
            "name": baseline.name,
            "baseline_date": baseline.baseline_date
        },
        "summary": {
            "total_tasks": len(task_variance),
            "delayed_tasks": delayed_tasks,
            "on_track_tasks": len(task_variance) - delayed_tasks,
            "total_milestones": len(milestone_variance),
            "delayed_milestones": delayed_milestones,
            "on_track_milestones": len(milestone_variance) - delayed_milestones
        },
        "tasks": task_variance,
        "milestones": milestone_variance
    }


@router.delete("/baselines/{baseline_id}")
async def delete_baseline(
    baseline_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a project baseline."""
    result = await db.execute(
        select(ProjectBaseline).where(ProjectBaseline.id == baseline_id)
    )
    baseline = result.scalar_one_or_none()
    
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    
    await db.delete(baseline)
    await db.commit()
    
    return {"message": "Baseline deleted successfully"}
