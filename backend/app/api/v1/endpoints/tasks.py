from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime
import os
import shutil
import uuid

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import Task, Comment, TaskDocument, TimeLog, TaskDependency
from app.schemas.schemas import (
    TaskCreate, TaskUpdate, TaskResponse,
    CommentBase, CommentResponse,
    TimeLogBase, TimeLogResponse,
    TaskDocumentResponse,
    TaskDependencyResponse,
)
from pydantic import BaseModel

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "../../../../../uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


class DependencyAdd(BaseModel):
    predecessor_id: int
    dependency_type: str = "finish_to_start"
    lag_days: int = 0


router = APIRouter()


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    current_user=Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new task"""
    db_task = Task(**task.dict())
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return db_task


@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    project_id: int = Query(None),
    status: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all tasks with filters"""
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status == status)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/calendar")
async def get_tasks_calendar(
    year: int = Query(...),
    month: int = Query(...),
    project_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tasks grouped by due date for a calendar month"""
    from calendar import monthrange
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month, monthrange(year, month)[1], 23, 59, 59)
    query = select(Task).where(Task.due_date >= first_day, Task.due_date <= last_day)
    if project_id:
        query = query.where(Task.project_id == project_id)
    result = await db.execute(query)
    tasks = result.scalars().all()
    tasks_by_date: dict[str, list] = {}
    for t in tasks:
        date_str = t.due_date.strftime("%Y-%m-%d")
        tasks_by_date.setdefault(date_str, []).append({
            "id": t.id, "title": t.title, "status": t.status,
            "priority": t.priority, "progress": t.progress,
            "project_id": t.project_id, "assignee_id": t.assignee_id,
        })
    return {"tasks_by_date": tasks_by_date}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single task by ID"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return db_task


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    current_user=Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Update a task"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    for field, value in task_update.dict(exclude_unset=True).items():
        setattr(db_task, field, value)
    await db.commit()
    await db.refresh(db_task)
    return db_task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    current_user=Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a task"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = result.scalar_one_or_none()
    if not db_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    await db.delete(db_task)
    await db.commit()


# ── Comments ──────────────────────────────────────────────────────────────────

@router.get("/{task_id}/comments", response_model=List[CommentResponse])
async def get_task_comments(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Comment).where(Comment.task_id == task_id).order_by(Comment.created_at.asc())
    )
    return result.scalars().all()


@router.post("/{task_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def add_task_comment(
    task_id: int,
    body: CommentBase,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    task_check = await db.execute(select(Task).where(Task.id == task_id))
    if not task_check.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db_comment = Comment(
        task_id=task_id,
        author_id=current_user.id,
        content=body.content,
    )
    db.add(db_comment)
    await db.commit()
    await db.refresh(db_comment)
    return db_comment


@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_comment(
    task_id: int,
    comment_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.task_id == task_id)
    )
    db_comment = result.scalar_one_or_none()
    if not db_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    await db.delete(db_comment)
    await db.commit()


# ── Time Logs ─────────────────────────────────────────────────────────────────

@router.get("/{task_id}/timelogs", response_model=List[TimeLogResponse])
async def get_task_timelogs(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TimeLog).where(TimeLog.task_id == task_id).order_by(TimeLog.date.desc())
    )
    return result.scalars().all()


@router.post("/{task_id}/timelogs", response_model=TimeLogResponse, status_code=status.HTTP_201_CREATED)
async def add_task_timelog(
    task_id: int,
    body: TimeLogBase,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    task_check = await db.execute(select(Task).where(Task.id == task_id))
    db_task = task_check.scalar_one_or_none()
    if not db_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    db_log = TimeLog(
        task_id=task_id,
        user_id=current_user.id,
        hours=body.hours,
        description=body.description,
        date=datetime.utcnow(),
    )
    db.add(db_log)
    # Update actual_hours on the task
    db_task.actual_hours = (db_task.actual_hours or 0) + body.hours
    await db.commit()
    await db.refresh(db_log)
    return db_log


@router.delete("/{task_id}/timelogs/{timelog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_timelog(
    task_id: int,
    timelog_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TimeLog).where(TimeLog.id == timelog_id, TimeLog.task_id == task_id)
    )
    db_log = result.scalar_one_or_none()
    if not db_log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time log not found")
    # Subtract hours from task
    task_result = await db.execute(select(Task).where(Task.id == task_id))
    db_task = task_result.scalar_one_or_none()
    if db_task:
        db_task.actual_hours = max(0, (db_task.actual_hours or 0) - db_log.hours)
    await db.delete(db_log)
    await db.commit()


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/{task_id}/documents", response_model=List[TaskDocumentResponse])
async def get_task_documents(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TaskDocument).where(TaskDocument.task_id == task_id).order_by(TaskDocument.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{task_id}/documents", response_model=TaskDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_task_document(
    task_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    task_check = await db.execute(select(Task).where(Task.id == task_id))
    if not task_check.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    safe_filename = f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload')}"
    file_path = os.path.join(UPLOADS_DIR, safe_filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    file_size = os.path.getsize(file_path)
    db_doc = TaskDocument(
        task_id=task_id,
        filename=file.filename or safe_filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file.content_type or "application/octet-stream",
        uploaded_by=current_user.id,
    )
    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)
    return db_doc


@router.delete("/{task_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_document(
    task_id: int,
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TaskDocument).where(TaskDocument.id == doc_id, TaskDocument.task_id == task_id)
    )
    db_doc = result.scalar_one_or_none()
    if not db_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if os.path.exists(db_doc.file_path):
        os.remove(db_doc.file_path)
    await db.delete(db_doc)
    await db.commit()


# ── Dependencies ──────────────────────────────────────────────────────────────

@router.get("/{task_id}/dependencies", response_model=List[TaskDependencyResponse])
async def get_task_dependencies(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TaskDependency).where(
            (TaskDependency.successor_id == task_id) | (TaskDependency.predecessor_id == task_id)
        )
    )
    return result.scalars().all()


@router.post("/{task_id}/dependencies", response_model=TaskDependencyResponse, status_code=status.HTTP_201_CREATED)
async def add_task_dependency(
    task_id: int,
    body: DependencyAdd,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if body.predecessor_id == task_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A task cannot depend on itself")
    db_dep = TaskDependency(
        predecessor_id=body.predecessor_id,
        successor_id=task_id,
        dependency_type=body.dependency_type,
        lag_days=body.lag_days,
    )
    db.add(db_dep)
    await db.commit()
    await db.refresh(db_dep)
    return db_dep


@router.delete("/{task_id}/dependencies/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_dependency(
    task_id: int,
    dep_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(TaskDependency).where(
            TaskDependency.id == dep_id,
            (TaskDependency.successor_id == task_id) | (TaskDependency.predecessor_id == task_id)
        )
    )
    db_dep = result.scalar_one_or_none()
    if not db_dep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dependency not found")
    await db.delete(db_dep)
    await db.commit()
