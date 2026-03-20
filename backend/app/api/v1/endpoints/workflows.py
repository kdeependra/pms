from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import (
    Workflow, WorkflowStage, WorkflowTransition, WorkflowInstance,
    WorkflowApproval, WorkflowHistory, User, Task, WorkflowStatus
)
from app.schemas.schemas import (
    WorkflowCreate, WorkflowUpdate, WorkflowResponse,
    WorkflowStageCreate, WorkflowStageUpdate, WorkflowStageResponse,
    WorkflowTransitionCreate, WorkflowTransitionUpdate, WorkflowTransitionResponse,
    WorkflowInstanceCreate, WorkflowInstanceUpdate, WorkflowInstanceResponse,
    WorkflowApprovalCreate, WorkflowApprovalAction, WorkflowApprovalResponse
)

router = APIRouter()


# ========== Workflow CRUD ==========
@router.post("/", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow: WorkflowCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow"""
    db_workflow = Workflow(
        **workflow.model_dump(),
        created_by=current_user.id
    )
    db.add(db_workflow)
    await db.commit()
    await db.refresh(db_workflow)
    
    # Load relationships
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages), selectinload(Workflow.transitions))
        .where(Workflow.id == db_workflow.id)
    )
    workflow_with_relations = result.scalar_one()
    
    return workflow_with_relations


@router.get("/", response_model=List[WorkflowResponse])
async def get_workflows(
    project_id: int = None,
    status: str = None,
    is_template: bool = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all workflows with optional filters"""
    query = select(Workflow).options(
        selectinload(Workflow.stages),
        selectinload(Workflow.transitions)
    )
    
    filters = []
    if project_id:
        filters.append(Workflow.project_id == project_id)
    if status:
        filters.append(Workflow.status == status)
    if is_template is not None:
        filters.append(Workflow.is_template == is_template)
    
    if filters:
        query = query.where(and_(*filters))
    
    query = query.order_by(Workflow.created_at.desc())
    
    result = await db.execute(query)
    workflows = result.scalars().all()
    
    return workflows


# ========== SPECIFIC ROUTES (MUST COME BEFORE /{workflow_id}) ==========

# ========== Workflow Approvals (Specific Routes) ==========
@router.get("/my-approvals", response_model=List[WorkflowApprovalResponse])
async def get_my_approvals(
    status: str = "pending",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all approvals assigned to current user"""
    query = select(WorkflowApproval).where(
        WorkflowApproval.approver_id == current_user.id
    )
    
    if status:
        query = query.where(WorkflowApproval.status == status)
    
    query = query.order_by(WorkflowApproval.requested_at.desc())
    
    result = await db.execute(query)
    approvals = result.scalars().all()
    return approvals


# ========== Workflow Stages ==========
@router.post("/stages", response_model=WorkflowStageResponse, status_code=status.HTTP_201_CREATED)
async def create_stage(
    stage: WorkflowStageCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow stage"""
    db_stage = WorkflowStage(**stage.model_dump())
    db.add(db_stage)
    await db.commit()
    await db.refresh(db_stage)
    return db_stage


@router.get("/stages/{stage_id}", response_model=WorkflowStageResponse)
async def get_stage(
    stage_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific stage"""
    result = await db.execute(select(WorkflowStage).where(WorkflowStage.id == stage_id))
    stage = result.scalar_one_or_none()
    
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    return stage


@router.put("/stages/{stage_id}", response_model=WorkflowStageResponse)
async def update_stage(
    stage_id: int,
    stage_update: WorkflowStageUpdate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow stage"""
    result = await db.execute(select(WorkflowStage).where(WorkflowStage.id == stage_id))
    db_stage = result.scalar_one_or_none()
    
    if not db_stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    update_data = stage_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_stage, field, value)
    
    await db.commit()
    await db.refresh(db_stage)
    return db_stage


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stage(
    stage_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow stage"""
    result = await db.execute(select(WorkflowStage).where(WorkflowStage.id == stage_id))
    stage = result.scalar_one_or_none()
    
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    await db.delete(stage)
    await db.commit()


# ========== Workflow Transitions ==========
@router.post("/transitions", response_model=WorkflowTransitionResponse, status_code=status.HTTP_201_CREATED)
async def create_transition(
    transition: WorkflowTransitionCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new workflow transition"""
    db_transition = WorkflowTransition(**transition.model_dump())
    db.add(db_transition)
    await db.commit()
    await db.refresh(db_transition)
    return db_transition


@router.put("/transitions/{transition_id}", response_model=WorkflowTransitionResponse)
async def update_transition(
    transition_id: int,
    transition_update: WorkflowTransitionUpdate,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow transition"""
    result = await db.execute(select(WorkflowTransition).where(WorkflowTransition.id == transition_id))
    db_transition = result.scalar_one_or_none()
    
    if not db_transition:
        raise HTTPException(status_code=404, detail="Transition not found")
    
    update_data = transition_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_transition, field, value)
    
    await db.commit()
    await db.refresh(db_transition)
    return db_transition


@router.delete("/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transition(
    transition_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow transition"""
    result = await db.execute(select(WorkflowTransition).where(WorkflowTransition.id == transition_id))
    transition = result.scalar_one_or_none()
    
    if not transition:
        raise HTTPException(status_code=404, detail="Transition not found")
    
    await db.delete(transition)
    await db.commit()


# ========== Workflow Instances ==========
@router.post("/instances", response_model=WorkflowInstanceResponse, status_code=status.HTTP_201_CREATED)
async def start_workflow_instance(
    instance: WorkflowInstanceCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Start a new workflow instance for a task"""
    # Get workflow with stages
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages))
        .where(Workflow.id == instance.workflow_id)
    )
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow.status != WorkflowStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Workflow is not active")
    
    # Find start stage
    start_stage = next((s for s in workflow.stages if s.stage_type == "start"), None)
    if not start_stage and workflow.stages:
        start_stage = min(workflow.stages, key=lambda s: s.order)
    
    # Create instance
    db_instance = WorkflowInstance(
        workflow_id=instance.workflow_id,
        task_id=instance.task_id,
        current_stage_id=start_stage.id if start_stage else None,
        started_by=current_user.id,
        instance_metadata=instance.instance_metadata,
        status="in_progress"
    )
    db.add(db_instance)
    await db.flush()
    
    # Create history entry
    history = WorkflowHistory(
        instance_id=db_instance.id,
        to_stage_id=start_stage.id if start_stage else None,
        action="started",
        performed_by=current_user.id,
        comments="Workflow instance started"
    )
    db.add(history)
    
    # Handle auto-assignment if configured
    if start_stage and start_stage.auto_assign:
        await assign_task_by_rule(db_instance.task_id, start_stage.assignment_rule, db)
    
    # Handle approval requirement
    if start_stage and start_stage.requires_approval:
        await create_approval_request(db_instance.id, start_stage, db)
    
    await db.commit()
    
    # Load and return instance with relationships
    result = await db.execute(
        select(WorkflowInstance)
        .options(
            selectinload(WorkflowInstance.approvals),
            selectinload(WorkflowInstance.history)
        )
        .where(WorkflowInstance.id == db_instance.id)
    )
    instance_with_relations = result.scalar_one()
    
    return instance_with_relations


@router.get("/instances/{instance_id}", response_model=WorkflowInstanceResponse)
async def get_workflow_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workflow instance"""
    result = await db.execute(
        select(WorkflowInstance)
        .options(
            selectinload(WorkflowInstance.approvals),
            selectinload(WorkflowInstance.history)
        )
        .where(WorkflowInstance.id == instance_id)
    )
    instance = result.scalar_one_or_none()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    
    return instance


@router.post("/instances/{instance_id}/transition/{to_stage_id}")
async def transition_workflow(
    instance_id: int,
    to_stage_id: int,
    comments: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Transition a workflow instance to another stage"""
    # Get instance
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == instance_id)
    )
    instance = result.scalar_one_or_none()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Workflow instance not found")
    
    if instance.status != "in_progress":
        raise HTTPException(status_code=400, detail="Workflow instance is not in progress")
    
    # Get target stage
    result = await db.execute(
        select(WorkflowStage).where(WorkflowStage.id == to_stage_id)
    )
    to_stage = result.scalar_one_or_none()
    
    if not to_stage:
        raise HTTPException(status_code=404, detail="Target stage not found")
    
    # Verify transition exists
    if instance.current_stage_id:
        result = await db.execute(
            select(WorkflowTransition).where(
                and_(
                    WorkflowTransition.workflow_id == instance.workflow_id,
                    WorkflowTransition.from_stage_id == instance.current_stage_id,
                    WorkflowTransition.to_stage_id == to_stage_id
                )
            )
        )
        transition = result.scalar_one_or_none()
        
        if not transition:
            raise HTTPException(status_code=400, detail="Invalid transition")
        
        # Check conditional logic if applicable
        if transition.condition_type == "conditional" and transition.condition_logic:
            # Evaluate conditions
            if not await evaluate_conditions(instance.task_id, transition.condition_logic, db):
                raise HTTPException(status_code=400, detail="Transition conditions not met")
    
    # Update instance
    from_stage_id = instance.current_stage_id
    instance.current_stage_id = to_stage_id
    
    # Check if workflow is complete
    if to_stage.stage_type == "end":
        instance.status = "completed"
        instance.completed_at = datetime.now()
    
    # Create history entry
    history = WorkflowHistory(
        instance_id=instance.id,
        from_stage_id=from_stage_id,
        to_stage_id=to_stage_id,
        action="transitioned",
        performed_by=current_user.id,
        comments=comments
    )
    db.add(history)
    
    # Handle auto-assignment for new stage
    if to_stage.auto_assign:
        await assign_task_by_rule(instance.task_id, to_stage.assignment_rule, db)
    
    # Handle approval requirement for new stage
    if to_stage.requires_approval:
        await create_approval_request(instance.id, to_stage, db)
    
    await db.commit()
    
    return {"message": "Workflow transitioned successfully", "current_stage_id": to_stage_id}


@router.get("/instances/{instance_id}/approvals", response_model=List[WorkflowApprovalResponse])
async def get_pending_approvals(
    instance_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get pending approvals for a workflow instance"""
    result = await db.execute(
        select(WorkflowApproval).where(
            and_(
                WorkflowApproval.instance_id == instance_id,
                WorkflowApproval.status == "pending"
            )
        )
    )
    approvals = result.scalars().all()
    return approvals


@router.post("/approvals/{approval_id}/action")
async def action_approval(
    approval_id: int,
    action: WorkflowApprovalAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Approve or reject a workflow approval request"""
    # Get approval
    result = await db.execute(
        select(WorkflowApproval).where(WorkflowApproval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    
    if approval.approver_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to approve")
    
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="Approval already processed")
    
    # Update approval
    approval.status = action.status
    approval.comments = action.comments
    approval.responded_at = datetime.now()
    
    # Get instance
    result = await db.execute(
        select(WorkflowInstance).where(WorkflowInstance.id == approval.instance_id)
    )
    instance = result.scalar_one_or_none()
    
    # Create history entry
    history = WorkflowHistory(
        instance_id=approval.instance_id,
        action=action.status,
        performed_by=current_user.id,
        comments=action.comments
    )
    db.add(history)
    
    # If approved, find and execute next transition
    if action.status == "approved":
        # Find transition for approved path
        result = await db.execute(
            select(WorkflowTransition).where(
                and_(
                    WorkflowTransition.workflow_id == instance.workflow_id,
                    WorkflowTransition.from_stage_id == approval.stage_id,
                    WorkflowTransition.condition_type == "approved"
                )
            )
        )
        transition = result.scalar_one_or_none()
        
        if transition:
            # Get target stage
            result = await db.execute(
                select(WorkflowStage).where(WorkflowStage.id == transition.to_stage_id)
            )
            to_stage = result.scalar_one_or_none()
            
            # Update instance
            instance.current_stage_id = transition.to_stage_id
            
            # Check if workflow is complete
            if to_stage and to_stage.stage_type == "end":
                instance.status = "completed"
                instance.completed_at = datetime.now()
            
            # Handle auto-assignment for new stage
            if to_stage and to_stage.auto_assign:
                await assign_task_by_rule(instance.task_id, to_stage.assignment_rule, db)
    
    elif action.status == "rejected":
        # Find transition for rejected path
        result = await db.execute(
            select(WorkflowTransition).where(
                and_(
                    WorkflowTransition.workflow_id == instance.workflow_id,
                    WorkflowTransition.from_stage_id == approval.stage_id,
                    WorkflowTransition.condition_type == "rejected"
                )
            )
        )
        transition = result.scalar_one_or_none()
        
        if transition:
            instance.current_stage_id = transition.to_stage_id
        else:
            # No rejected path, cancel workflow
            instance.status = "cancelled"
            instance.completed_at = datetime.now()
    
    await db.commit()
    
    return {"message": f"Approval {action.status} successfully"}


# ========== GENERIC ROUTES (COME AFTER SPECIFIC ROUTES) ==========
@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific workflow by ID"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages), selectinload(Workflow.transitions))
        .where(Workflow.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: int,
    workflow_update: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a workflow"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    db_workflow = result.scalar_one_or_none()
    
    if not db_workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    update_data = workflow_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_workflow, field, value)
    
    await db.commit()
    await db.refresh(db_workflow)
    
    # Load relationships
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages), selectinload(Workflow.transitions))
        .where(Workflow.id == workflow_id)
    )
    workflow_with_relations = result.scalar_one()
    
    return workflow_with_relations


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a workflow"""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    await db.delete(workflow)
    await db.commit()


@router.post("/{workflow_id}/duplicate", response_model=WorkflowResponse)
async def duplicate_workflow(
    workflow_id: int,
    new_name: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Duplicate an existing workflow"""
    # Get original workflow with stages and transitions
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages), selectinload(Workflow.transitions))
        .where(Workflow.id == workflow_id)
    )
    original = result.scalar_one_or_none()
    
    if not original:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Create new workflow
    new_workflow = Workflow(
        name=new_name or f"{original.name} (Copy)",
        description=original.description,
        project_id=original.project_id,
        created_by=current_user.id,
        status=WorkflowStatus.DRAFT,
        is_template=original.is_template
    )
    db.add(new_workflow)
    await db.flush()
    
    # Map old stage IDs to new stage IDs
    stage_id_map = {}
    
    # Duplicate stages
    for stage in original.stages:
        new_stage = WorkflowStage(
            workflow_id=new_workflow.id,
            name=stage.name,
            description=stage.description,
            stage_type=stage.stage_type,
            requires_approval=stage.requires_approval,
            approver_role=stage.approver_role,
            approver_user_id=stage.approver_user_id,
            auto_assign=stage.auto_assign,
            assignment_rule=stage.assignment_rule,
            position_x=stage.position_x,
            position_y=stage.position_y,
            order=stage.order
        )
        db.add(new_stage)
        await db.flush()
        stage_id_map[stage.id] = new_stage.id
    
    # Duplicate transitions with updated stage IDs
    for transition in original.transitions:
        new_transition = WorkflowTransition(
            workflow_id=new_workflow.id,
            from_stage_id=stage_id_map[transition.from_stage_id],
            to_stage_id=stage_id_map[transition.to_stage_id],
            name=transition.name,
            condition_type=transition.condition_type,
            condition_logic=transition.condition_logic,
            order=transition.order
        )
        db.add(new_transition)
    
    await db.commit()
    
    # Load and return new workflow with relationships
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.stages), selectinload(Workflow.transitions))
        .where(Workflow.id == new_workflow.id)
    )
    duplicated_workflow = result.scalar_one()
    
    return duplicated_workflow

# ========== Helper Functions ==========

async def create_approval_request(instance_id: int, stage: WorkflowStage, db: AsyncSession):
    """Create an approval request for a stage"""
    approver_id = None
    
    if stage.approver_user_id:
        approver_id = stage.approver_user_id
    elif stage.approver_role:
        # Find first user with matching role
        result = await db.execute(
            select(User).where(
                and_(
                    User.role == stage.approver_role,
                    User.is_active == True
                )
            ).limit(1)
        )
        user = result.scalar_one_or_none()
        if user:
            approver_id = user.id
    
    if approver_id:
        approval = WorkflowApproval(
            instance_id=instance_id,
            stage_id=stage.id,
            approver_id=approver_id,
            status="pending"
        )
        db.add(approval)


async def assign_task_by_rule(task_id: int, assignment_rule: dict, db: AsyncSession):
    """Assign task based on assignment rules"""
    if not assignment_rule:
        return
    
    rule_type = assignment_rule.get("rule_type")
    
    # Get task
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        return
    
    assignee = None
    
    if rule_type == "role":
        # Assign to user with specific role
        target_role = assignment_rule.get("target_role")
        result = await db.execute(
            select(User).where(
                and_(
                    User.role == target_role,
                    User.is_active == True
                )
            ).limit(1)
        )
        assignee = result.scalar_one_or_none()
    
    elif rule_type == "department":
        # Assign to user in specific department
        target_dept = assignment_rule.get("target_department")
        result = await db.execute(
            select(User).where(
                and_(
                    User.department == target_dept,
                    User.is_active == True
                )
            ).limit(1)
        )
        assignee = result.scalar_one_or_none()
    
    elif rule_type == "round_robin":
        # Assign to user with least tasks
        result = await db.execute(
            select(User, func.count(Task.id).label('task_count'))
            .outerjoin(Task, Task.assignee_id == User.id)
            .where(User.is_active == True)
            .group_by(User.id)
            .order_by(func.count(Task.id))
            .limit(1)
        )
        row = result.first()
        if row:
            assignee = row[0]
    
    if assignee:
        task.assignee_id = assignee.id


async def evaluate_conditions(task_id: int, condition_logic: dict, db: AsyncSession) -> bool:
    """Evaluate conditional logic for workflow transitions"""
    if not condition_logic:
        return True
    
    # Get task
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        return False
    
    field = condition_logic.get("field")
    operator = condition_logic.get("operator")
    value = condition_logic.get("value")
    
    if not field or not operator:
        return True
    
    # Get field value from task
    task_value = getattr(task, field, None)
    
    if task_value is None:
        return False
    
    # Evaluate based on operator
    if operator == "equals":
        return str(task_value) == str(value)
    elif operator == "not_equals":
        return str(task_value) != str(value)
    elif operator == "greater_than":
        try:
            return float(task_value) > float(value)
        except:
            return False
    elif operator == "less_than":
        try:
            return float(task_value) < float(value)
        except:
            return False
    elif operator == "contains":
        return str(value).lower() in str(task_value).lower()
    
    return True
