from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import List, Dict
from datetime import datetime, timedelta
import math

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import (
    KanbanBoard, KanbanColumn, GanttView, Project, Task, TaskDependency, TaskBaseline, User
)
from app.schemas.schemas import (
    KanbanBoardCreate, KanbanBoardResponse,
    KanbanColumnCreate, KanbanColumnResponse,
    GanttViewCreate, GanttViewResponse
)

router = APIRouter()


# Kanban Boards
@router.post("/kanban", response_model=KanbanBoardResponse, status_code=status.HTTP_201_CREATED)
async def create_kanban_board(
    board: KanbanBoardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new Kanban board"""
    # Verify project exists
    project_query = select(Project).where(Project.id == board.project_id)
    result = await db.execute(project_query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Create board
    db_board = KanbanBoard(
        project_id=board.project_id,
        name=board.name,
        description=board.description,
        is_default=board.is_default,
        created_by=current_user.id
    )
    
    db.add(db_board)
    await db.flush()  # Get the board ID
    
    # Create columns if provided
    if board.columns:
        for col in board.columns:
            db_column = KanbanColumn(
                board_id=db_board.id,
                **col.dict()
            )
            db.add(db_column)
    else:
        # Create default columns if none provided
        default_columns = [
            {"name": "To Do", "order": 0, "task_status_mapping": "todo", "color": "#e3e3e3"},
            {"name": "In Progress", "order": 1, "task_status_mapping": "in_progress", "color": "#ffd700"},
            {"name": "Review", "order": 2, "task_status_mapping": "review", "color": "#87ceeb"},
            {"name": "Done", "order": 3, "task_status_mapping": "done", "color": "#90ee90", "is_done_column": True}
        ]
        
        for col_data in default_columns:
            db_column = KanbanColumn(
                board_id=db_board.id,
                **col_data
            )
            db.add(db_column)
    
    await db.commit()
    
    # Re-query board with columns eagerly loaded
    result = await db.execute(
        select(KanbanBoard)
        .options(selectinload(KanbanBoard.columns))
        .where(KanbanBoard.id == db_board.id)
    )
    db_board = result.scalar_one()
    
    return db_board


@router.get("/kanban", response_model=List[KanbanBoardResponse])
async def get_kanban_boards(
    project_id: int = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Kanban boards"""
    query = select(KanbanBoard).options(selectinload(KanbanBoard.columns))
    
    if project_id:
        query = query.where(KanbanBoard.project_id == project_id)
    
    result = await db.execute(query)
    boards = result.scalars().all()
    
    return boards


@router.get("/kanban/{board_id}", response_model=KanbanBoardResponse)
async def get_kanban_board(
    board_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific Kanban board"""
    query = select(KanbanBoard).where(KanbanBoard.id == board_id)
    result = await db.execute(query)
    board = result.scalar_one_or_none()
    
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban board not found"
        )
    
    # Load columns
    columns_query = select(KanbanColumn).where(
        KanbanColumn.board_id == board.id
    ).order_by(KanbanColumn.order)
    result = await db.execute(columns_query)
    board.columns = result.scalars().all()
    
    return board


@router.get("/kanban/{board_id}/tasks")
async def get_kanban_board_with_tasks(
    board_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Kanban board with tasks organized by columns"""
    # Get board
    board_query = select(KanbanBoard).where(KanbanBoard.id == board_id)
    result = await db.execute(board_query)
    board = result.scalar_one_or_none()
    
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban board not found"
        )
    
    # Get columns
    columns_query = select(KanbanColumn).where(
        KanbanColumn.board_id == board.id
    ).order_by(KanbanColumn.order)
    result = await db.execute(columns_query)
    columns = result.scalars().all()
    
    # Get tasks for the project with assignee info
    tasks_query = select(Task).options(selectinload(Task.assignee)).where(Task.project_id == board.project_id)
    result = await db.execute(tasks_query)
    all_tasks = result.scalars().all()
    
    # Organize tasks by column
    columns_with_tasks = []
    for column in columns:
        column_tasks = [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "assignee_id": task.assignee_id,
                "assignee_name": (task.assignee.full_name or task.assignee.username) if task.assignee else None,
                "priority": task.priority,
                "due_date": task.due_date,
                "progress": task.progress
            }
            for task in all_tasks
            if task.status == column.task_status_mapping
        ]
        
        columns_with_tasks.append({
            "id": column.id,
            "name": column.name,
            "color": column.color,
            "order": column.order,
            "wip_limit": column.wip_limit,
            "task_count": len(column_tasks),
            "tasks": column_tasks
        })
    
    return {
        "board_id": board.id,
        "board_name": board.name,
        "project_id": board.project_id,
        "columns": columns_with_tasks
    }


