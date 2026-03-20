from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import Project, Task
from app.api.v1.endpoints.auth import get_current_user
from app.services.ivalua_service import get_ivalua_service

router = APIRouter()


class PurchaseRequisitionItem(BaseModel):
    description: str
    quantity: int
    unit_price: float
    category_code: str
    delivery_date: str
    gl_account: str


class CreatePRRequest(BaseModel):
    project_id: int
    task_id: int = None
    items: List[PurchaseRequisitionItem]
    justification: str


@router.post("/purchase-requisitions")
async def create_purchase_requisition(
    request: CreatePRRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a purchase requisition in Ivalua for a project/task.
    """
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify task exists if provided
    if request.task_id:
        result = await db.execute(
            select(Task).where(Task.id == request.task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    
    # Convert items to dict
    items = [item.dict() for item in request.items]
    
    # Create PR in Ivalua
    ivalua_service = get_ivalua_service()
    result = await ivalua_service.create_purchase_requisition(
        project_id=request.project_id,
        task_id=request.task_id,
        items=items,
        requester_email=current_user.email,
        justification=request.justification
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Failed to create purchase requisition")
        )
    
    return result


@router.get("/purchase-orders/{po_number}")
async def get_purchase_order(
    po_number: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details and status of a purchase order."""
    ivalua_service = get_ivalua_service()
    result = await ivalua_service.get_purchase_order_status(po_number)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=404,
            detail=result.get("message", f"Purchase order {po_number} not found")
        )
    
    return result


@router.get("/projects/{project_id}/purchase-orders")
async def get_project_purchase_orders(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all purchase orders linked to a project."""
    # Verify project exists
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get POs from Ivalua
    ivalua_service = get_ivalua_service()
    pos = await ivalua_service.get_project_purchase_orders(project_id)
    
    return {
        "project_id": project_id,
        "project_name": project.name,
        "purchase_orders": pos,
        "total_count": len(pos)
    }


@router.get("/vendors/{vendor_code}/performance")
async def get_vendor_performance(
    vendor_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Get vendor performance metrics."""
    ivalua_service = get_ivalua_service()
    result = await ivalua_service.get_vendor_performance(vendor_code)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=404,
            detail=f"Vendor {vendor_code} not found or no performance data available"
        )
    
    return result


@router.post("/purchase-orders/{po_number}/link")
async def link_po_to_task(
    po_number: str,
    project_id: int,
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Link an existing purchase order to a project task."""
    # Verify task exists
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.project_id == project_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Link in Ivalua
    ivalua_service = get_ivalua_service()
    result = await ivalua_service.link_po_to_task(po_number, project_id, task_id)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to link PO {po_number} to task"
        )
    
    return result
