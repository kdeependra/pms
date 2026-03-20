from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime
import hashlib
import os

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import Document, DocumentVersion, DocumentApproval, Project
from app.schemas.schemas import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentVersionCreate, DocumentVersionResponse,
    DocumentApprovalCreate, DocumentApprovalResponse
)

router = APIRouter()


# Documents
@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    document: DocumentCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new document"""
    # Verify project exists
    project_query = select(Project).where(Project.id == document.project_id)
    result = await db.execute(project_query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    db_document = Document(
        **document.dict(),
        owner_id=current_user.id,
        created_by=current_user.id
    )
    
    db.add(db_document)
    await db.commit()
    await db.refresh(db_document)
    return db_document


@router.get("/", response_model=List[DocumentResponse])
async def get_documents(
    project_id: int = Query(None),
    document_type: str = Query(None),
    status: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get documents with filters"""
    query = select(Document)
    
    if project_id:
        query = query.where(Document.project_id == project_id)
    if document_type:
        query = query.where(Document.document_type == document_type)
    if status:
        query = query.where(Document.status == status)
    
    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()
    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document"""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    document_update: DocumentUpdate,
    current_user: dict = Depends(require_role("Admin", "Project Manager", "Team Member")),
    db: AsyncSession = Depends(get_db)
):
    """Update a document"""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    db_document = result.scalar_one_or_none()
    
    if not db_document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions (owner or admin)
    if db_document.owner_id != current_user.id and "Admin" not in {r.name for r in current_user.assigned_roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this document"
        )
    
    # Update fields
    update_data = document_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_document, key, value)
    
    await db.commit()
    await db.refresh(db_document)
    return db_document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document"""
    query = select(Document).where(Document.id == document_id)
    result = await db.execute(query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Check permissions
    if document.owner_id != current_user.id and "Admin" not in {r.name for r in current_user.assigned_roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this document"
        )
    
    await db.delete(document)
    await db.commit()


# Document Versions
@router.post("/{document_id}/versions", response_model=DocumentVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_document_version(
    document_id: int,
    version: DocumentVersionCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new version of a document"""
    # Verify document exists
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Calculate file hash
    file_hash = hashlib.sha256(version.file_path.encode()).hexdigest()[:16]
    
    db_version = DocumentVersion(
        document_id=document_id,
        **version.dict(),
        file_hash=file_hash,
        changed_by=current_user.id
    )
    
    db.add(db_version)
    
    # Update document current version
    document.current_version = version.version_number
    document.current_file_path = version.file_path
    document.current_file_size = version.file_size
    
    await db.commit()
    await db.refresh(db_version)
    return db_version


@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
async def get_document_versions(
    document_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all versions of a document"""
    query = select(DocumentVersion).where(
        DocumentVersion.document_id == document_id
    ).order_by(DocumentVersion.version_number.desc())
    
    result = await db.execute(query)
    versions = result.scalars().all()
    return versions


@router.post("/{document_id}/versions/{version_id}/checkout", response_model=DocumentVersionResponse)
async def checkout_document_version(
    document_id: int,
    version_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check out a document version for editing"""
    query = select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found"
        )
    
    if version.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is already checked out by user {version.checked_out_by}"
        )
    
    version.is_checked_out = True
    version.checked_out_by = current_user.id
    version.checked_out_at = datetime.now()
    
    await db.commit()
    await db.refresh(version)
    return version


@router.post("/{document_id}/versions/{version_id}/checkin", response_model=DocumentVersionResponse)
async def checkin_document_version(
    document_id: int,
    version_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check in a document version after editing"""
    query = select(DocumentVersion).where(
        DocumentVersion.id == version_id,
        DocumentVersion.document_id == document_id
    )
    result = await db.execute(query)
    version = result.scalar_one_or_none()
    
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document version not found"
        )
    
    if not version.is_checked_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document is not checked out"
        )
    
    if version.checked_out_by != current_user.id and "Admin" not in {r.name for r in current_user.assigned_roles}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the user who checked out the document can check it in"
        )
    
    version.is_checked_out = False
    version.checked_out_by = None
    version.checked_out_at = None
    
    await db.commit()
    await db.refresh(version)
    return version


# Document Approvals
@router.post("/{document_id}/approvals", response_model=DocumentApprovalResponse, status_code=status.HTTP_201_CREATED)
async def request_document_approval(
    document_id: int,
    approver_id: int,
    version_id: int,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Request approval for a document version"""
    # Verify document exists
    doc_query = select(Document).where(Document.id == document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    db_approval = DocumentApproval(
        document_id=document_id,
        version_id=version_id,
        approver_id=approver_id,
        status="pending"
    )
    
    db.add(db_approval)
    
    # Update document status
    if document.status == "draft":
        document.status = "under_review"
    
    await db.commit()
    await db.refresh(db_approval)
    return db_approval


@router.put("/approvals/{approval_id}", response_model=DocumentApprovalResponse)
async def respond_to_approval(
    approval_id: int,
    approval_response: DocumentApprovalCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Approve or reject a document"""
    query = select(DocumentApproval).where(DocumentApproval.id == approval_id)
    result = await db.execute(query)
    approval = result.scalar_one_or_none()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found"
        )
    
    # Check if current user is the approver
    if approval.approver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the designated approver can respond to this request"
        )
    
    approval.status = approval_response.status
    approval.comments = approval_response.comments
    approval.approved_at = datetime.now()
    
    # Update document status
    doc_query = select(Document).where(Document.id == approval.document_id)
    result = await db.execute(doc_query)
    document = result.scalar_one_or_none()
    
    if document and approval_response.status == "approved":
        document.status = "approved"
    elif document and approval_response.status == "rejected":
        document.status = "draft"
    
    await db.commit()
    await db.refresh(approval)
    return approval


@router.get("/{document_id}/approvals", response_model=List[DocumentApprovalResponse])
async def get_document_approvals(
    document_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all approval requests for a document"""
    query = select(DocumentApproval).where(
        DocumentApproval.document_id == document_id
    ).order_by(DocumentApproval.created_at.desc())
    
    result = await db.execute(query)
    approvals = result.scalars().all()
    return approvals