@router.put("/kanban/{board_id}")
async def update_kanban_board(
    board_id: int,
    name: str = Query(None),
    description: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a Kanban board"""
    query = select(KanbanBoard).where(KanbanBoard.id == board_id)
    result = await db.execute(query)
    board = result.scalar_one_or_none()
    
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban board not found"
        )
    
    if name:
        board.name = name
    if description:
        board.description = description
    
    await db.commit()
    await db.refresh(board)
    return board


@router.delete("/kanban/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kanban_board(
    board_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a Kanban board"""
    query = select(KanbanBoard).where(KanbanBoard.id == board_id)
    result = await db.execute(query)
    board = result.scalar_one_or_none()
    
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban board not found"
        )
    
    await db.delete(board)
    await db.commit()


# Kanban Columns
@router.post("/kanban/{board_id}/columns", response_model=KanbanColumnResponse, status_code=status.HTTP_201_CREATED)
async def create_kanban_column(
    board_id: int,
    column: KanbanColumnCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a column to a Kanban board"""
    # Verify board exists
    board_query = select(KanbanBoard).where(KanbanBoard.id == board_id)
    result = await db.execute(board_query)
    board = result.scalar_one_or_none()
    
    if not board:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban board not found"
        )
    
    db_column = KanbanColumn(
        board_id=board_id,
        **column.dict()
    )
    
    db.add(db_column)
    await db.commit()
    await db.refresh(db_column)
    return db_column


@router.put("/kanban/columns/{column_id}", response_model=KanbanColumnResponse)
async def update_kanban_column(
    column_id: int,
    column_update: KanbanColumnCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a Kanban column"""
    query = select(KanbanColumn).where(KanbanColumn.id == column_id)
    result = await db.execute(query)
    db_column = result.scalar_one_or_none()
    
    if not db_column:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban column not found"
        )
    
    update_data = column_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_column, key, value)
    
    await db.commit()
    await db.refresh(db_column)
    return db_column


@router.delete("/kanban/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kanban_column(
    column_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a Kanban column"""
    query = select(KanbanColumn).where(KanbanColumn.id == column_id)
    result = await db.execute(query)
    column = result.scalar_one_or_none()
    
    if not column:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kanban column not found"
        )
    
    await db.delete(column)
    await db.commit()


# ── Kanban Task Move (with WIP limit enforcement) ────────────────────────────

@router.put("/kanban/{board_id}/tasks/{task_id}/move")
async def move_kanban_task(
    board_id: int,
    task_id: int,
    target_column_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move a task to a different Kanban column, enforcing WIP limits."""
    # Verify board
    board_q = select(KanbanBoard).where(KanbanBoard.id == board_id)
    board = (await db.execute(board_q)).scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    # Verify target column belongs to this board
    col_q = select(KanbanColumn).where(KanbanColumn.id == target_column_id, KanbanColumn.board_id == board_id)
    column = (await db.execute(col_q)).scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=404, detail="Column not found on this board")

    # Verify task exists and belongs to the board's project
    task_q = select(Task).where(Task.id == task_id, Task.project_id == board.project_id)
    task = (await db.execute(task_q)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found in this project")

    # WIP limit check: count tasks currently in target column
    if column.wip_limit and column.wip_limit > 0:
        count_q = select(Task).where(
            Task.project_id == board.project_id,
            Task.status == column.task_status_mapping,
            Task.id != task_id,  # exclude the task being moved
        )
        current_count = len((await db.execute(count_q)).scalars().all())
        if current_count >= column.wip_limit:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"WIP limit reached for column '{column.name}' (limit: {column.wip_limit})",
            )

    # Move task
    task.status = column.task_status_mapping
    if column.is_done_column:
        task.progress = 100
    await db.commit()
    await db.refresh(task)

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "progress": task.progress,
        "column_id": column.id,
        "column_name": column.name,
    }


