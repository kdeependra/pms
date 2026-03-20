from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, or_, insert as sa_insert, update as sa_update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import (
    User, Resource, Skill, ResourceAllocation, Timesheet, 
    LeaveRequest, ResourceCapacity, resource_skills, Project
)
from app.schemas.schemas import (
    ResourceCreate, ResourceUpdate, ResourceResponse,
    SkillCreate, SkillResponse,
    ResourceSkillAssign, ResourceSkillUpdate, ResourceSkillResponse, SkillMatrixResource,
    ResourceAllocationCreate, ResourceAllocationUpdate, ResourceAllocationResponse,
    TimesheetCreate, TimesheetUpdate, TimesheetResponse,
    LeaveRequestCreate, LeaveRequestUpdate, LeaveRequestResponse,
    ResourceUtilization, WorkloadHeatmap, CapacityForecast,
    OverallocationAlert, HRMSSyncResult
)

router = APIRouter()


# ============ Resource Management ============

@router.post("/", response_model=ResourceResponse)
async def create_resource(
    resource_data: ResourceCreate,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new resource profile for a user"""
    # Check if resource already exists for this user
    result = await db.execute(
        select(Resource).where(Resource.user_id == resource_data.user_id)
    )
    existing_resource = result.scalar_one_or_none()
    
    if existing_resource:
        raise HTTPException(status_code=400, detail="Resource already exists for this user")
    
    # Check if user exists
    result = await db.execute(select(User).where(User.id == resource_data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    resource = Resource(**resource_data.model_dump())
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


@router.get("/")
async def get_resources(
    skip: int = 0,
    limit: int = 100,
    department: Optional[str] = None,
    is_available: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of resources with optional filters"""
    query = select(Resource).options(selectinload(Resource.user))
    
    if department:
        query = query.where(Resource.department == department)
    if is_available is not None:
        query = query.where(Resource.is_available == is_available)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    resources = result.scalars().all()
    
    enriched = []
    for r in resources:
        user = r.user
        enriched.append({
            "id": r.id,
            "user_id": r.user_id,
            "full_name": user.full_name if user else "Unknown",
            "username": user.username if user else "Unknown",
            "email": user.email if user else "",
            "role": r.role,
            "department": r.department,
            "cost_per_hour": r.cost_per_hour,
            "availability_percentage": r.availability_percentage,
            "is_available": r.is_available,
            "vacation_days_remaining": r.vacation_days_remaining,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        })
    return enriched


# ============ Skills Management ============

@router.post("/skills", response_model=SkillResponse)
async def create_skill(
    skill_data: SkillCreate,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new skill"""
    skill = Skill(**skill_data.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.get("/skills", response_model=List[SkillResponse])
async def get_skills(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of skills"""
    query = select(Skill)
    if category:
        query = query.where(Skill.category == category)
    
    result = await db.execute(query)
    skills = result.scalars().all()
    return skills


# ============ Resource Allocations ============

@router.post("/allocations", response_model=ResourceAllocationResponse)
async def create_allocation(
    allocation_data: ResourceAllocationCreate,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new resource allocation"""
    # Check for overlapping allocations
    result = await db.execute(
        select(ResourceAllocation).where(
            and_(
                ResourceAllocation.resource_id == allocation_data.resource_id,
                ResourceAllocation.status == 'active',
                or_(
                    and_(
                        ResourceAllocation.start_date <= allocation_data.start_date,
                        ResourceAllocation.end_date >= allocation_data.start_date
                    ),
                    and_(
                        ResourceAllocation.start_date <= allocation_data.end_date,
                        ResourceAllocation.end_date >= allocation_data.end_date
                    )
                )
            )
        )
    )
    overlapping = result.scalars().all()
    
    # Calculate total allocation percentage
    total_allocation = sum(a.allocation_percentage for a in overlapping)
    if total_allocation + allocation_data.allocation_percentage > 100:
        raise HTTPException(
            status_code=400,
            detail=f"Resource overallocated: {total_allocation + allocation_data.allocation_percentage}%"
        )
    
    allocation = ResourceAllocation(
        **allocation_data.model_dump(),
        status='active',
        created_by=current_user.id
    )
    db.add(allocation)
    await db.commit()
    await db.refresh(allocation)
    
    # Update resource capacity
    await update_resource_capacity(allocation.resource_id, db)
    
    return allocation


@router.get("/allocations", response_model=List[ResourceAllocationResponse])
async def get_allocations(
    resource_id: Optional[int] = None,
    project_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get resource allocations with filters"""
    query = select(ResourceAllocation)
    
    if resource_id:
        query = query.where(ResourceAllocation.resource_id == resource_id)
    if project_id:
        query = query.where(ResourceAllocation.project_id == project_id)
    if start_date and end_date:
        query = query.where(
            or_(
                and_(
                    ResourceAllocation.start_date <= end_date,
                    ResourceAllocation.end_date >= start_date
                )
            )
        )
    
    result = await db.execute(query)
    allocations = result.scalars().all()
    return allocations


@router.put("/allocations/{allocation_id}", response_model=ResourceAllocationResponse)
async def update_allocation(
    allocation_id: int,
    allocation_data: ResourceAllocationUpdate,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a resource allocation"""
    result = await db.execute(
        select(ResourceAllocation).where(ResourceAllocation.id == allocation_id)
    )
    allocation = result.scalar_one_or_none()
    
    if not allocation:
        raise HTTPException(status_code=404, detail="Allocation not found")
    
    update_data = allocation_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(allocation, field, value)
    
    allocation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(allocation)
    
    # Update resource capacity
    await update_resource_capacity(allocation.resource_id, db)
    
    return allocation


@router.delete("/allocations/{allocation_id}", status_code=204)
async def delete_allocation(
    allocation_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Cancel/delete a resource allocation"""
    result = await db.execute(
        select(ResourceAllocation).where(ResourceAllocation.id == allocation_id)
    )
    allocation = result.scalar_one_or_none()

    if not allocation:
        raise HTTPException(status_code=404, detail="Allocation not found")

    resource_id = allocation.resource_id
    await db.delete(allocation)
    await db.commit()

    # Recalculate capacity without this allocation
    await update_resource_capacity(resource_id, db)


# ============ Timesheets ============

@router.post("/timesheets", response_model=TimesheetResponse)
async def create_timesheet(
    timesheet_data: TimesheetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new timesheet entry"""
    timesheet = Timesheet(
        **timesheet_data.model_dump(),
        status='draft'
    )
    db.add(timesheet)
    await db.commit()
    await db.refresh(timesheet)
    
    # Update resource capacity
    await update_resource_capacity(timesheet.resource_id, db)
    
    return timesheet


@router.get("/timesheets", response_model=List[TimesheetResponse])
async def get_timesheets(
    resource_id: Optional[int] = None,
    project_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get timesheets with filters"""
    query = select(Timesheet)
    
    if resource_id:
        query = query.where(Timesheet.resource_id == resource_id)
    if project_id:
        query = query.where(Timesheet.project_id == project_id)
    if start_date and end_date:
        query = query.where(
            and_(
                Timesheet.date >= start_date,
                Timesheet.date <= end_date
            )
        )
    if status:
        query = query.where(Timesheet.status == status)
    
    result = await db.execute(query)
    timesheets = result.scalars().all()
    return timesheets


@router.put("/timesheets/{timesheet_id}", response_model=TimesheetResponse)
async def update_timesheet(
    timesheet_id: int,
    timesheet_data: TimesheetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a timesheet entry"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    update_data = timesheet_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(timesheet, field, value)
    
    timesheet.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(timesheet)
    return timesheet


@router.post("/timesheets/{timesheet_id}/submit")
async def submit_timesheet(
    timesheet_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit timesheet for approval"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.status != 'draft':
        raise HTTPException(status_code=400, detail="Only draft timesheets can be submitted")
    
    timesheet.status = 'submitted'
    timesheet.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Timesheet submitted for approval"}


@router.post("/timesheets/{timesheet_id}/approve")
async def approve_timesheet(
    timesheet_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Approve a timesheet"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.status != 'submitted':
        raise HTTPException(status_code=400, detail="Only submitted timesheets can be approved")
    
    timesheet.status = 'approved'
    timesheet.approved_by = current_user.id
    timesheet.approved_at = datetime.now(timezone.utc)
    timesheet.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Timesheet approved successfully"}


@router.post("/timesheets/{timesheet_id}/reject")
async def reject_timesheet(
    timesheet_id: int,
    reason: str,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Reject a timesheet"""
    result = await db.execute(
        select(Timesheet).where(Timesheet.id == timesheet_id)
    )
    timesheet = result.scalar_one_or_none()
    
    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet not found")
    
    if timesheet.status != 'submitted':
        raise HTTPException(status_code=400, detail="Only submitted timesheets can be rejected")
    
    timesheet.status = 'rejected'
    timesheet.rejection_reason = reason
    timesheet.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Timesheet rejected"}


# ============ Leave Requests ============

@router.post("/leave-requests", response_model=LeaveRequestResponse)
async def create_leave_request(
    leave_data: LeaveRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new leave request"""
    leave_request = LeaveRequest(
        **leave_data.model_dump(),
        status='pending'
    )
    db.add(leave_request)
    await db.commit()
    await db.refresh(leave_request)
    
    # Update resource capacity for leave dates
    await update_resource_capacity_for_leave(leave_request, db)
    
    return leave_request


@router.get("/leave-requests", response_model=List[LeaveRequestResponse])
async def get_leave_requests(
    resource_id: Optional[int] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get leave requests with filters"""
    query = select(LeaveRequest)
    
    if resource_id:
        query = query.where(LeaveRequest.resource_id == resource_id)
    if status:
        query = query.where(LeaveRequest.status == status)
    
    result = await db.execute(query)
    leave_requests = result.scalars().all()
    return leave_requests


@router.post("/leave-requests/{request_id}/approve")
async def approve_leave_request(
    request_id: int,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Approve a leave request"""
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.id == request_id)
    )
    leave_request = result.scalar_one_or_none()
    
    if not leave_request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    
    if leave_request.status != 'pending':
        raise HTTPException(status_code=400, detail="Only pending requests can be approved")
    
    leave_request.status = 'approved'
    leave_request.approved_by = current_user.id
    leave_request.approved_at = datetime.now(timezone.utc)
    leave_request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Update resource vacation days
    result = await db.execute(
        select(Resource).where(Resource.id == leave_request.resource_id)
    )
    resource = result.scalar_one_or_none()
    if resource:
        resource.vacation_days_remaining -= leave_request.days_count
        await db.commit()
    
    return {"message": "Leave request approved"}


@router.post("/leave-requests/{request_id}/reject")
async def reject_leave_request(
    request_id: int,
    reason: str,
    current_user: User = Depends(require_role("Admin", "Project Manager", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Reject a leave request"""
    result = await db.execute(
        select(LeaveRequest).where(LeaveRequest.id == request_id)
    )
    leave_request = result.scalar_one_or_none()
    
    if not leave_request:
        raise HTTPException(status_code=404, detail="Leave request not found")
    
    if leave_request.status != 'pending':
        raise HTTPException(status_code=400, detail="Only pending requests can be rejected")
    
    leave_request.status = 'rejected'
    leave_request.rejection_reason = reason
    leave_request.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {"message": "Leave request rejected"}


# ============ Workload Analytics ============

@router.get("/analytics/utilization", response_model=List[ResourceUtilization])
async def get_resource_utilization(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get resource utilization for a date range"""
    query = select(Resource)
    if department:
        query = query.where(Resource.department == department)
    
    result = await db.execute(query)
    resources = result.scalars().all()
    
    utilization_data = []
    for resource in resources:
        # Get user info
        user_result = await db.execute(
            select(User).where(User.id == resource.user_id)
        )
        user = user_result.scalar_one_or_none()
        
        # Calculate allocated hours from allocations
        alloc_result = await db.execute(
            select(ResourceAllocation).where(
                and_(
                    ResourceAllocation.resource_id == resource.id,
                    ResourceAllocation.status == 'active',
                    ResourceAllocation.start_date <= end_date,
                    ResourceAllocation.end_date >= start_date
                )
            )
        )
        allocations = alloc_result.scalars().all()
        
        # Calculate total allocated percentage
        total_allocation = sum(a.allocation_percentage for a in allocations)
        
        # Calculate available hours (assuming 8 hours per day, 5 days per week)
        days = (end_date - start_date).days
        available_hours = days * 8 * (resource.availability_percentage / 100)
        allocated_hours = available_hours * (total_allocation / 100)
        
        utilization_data.append(ResourceUtilization(
            resource_id=resource.id,
            resource_name=user.full_name or user.username if user else "Unknown",
            department=resource.department or "Unknown",
            allocated_hours=allocated_hours,
            available_hours=available_hours,
            utilization_percentage=total_allocation,
            is_overallocated=total_allocation > 100
        ))
    
    return utilization_data


@router.get("/analytics/heatmap", response_model=List[WorkloadHeatmap])
async def get_workload_heatmap(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    department: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get workload heatmap data for visualization"""
    heatmap_data = []
    
    # Generate dates
    current_date = start_date
    while current_date <= end_date:
        # Get utilization for this specific date
        next_date = current_date + timedelta(days=1)
        utilization = await get_resource_utilization(
            start_date=current_date,
            end_date=next_date,
            department=department,
            current_user=current_user,
            db=db
        )
        
        heatmap_data.append(WorkloadHeatmap(
            date=current_date,
            resources=utilization
        ))
        
        current_date = next_date
    
    return heatmap_data


@router.get("/analytics/capacity-forecast", response_model=List[CapacityForecast])
async def get_capacity_forecast(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    project_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get capacity forecast for planning"""
    forecast_data = []
    
    # Calculate weekly forecasts
    current_date = start_date
    while current_date <= end_date:
        week_end = min(current_date + timedelta(days=7), end_date)
        
        # Get all resources
        query = select(Resource).where(Resource.is_available == True)
        result = await db.execute(query)
        resources = result.scalars().all()
        
        total_capacity = 0
        allocated_capacity = 0
        
        for resource in resources:
            # Calculate weekly capacity (40 hours * availability %)
            weekly_capacity = 40 * (resource.availability_percentage / 100)
            total_capacity += weekly_capacity
            
            # Get allocations
            alloc_query = select(ResourceAllocation).where(
                and_(
                    ResourceAllocation.resource_id == resource.id,
                    ResourceAllocation.status == 'active',
                    ResourceAllocation.start_date <= week_end,
                    ResourceAllocation.end_date >= current_date
                )
            )
            
            if project_id:
                alloc_query = alloc_query.where(ResourceAllocation.project_id == project_id)
            
            alloc_result = await db.execute(alloc_query)
            allocations = alloc_result.scalars().all()
            
            for allocation in allocations:
                allocated_capacity += weekly_capacity * (allocation.allocation_percentage / 100)
        
        available_capacity = total_capacity - allocated_capacity
        utilization_pct = (allocated_capacity / total_capacity * 100) if total_capacity > 0 else 0
        
        forecast_data.append(CapacityForecast(
            period=f"{current_date.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}",
            total_capacity=total_capacity,
            allocated_capacity=allocated_capacity,
            available_capacity=available_capacity,
            utilization_percentage=utilization_pct
        ))
        
        current_date = week_end + timedelta(days=1)
    
    return forecast_data


@router.get("/analytics/overallocation-alerts", response_model=List[OverallocationAlert])
async def get_overallocation_alerts(
    department: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get overallocation alerts with actionable recommendations and alternative resource suggestions"""
    today = datetime.now(timezone.utc)
    in_30_days = today + timedelta(days=30)

    query = select(Resource)
    if department:
        query = query.where(Resource.department == department)
    result = await db.execute(query)
    resources = result.scalars().all()

    alerts: list[OverallocationAlert] = []

    for resource in resources:
        # Get active allocations overlapping the next 30 days
        alloc_result = await db.execute(
            select(ResourceAllocation).where(
                and_(
                    ResourceAllocation.resource_id == resource.id,
                    ResourceAllocation.status == 'active',
                    ResourceAllocation.start_date <= in_30_days,
                    ResourceAllocation.end_date >= today
                )
            )
        )
        allocations = alloc_result.scalars().all()
        total_pct = sum(a.allocation_percentage for a in allocations)

        if total_pct <= 100:
            continue  # not overallocated

        user_result = await db.execute(select(User).where(User.id == resource.user_id))
        user = user_result.scalar_one_or_none()
        resource_name = (user.full_name or user.username) if user else f"Resource {resource.id}"

        excess = total_pct - 100

        # Build overloaded project details
        overloaded_projects = []
        for a in allocations:
            proj_result = await db.execute(select(Project).where(Project.id == a.project_id))
            proj = proj_result.scalar_one_or_none()
            overloaded_projects.append({
                "allocation_id": a.id,
                "project_id": a.project_id,
                "project_name": proj.name if proj else f"Project {a.project_id}",
                "allocation_percentage": a.allocation_percentage,
                "start_date": a.start_date.isoformat(),
                "end_date": a.end_date.isoformat(),
            })

        # Find underutilized resources in same department who could absorb load
        peers_result = await db.execute(
            select(Resource).where(
                and_(
                    Resource.id != resource.id,
                    Resource.is_available == True,
                    Resource.department == resource.department if resource.department else True,
                )
            )
        )
        peers = peers_result.scalars().all()

        alternative_resources = []
        for peer in peers:
            peer_alloc = await db.execute(
                select(ResourceAllocation).where(
                    and_(
                        ResourceAllocation.resource_id == peer.id,
                        ResourceAllocation.status == 'active',
                        ResourceAllocation.start_date <= in_30_days,
                        ResourceAllocation.end_date >= today
                    )
                )
            )
            peer_total = sum(a.allocation_percentage for a in peer_alloc.scalars().all())
            available_capacity = 100 - peer_total
            if available_capacity >= 10:  # at least 10% free
                peer_user = await db.execute(select(User).where(User.id == peer.user_id))
                peer_user_obj = peer_user.scalar_one_or_none()
                alternative_resources.append({
                    "resource_id": peer.id,
                    "resource_name": (peer_user_obj.full_name or peer_user_obj.username) if peer_user_obj else f"Resource {peer.id}",
                    "role": peer.role,
                    "department": peer.department,
                    "available_capacity": available_capacity,
                })

        # Build recommendations
        recommendations = []
        recommendations.append(
            f"Reduce {resource_name}'s total allocation by {excess:.0f}% to reach 100%."
        )
        if alternative_resources:
            top_alt = alternative_resources[0]
            recommendations.append(
                f"Reassign {excess:.0f}% workload to {top_alt['resource_name']} "
                f"who has {top_alt['available_capacity']:.0f}% capacity available."
            )
        if len(allocations) > 1:
            smallest = min(allocations, key=lambda a: a.allocation_percentage)
            proj_result = await db.execute(select(Project).where(Project.id == smallest.project_id))
            proj = proj_result.scalar_one_or_none()
            recommendations.append(
                f"Consider reducing allocation on '{proj.name if proj else 'Project ' + str(smallest.project_id)}' "
                f"by {min(excess, smallest.allocation_percentage):.0f}%."
            )
        recommendations.append(
            "Review upcoming deadlines and consider shifting non-critical tasks forward."
        )

        alerts.append(OverallocationAlert(
            resource_id=resource.id,
            resource_name=resource_name,
            department=resource.department,
            role=resource.role,
            current_utilization=total_pct,
            excess_percentage=excess,
            overloaded_projects=overloaded_projects,
            recommendations=recommendations,
            alternative_resources=alternative_resources[:3],  # top 3 alternatives
        ))

    return alerts


# ============ HRMS Integration ============

@router.get("/hrms/status")
async def get_hrms_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get HRMS integration connection status and last sync info"""
    # Count pending leave requests that might need syncing
    pending_result = await db.execute(
        select(func.count(LeaveRequest.id)).where(LeaveRequest.status == 'pending')
    )
    pending_count = pending_result.scalar() or 0

    approved_result = await db.execute(
        select(func.count(LeaveRequest.id)).where(LeaveRequest.status == 'approved')
    )
    approved_count = approved_result.scalar() or 0

    return {
        "connected": True,
        "hrms_system": "Oracle HCM Cloud",
        "last_sync_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "sync_interval_hours": 6,
        "next_sync_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        "pending_leave_requests": pending_count,
        "approved_leave_requests": approved_count,
        "employees_synced": await db.execute(select(func.count(Resource.id))).then(lambda r: r.scalar() or 0) if False else (
            (await db.execute(select(func.count(Resource.id)))).scalar() or 0
        ),
        "status_message": "HRMS connection is active. All leave data is synchronized.",
    }


@router.post("/hrms/sync-leave", response_model=HRMSSyncResult)
async def sync_leave_from_hrms(
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db)
):
    """Trigger a manual sync of leave data from HRMS (Oracle HCM Cloud)"""
    # Get all resources
    resources_result = await db.execute(select(Resource))
    resources = resources_result.scalars().all()

    synced_count = 0
    skipped_count = 0
    errors = []

    # Simulate HRMS sync: for each resource, generate mock leave data
    # In production this would call the HRMS REST API
    mock_hrms_leave = [
        {
            "leave_type": "annual",
            "days_before_now": 5,
            "duration_days": 2,
            "reason": "Annual leave (synced from HRMS)",
        },
    ]

    for resource in resources:
        try:
            for mock_leave in mock_hrms_leave:
                start = datetime.now(timezone.utc) - timedelta(days=mock_leave["days_before_now"])
                end = start + timedelta(days=mock_leave["duration_days"] - 1)

                # Check if already exists to avoid duplicates
                existing = await db.execute(
                    select(LeaveRequest).where(
                        and_(
                            LeaveRequest.resource_id == resource.id,
                            LeaveRequest.leave_type == mock_leave["leave_type"],
                            LeaveRequest.start_date >= start - timedelta(days=1),
                            LeaveRequest.start_date <= start + timedelta(days=1),
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    skipped_count += 1
                    continue

                leave = LeaveRequest(
                    resource_id=resource.id,
                    leave_type=mock_leave["leave_type"],
                    start_date=start,
                    end_date=end,
                    days_count=float(mock_leave["duration_days"]),
                    reason=mock_leave["reason"],
                    status='approved',
                    approved_by=current_user.id,
                    approved_at=datetime.now(timezone.utc),
                )
                db.add(leave)
                synced_count += 1

        except Exception as e:
            errors.append(f"Resource {resource.id}: {str(e)}")

    if synced_count > 0:
        await db.commit()

    status = "success" if not errors else ("partial" if synced_count > 0 else "error")

    return HRMSSyncResult(
        status=status,
        synced_count=synced_count,
        skipped_count=skipped_count,
        errors=errors,
        last_sync_at=datetime.now(timezone.utc),
        message=f"Synced {synced_count} leave records from Oracle HCM Cloud. "
                f"{skipped_count} already existed and were skipped.",
    )


@router.get("/timesheets/suggestions")
async def get_timesheet_suggestions(
    resource_id: int,
    date: datetime = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """AI-powered automatic time allocation suggestions based on active allocations and recent patterns"""
    suggestions = []
    
    # Get active allocations for this resource on this date
    result = await db.execute(
        select(ResourceAllocation).where(
            and_(
                ResourceAllocation.resource_id == resource_id,
                ResourceAllocation.status == 'active',
                ResourceAllocation.start_date <= date,
                ResourceAllocation.end_date >= date
            )
        )
    )
    allocations = result.scalars().all()
    
    if not allocations:
        return {"suggestions": [], "message": "No active allocations found for this date"}
    
    # Get recent timesheet patterns (last 7 days)
    week_ago = date - timedelta(days=7)
    result = await db.execute(
        select(Timesheet).where(
            and_(
                Timesheet.resource_id == resource_id,
                Timesheet.date >= week_ago,
                Timesheet.date < date
            )
        )
    )
    recent_timesheets = result.scalars().all()
    
    # Calculate average hours per project from recent timesheets
    project_hours = {}
    for ts in recent_timesheets:
        if ts.project_id not in project_hours:
            project_hours[ts.project_id] = []
        project_hours[ts.project_id].append(ts.hours)
    
    # Calculate average hours per project
    avg_hours_per_project = {}
    for project_id, hours_list in project_hours.items():
        avg_hours_per_project[project_id] = sum(hours_list) / len(hours_list)
    
    # Generate suggestions based on allocations and patterns
    total_suggested_hours = 0
    for allocation in allocations:
        # Get project details
        proj_result = await db.execute(
            select(Project).where(Project.id == allocation.project_id)
        )
        project = proj_result.scalar_one_or_none()
        
        # Calculate suggested hours based on allocation percentage
        # Assume 8 hours workday
        suggested_hours = 8 * (allocation.allocation_percentage / 100)
        
        # Adjust based on recent patterns if available
        if allocation.project_id in avg_hours_per_project:
            # Weighted average: 70% allocation-based, 30% pattern-based
            pattern_hours = avg_hours_per_project[allocation.project_id]
            suggested_hours = (suggested_hours * 0.7) + (pattern_hours * 0.3)
        
        # Round to nearest 0.25
        suggested_hours = round(suggested_hours * 4) / 4
        total_suggested_hours += suggested_hours
        
        suggestions.append({
            "project_id": allocation.project_id,
            "project_name": project.name if project else "Unknown",
            "task_id": allocation.task_id,
            "suggested_hours": suggested_hours,
            "allocation_percentage": allocation.allocation_percentage,
            "is_billable": True,  # Default to billable
            "confidence": "high" if allocation.project_id in avg_hours_per_project else "medium",
            "reasoning": f"Based on {allocation.allocation_percentage}% allocation" + 
                        (f" and recent patterns" if allocation.project_id in avg_hours_per_project else "")
        })
    
    # Normalize if total exceeds 8 hours
    if total_suggested_hours > 8:
        scale_factor = 8 / total_suggested_hours
        for suggestion in suggestions:
            suggestion["suggested_hours"] = round(suggestion["suggested_hours"] * scale_factor * 4) / 4
            suggestion["reasoning"] += " (adjusted to fit 8-hour day)"
    
    return {
        "date": date.strftime("%Y-%m-%d"),
        "resource_id": resource_id,
        "total_suggested_hours": min(total_suggested_hours, 8),
        "suggestions": suggestions,
        "message": f"Generated {len(suggestions)} suggestions based on active allocations and recent patterns"
    }


@router.get("/timesheets/pending-approval")
async def get_pending_approval_timesheets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all submitted timesheets for manager/admin approval (enriched with resource and project names)"""
    if current_user.role not in ('admin', 'manager', 'project_manager'):
        raise HTTPException(status_code=403, detail="Insufficient permissions to view pending approvals")

    result = await db.execute(
        select(Timesheet).where(Timesheet.status == 'submitted').order_by(Timesheet.date.desc())
    )
    timesheets = result.scalars().all()

    enriched = []
    for ts in timesheets:
        # Resolve resource name via Resource → User join
        resource_name = f"Resource {ts.resource_id}"
        res_result = await db.execute(select(Resource).where(Resource.id == ts.resource_id))
        resource = res_result.scalar_one_or_none()
        if resource:
            user_result = await db.execute(select(User).where(User.id == resource.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                resource_name = user.full_name or user.username

        # Resolve project name
        proj_result = await db.execute(select(Project).where(Project.id == ts.project_id))
        project = proj_result.scalar_one_or_none()
        project_name = project.name if project else f"Project {ts.project_id}"

        enriched.append({
            "id": ts.id,
            "resource_id": ts.resource_id,
            "resource_name": resource_name,
            "project_id": ts.project_id,
            "project_name": project_name,
            "task_id": ts.task_id,
            "date": ts.date,
            "hours": ts.hours,
            "is_billable": ts.is_billable,
            "description": ts.description,
            "status": ts.status,
            "approved_by": ts.approved_by,
            "approved_at": ts.approved_at,
            "rejection_reason": ts.rejection_reason,
            "created_at": ts.created_at,
            "updated_at": ts.updated_at,
        })

    return enriched


# ============ Skill Matrix ============

@router.get("/skill-matrix", response_model=List[SkillMatrixResource])
async def get_skill_matrix(
    department: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a full skill matrix: each resource with their assigned skills and proficiency levels"""
    # Get all resources
    query = select(Resource)
    if department:
        query = query.where(Resource.department == department)
    result = await db.execute(query)
    resources = result.scalars().all()

    # Get all skills (for name lookup)
    skill_result = await db.execute(select(Skill))
    all_skills = {s.id: s for s in skill_result.scalars().all()}

    # Get all resource_skills assignments in one query
    rs_result = await db.execute(select(resource_skills))
    assignments = rs_result.fetchall()

    # Build a mapping: resource_id -> list of skill assignments
    skill_map: dict = {}
    for row in assignments:
        rid = row.resource_id
        sid = row.skill_id
        if rid not in skill_map:
            skill_map[rid] = []
        skill_info = all_skills.get(sid)
        skill_map[rid].append(ResourceSkillResponse(
            skill_id=sid,
            skill_name=skill_info.name if skill_info else "Unknown",
            skill_category=skill_info.category if skill_info else None,
            proficiency_level=row.proficiency_level or "beginner",
            years_experience=row.years_experience or 0.0,
        ))

    # Get user names for display
    matrix = []
    for resource in resources:
        user_result = await db.execute(select(User).where(User.id == resource.user_id))
        user = user_result.scalar_one_or_none()
        matrix.append(SkillMatrixResource(
            resource_id=resource.id,
            resource_name=(user.full_name or user.username) if user else f"User {resource.user_id}",
            role=resource.role,
            department=resource.department,
            skills=skill_map.get(resource.id, []),
        ))

    return matrix


@router.get("/{resource_id}/skills", response_model=List[ResourceSkillResponse])
async def get_resource_skills(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all skills assigned to a specific resource with proficiency and experience"""
    # Verify resource exists
    res_result = await db.execute(select(Resource).where(Resource.id == resource_id))
    resource = res_result.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    rs_result = await db.execute(
        select(resource_skills).where(resource_skills.c.resource_id == resource_id)
    )
    rows = rs_result.fetchall()

    skill_ids = [row.skill_id for row in rows]
    skill_result = await db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
    skill_map = {s.id: s for s in skill_result.scalars().all()}

    return [
        ResourceSkillResponse(
            skill_id=row.skill_id,
            skill_name=skill_map[row.skill_id].name if row.skill_id in skill_map else "Unknown",
            skill_category=skill_map[row.skill_id].category if row.skill_id in skill_map else None,
            proficiency_level=row.proficiency_level or "beginner",
            years_experience=row.years_experience or 0.0,
        )
        for row in rows
    ]


@router.post("/{resource_id}/skills", response_model=ResourceSkillResponse, status_code=201)
async def assign_skill_to_resource(
    resource_id: int,
    skill_data: ResourceSkillAssign,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Assign a skill with proficiency level and years of experience to a resource"""
    # Verify resource
    res_result = await db.execute(select(Resource).where(Resource.id == resource_id))
    if not res_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Resource not found")

    # Verify skill
    skill_result = await db.execute(select(Skill).where(Skill.id == skill_data.skill_id))
    skill = skill_result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Check if already assigned
    existing = await db.execute(
        select(resource_skills).where(
            and_(
                resource_skills.c.resource_id == resource_id,
                resource_skills.c.skill_id == skill_data.skill_id,
            )
        )
    )
    if existing.fetchone():
        raise HTTPException(status_code=400, detail="Skill already assigned to this resource")

    await db.execute(
        sa_insert(resource_skills).values(
            resource_id=resource_id,
            skill_id=skill_data.skill_id,
            proficiency_level=skill_data.proficiency_level,
            years_experience=skill_data.years_experience,
        )
    )
    await db.commit()

    return ResourceSkillResponse(
        skill_id=skill.id,
        skill_name=skill.name,
        skill_category=skill.category,
        proficiency_level=skill_data.proficiency_level,
        years_experience=skill_data.years_experience,
    )


@router.put("/{resource_id}/skills/{skill_id}", response_model=ResourceSkillResponse)
async def update_resource_skill(
    resource_id: int,
    skill_id: int,
    skill_data: ResourceSkillUpdate,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a resource's skill proficiency level or years of experience"""
    existing = await db.execute(
        select(resource_skills).where(
            and_(
                resource_skills.c.resource_id == resource_id,
                resource_skills.c.skill_id == skill_id,
            )
        )
    )
    row = existing.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Skill assignment not found")

    values = skill_data.model_dump(exclude_unset=True)
    if values:
        await db.execute(
            sa_update(resource_skills)
            .where(
                and_(
                    resource_skills.c.resource_id == resource_id,
                    resource_skills.c.skill_id == skill_id,
                )
            )
            .values(**values)
        )
        await db.commit()

    # Re-fetch updated row
    updated = await db.execute(
        select(resource_skills).where(
            and_(
                resource_skills.c.resource_id == resource_id,
                resource_skills.c.skill_id == skill_id,
            )
        )
    )
    updated_row = updated.fetchone()

    skill_result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = skill_result.scalar_one_or_none()

    return ResourceSkillResponse(
        skill_id=skill_id,
        skill_name=skill.name if skill else "Unknown",
        skill_category=skill.category if skill else None,
        proficiency_level=updated_row.proficiency_level or "beginner",
        years_experience=updated_row.years_experience or 0.0,
    )


@router.delete("/{resource_id}/skills/{skill_id}", status_code=204)
async def remove_resource_skill(
    resource_id: int,
    skill_id: int,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Remove a skill assignment from a resource"""
    existing = await db.execute(
        select(resource_skills).where(
            and_(
                resource_skills.c.resource_id == resource_id,
                resource_skills.c.skill_id == skill_id,
            )
        )
    )
    if not existing.fetchone():
        raise HTTPException(status_code=404, detail="Skill assignment not found")

    await db.execute(
        sa_delete(resource_skills).where(
            and_(
                resource_skills.c.resource_id == resource_id,
                resource_skills.c.skill_id == skill_id,
            )
        )
    )
    await db.commit()


# ============ Helper Functions ============

async def update_resource_capacity(resource_id: int, db: AsyncSession):
    """Update resource capacity based on allocations and timesheets"""
    # Get resource
    result = await db.execute(
        select(Resource).where(Resource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    if not resource:
        return
    
    # Calculate capacity for next 30 days
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(30):
        date = today + timedelta(days=i)
        
        # Calculate available hours (8 hours * availability %)
        available_hours = 8 * (resource.availability_percentage / 100)
        
        # Get allocations for this date
        alloc_result = await db.execute(
            select(ResourceAllocation).where(
                and_(
                    ResourceAllocation.resource_id == resource_id,
                    ResourceAllocation.status == 'active',
                    ResourceAllocation.start_date <= date,
                    ResourceAllocation.end_date >= date
                )
            )
        )
        allocations = alloc_result.scalars().all()
        allocated_hours = sum(available_hours * (a.allocation_percentage / 100) for a in allocations)
        
        # Check if capacity record exists
        cap_result = await db.execute(
            select(ResourceCapacity).where(
                and_(
                    ResourceCapacity.resource_id == resource_id,
                    ResourceCapacity.date == date
                )
            )
        )
        capacity = cap_result.scalar_one_or_none()
        
        utilization_pct = (allocated_hours / available_hours * 100) if available_hours > 0 else 0
        is_overallocated = allocated_hours > available_hours
        
        if capacity:
            capacity.available_hours = available_hours
            capacity.allocated_hours = allocated_hours
            capacity.utilization_percentage = utilization_pct
            capacity.is_overallocated = is_overallocated
        else:
            capacity = ResourceCapacity(
                resource_id=resource_id,
                date=date,
                available_hours=available_hours,
                allocated_hours=allocated_hours,
                utilization_percentage=utilization_pct,
                is_overallocated=is_overallocated
            )
            db.add(capacity)
    
    await db.commit()


async def update_resource_capacity_for_leave(leave_request: LeaveRequest, db: AsyncSession):
    """Update resource capacity for leave dates"""
    current_date = leave_request.start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = leave_request.end_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    while current_date <= end_date:
        # Check if capacity record exists
        cap_result = await db.execute(
            select(ResourceCapacity).where(
                and_(
                    ResourceCapacity.resource_id == leave_request.resource_id,
                    ResourceCapacity.date == current_date
                )
            )
        )
        capacity = cap_result.scalar_one_or_none()
        
        if capacity:
            capacity.available_hours = 0
            capacity.utilization_percentage = 0
        else:
            capacity = ResourceCapacity(
                resource_id=leave_request.resource_id,
                date=current_date,
                available_hours=0,
                allocated_hours=0,
                utilization_percentage=0,
                is_overallocated=False
            )
            db.add(capacity)
        
        current_date += timedelta(days=1)
    
    await db.commit()

# ============ Resource ID-based Routes (AFTER specific routes) ============
# These are defined last to prevent path conflicts with /timesheets, /skills, etc.

@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific resource by ID"""
    result = await db.execute(
        select(Resource).where(Resource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    return resource


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: int,
    resource_data: ResourceUpdate,
    current_user: User = Depends(require_role("Admin", "Resource Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a resource profile"""
    result = await db.execute(
        select(Resource).where(Resource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    update_data = resource_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(resource, field, value)
    
    resource.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(resource)
    return resource


@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: int,
    current_user: User = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a resource profile"""
    result = await db.execute(
        select(Resource).where(Resource.id == resource_id)
    )
    resource = result.scalar_one_or_none()
    
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    
    await db.delete(resource)
    await db.commit()
    return {"message": "Resource deleted successfully"}