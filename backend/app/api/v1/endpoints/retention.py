from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.models.models import RetentionPolicy, Document
from app.api.v1.endpoints.auth import get_current_user
from app.services.retention_service import RetentionPolicyService

router = APIRouter()


class RetentionPolicyCreate(BaseModel):
    name: str
    description: str = None
    document_type: str = None
    project_status: str = None
    retention_days: int
    auto_archive: bool = True
    auto_delete: bool = False
    delete_after_days: int = None
    priority: int = 0
    legal_hold: bool = False


@router.post("/retention-policies")
async def create_retention_policy(
    policy_data: RetentionPolicyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new document retention policy."""
    policy = RetentionPolicy(
        **policy_data.dict(),
        created_by=current_user.id,
        is_active=True
    )
    
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "retention_days": policy.retention_days,
        "auto_archive": policy.auto_archive,
        "auto_delete": policy.auto_delete,
        "is_active": policy.is_active,
        "created_at": policy.created_at
    }


@router.get("/retention-policies")
async def get_retention_policies(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all retention policies."""
    result = await db.execute(
        select(RetentionPolicy).order_by(RetentionPolicy.priority.desc())
    )
    policies = result.scalars().all()
    
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "document_type": p.document_type,
            "project_status": p.project_status,
            "retention_days": p.retention_days,
            "auto_archive": p.auto_archive,
            "auto_delete": p.auto_delete,
            "delete_after_days": p.delete_after_days,
            "is_active": p.is_active,
            "priority": p.priority,
            "legal_hold": p.legal_hold,
            "created_at": p.created_at
        }
        for p in policies
    ]


@router.put("/retention-policies/{policy_id}")
async def update_retention_policy(
    policy_id: int,
    policy_data: RetentionPolicyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a retention policy."""
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    
    for key, value in policy_data.dict().items():
        setattr(policy, key, value)
    
    await db.commit()
    await db.refresh(policy)
    
    return {
        "id": policy.id,
        "name": policy.name,
        "message": "Retention policy updated successfully"
    }


@router.delete("/retention-policies/{policy_id}")
async def delete_retention_policy(
    policy_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a retention policy."""
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.id == policy_id)
    )
    policy = result.scalar_one_or_none()
    
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    
    await db.delete(policy)
    await db.commit()
    
    return {"message": "Retention policy deleted successfully"}


@router.post("/retention-policies/apply")
async def apply_retention_policies(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger retention policy enforcement.
    This runs all active policies and archives/deletes documents as needed.
    """
    result = await RetentionPolicyService.apply_retention_policies(db)
    return result


@router.get("/documents/pending-archival")
async def get_pending_archival(
    days_threshold: int = 30,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get documents that will be archived soon."""
    docs = await RetentionPolicyService.get_documents_pending_archival(db, days_threshold)
    return {
        "pending_documents": docs,
        "count": len(docs),
        "days_threshold": days_threshold
    }


@router.post("/documents/{document_id}/restore")
async def restore_document(
    document_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Restore an archived document."""
    success = await RetentionPolicyService.restore_document(
        db, document_id, current_user.id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document restored successfully"}


@router.get("/documents/archived")
async def get_archived_documents(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all archived documents."""
    result = await db.execute(
        select(Document)
        .where(Document.archived_at.isnot(None))
        .order_by(Document.archived_at.desc())
    )
    docs = result.scalars().all()
    
    return [
        {
            "id": doc.id,
            "name": doc.name,
            "document_type": doc.document_type,
            "project_id": doc.project_id,
            "created_at": doc.created_at.isoformat(),
            "archived_at": doc.archived_at.isoformat(),
            "retention_days": doc.retention_days
        }
        for doc in docs
    ]


@router.get("/retention-logs")
async def get_retention_logs(
    document_id: int = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get retention policy action logs."""
    logs = await RetentionPolicyService.get_retention_log(db, document_id, limit)
    return {
        "logs": logs,
        "count": len(logs)
    }