# Gantt Views
@router.post("/gantt", response_model=GanttViewResponse, status_code=status.HTTP_201_CREATED)
async def create_gantt_view(
    view: GanttViewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new Gantt chart view"""
    # Verify project exists
    project_query = select(Project).where(Project.id == view.project_id)
    result = await db.execute(project_query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    db_view = GanttView(
        **view.dict(),
        created_by=current_user.id
    )
    
    db.add(db_view)
    await db.commit()
    await db.refresh(db_view)
    return db_view


@router.get("/gantt", response_model=List[GanttViewResponse])
async def get_gantt_views(
    project_id: int = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get Gantt chart views"""
    query = select(GanttView)
    
    if project_id:
        query = query.where(GanttView.project_id == project_id)
    
    result = await db.execute(query)
    views = result.scalars().all()
    return views


@router.get("/gantt/{view_id}", response_model=GanttViewResponse)
async def get_gantt_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific Gantt chart view"""
    query = select(GanttView).where(GanttView.id == view_id)
    result = await db.execute(query)
    view = result.scalar_one_or_none()
    
    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gantt view not found"
        )
    
    return view


@router.put("/gantt/{view_id}", response_model=GanttViewResponse)
async def update_gantt_view(
    view_id: int,
    view_update: GanttViewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a Gantt chart view"""
    query = select(GanttView).where(GanttView.id == view_id)
    result = await db.execute(query)
    db_view = result.scalar_one_or_none()
    
    if not db_view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gantt view not found"
        )
    
    update_data = view_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_view, key, value)
    
    await db.commit()
    await db.refresh(db_view)
    return db_view


@router.delete("/gantt/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gantt_view(
    view_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a Gantt chart view"""
    query = select(GanttView).where(GanttView.id == view_id)
    result = await db.execute(query)
    view = result.scalar_one_or_none()
    
    if not view:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gantt view not found"
        )
    
    await db.delete(view)
    await db.commit()


# ─── Gantt-specific data endpoints ───────────────────────────────────────────

@router.get("/gantt/tasks/{project_id}")
async def get_gantt_tasks(
    project_id: int,
    status_filter: str = Query(None, description="Comma-separated statuses to include"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Return tasks formatted for Gantt chart rendering.
    Derives start_date from created_at and end_date from due_date.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
    result = await db.execute(query)
    tasks = result.scalars().all()

    task_ids = [t.id for t in tasks]

    # Load dependencies
    dep_result = await db.execute(
        select(TaskDependency).where(
            or_(
                TaskDependency.predecessor_id.in_(task_ids),
                TaskDependency.successor_id.in_(task_ids)
            )
        )
    )
    deps = dep_result.scalars().all()
    predecessors: Dict[int, List[int]] = {t.id: [] for t in tasks}
    for dep in deps:
        if dep.successor_id in predecessors:
            predecessors[dep.successor_id].append(dep.predecessor_id)

    # Apply status filter
    statuses = [s.strip() for s in status_filter.split(",")] if status_filter else None

    today = datetime.utcnow()
    gantt_tasks = []
    for task in tasks:
        if statuses and task.status not in statuses:
            continue
        start = task.created_at if task.created_at else today
        if task.due_date:
            end = task.due_date
        elif task.estimated_hours:
            end = start + timedelta(hours=task.estimated_hours)
        else:
            end = start + timedelta(days=7)
        duration_days = max(1, (end.date() - start.date()).days if end.date() > start.date() else 1)
        gantt_tasks.append({
            "id": task.id,
            "name": task.title,
            "start_date": start.strftime('%Y-%m-%d'),
            "end_date": end.strftime('%Y-%m-%d'),
            "duration": duration_days,
            "progress": task.progress,
            "status": task.status,
            "priority": task.priority,
            "assignee_id": task.assignee_id,
            "dependencies": predecessors.get(task.id, []),
        })

    return gantt_tasks


@router.get("/gantt/critical-path/{project_id}")
async def get_critical_path(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compute critical path using CPM (forward + backward pass).
    Returns list of task IDs, total project duration, and per-task float values.
    """
    result = await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
    )
    tasks = result.scalars().all()

    if not tasks:
        return {"critical_task_ids": [], "total_duration": 0, "task_details": []}

    task_ids = [t.id for t in tasks]
    task_map = {t.id: t for t in tasks}

    dep_result = await db.execute(
        select(TaskDependency).where(TaskDependency.predecessor_id.in_(task_ids))
    )
    deps = dep_result.scalars().all()

    predecessors: Dict[int, List[int]] = {t.id: [] for t in tasks}
    successors: Dict[int, List[int]] = {t.id: [] for t in tasks}
    for dep in deps:
        if dep.successor_id in predecessors:
            predecessors[dep.successor_id].append(dep.predecessor_id)
        if dep.predecessor_id in successors:
            successors[dep.predecessor_id].append(dep.successor_id)

    def get_dur(task: Task) -> int:
        if task.due_date and task.created_at:
            d = (task.due_date.date() - task.created_at.date()).days
            return max(1, d)
        if task.estimated_hours:
            return max(1, math.ceil(task.estimated_hours / 8))
        return 1

    # Topological sort (Kahn's algorithm)
    in_degree = {t.id: len(predecessors[t.id]) for t in tasks}
    queue = [t.id for t in tasks if in_degree[t.id] == 0]
    topo_order: List[int] = []
    while queue:
        tid = queue.pop(0)
        topo_order.append(tid)
        for suc in successors[tid]:
            in_degree[suc] -= 1
            if in_degree[suc] == 0:
                queue.append(suc)
    # Any remaining (cycle) tasks
    for tid in task_ids:
        if tid not in topo_order:
            topo_order.append(tid)

    # Forward pass
    ES: Dict[int, int] = {}
    EF: Dict[int, int] = {}
    for tid in topo_order:
        dur = get_dur(task_map[tid])
        ES[tid] = max((EF[p] for p in predecessors[tid] if p in EF), default=0)
        EF[tid] = ES[tid] + dur

    total_duration = max(EF.values()) if EF else 0

    # Backward pass
    LF: Dict[int, int] = {}
    LS: Dict[int, int] = {}
    for tid in reversed(topo_order):
        dur = get_dur(task_map[tid])
        LF[tid] = min((LS[s] for s in successors[tid] if s in LS), default=total_duration)
        LS[tid] = LF[tid] - dur

    critical_ids = []
    task_details = []
    for tid in task_ids:
        dur = get_dur(task_map[tid])
        float_days = LS.get(tid, 0) - ES.get(tid, 0)
        is_critical = float_days == 0 and dur > 0
        if is_critical:
            critical_ids.append(tid)
        task_details.append({
            "task_id": tid,
            "task_name": task_map[tid].title,
            "es": ES.get(tid, 0),
            "ef": EF.get(tid, 0),
            "ls": LS.get(tid, 0),
            "lf": LF.get(tid, 0),
            "float_days": float_days,
            "is_critical": is_critical,
            "duration": dur,
        })

    return {
        "critical_task_ids": critical_ids,
        "total_duration": total_duration,
        "task_details": task_details,
    }


@router.get("/baselines/{baseline_id}/gantt-tasks")
async def get_baseline_gantt_tasks(
    baseline_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Return task baseline data for Gantt baseline comparison overlay."""
    result = await db.execute(
        select(TaskBaseline, Task)
        .join(Task, TaskBaseline.task_id == Task.id)
        .where(TaskBaseline.baseline_id == baseline_id)
    )
    rows = result.all()
    return [
        {
            "task_id": tb.task_id,
            "task_name": task.title,
            "baseline_start_date": tb.baseline_start_date.strftime('%Y-%m-%d') if tb.baseline_start_date else None,
            "baseline_end_date": tb.baseline_end_date.strftime('%Y-%m-%d') if tb.baseline_end_date else None,
            "baseline_duration": tb.baseline_duration,
            "baseline_progress": tb.baseline_progress,
            "baseline_status": tb.baseline_status,
        }
        for tb, task in rows
    ]
