"""
Document Retention Policy Service.
Handles automated archival and deletion of documents based on retention policies.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime, timedelta
from typing import List, Dict
import logging

from app.models.models import Document, RetentionPolicy, DocumentRetentionLog, Project

logger = logging.getLogger(__name__)


class RetentionPolicyService:
    """Service for managing document retention policies."""
    
    @staticmethod
    async def apply_retention_policies(db: AsyncSession) -> Dict:
        """
        Apply all active retention policies to documents.
        This should be run periodically (e.g., daily via scheduled job).
        
        Returns:
            Dict with summary of actions taken
        """
        # Get all active retention policies ordered by priority (higher first)
        result = await db.execute(
            select(RetentionPolicy)
            .where(RetentionPolicy.is_active == True)
            .order_by(RetentionPolicy.priority.desc())
        )
        policies = result.scalars().all()
        
        archived_count = 0
        deleted_count = 0
        
        for policy in policies:
            # Apply policy
            archived, deleted = await RetentionPolicyService._apply_policy(db, policy)
            archived_count += archived
            deleted_count += deleted
        
        await db.commit()
        
        logger.info(f"Retention policies applied: {archived_count} archived, {deleted_count} deleted")
        
        return {
            "policies_applied": len(policies),
            "documents_archived": archived_count,
            "documents_deleted": deleted_count,
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    async def _apply_policy(db: AsyncSession, policy: RetentionPolicy) -> tuple:
        """Apply a single retention policy."""
        archived_count = 0
        deleted_count = 0
        
        # Build query for documents matching policy criteria
        query = select(Document).where(Document.archived_at.is_(None))
        
        # Filter by document type if specified
        if policy.document_type:
            query = query.where(Document.document_type == policy.document_type)
        
        # Filter by project status if specified
        if policy.project_status:
            query = query.join(Project).where(Project.status == policy.project_status)
        
        result = await db.execute(query)
        documents = result.scalars().all()
        
        for doc in documents:
            # Skip documents under legal hold
            # Check if document has a legal hold policy
            legal_hold_result = await db.execute(
                select(RetentionPolicy)
                .where(
                    and_(
                        RetentionPolicy.is_active == True,
                        RetentionPolicy.legal_hold == True,
                        or_(
                            RetentionPolicy.document_type == doc.document_type,
                            RetentionPolicy.document_type.is_(None)
                        )
                    )
                )
            )
            if legal_hold_result.scalar_one_or_none():
                continue
            
            # Check if document age exceeds retention period
            doc_age_days = (datetime.now() - doc.created_at.replace(tzinfo=None)).days
            
            if doc_age_days >= policy.retention_days:
                if policy.auto_archive and not doc.archived_at:
                    # Archive document
                    doc.archived_at = datetime.now()
                    
                    # Log action
                    log = DocumentRetentionLog(
                        document_id=doc.id,
                        policy_id=policy.id,
                        action="archived",
                        reason=f"Auto-archived by policy: {policy.name}",
                        performed_by=None  # System action
                    )
                    db.add(log)
                    archived_count += 1
                    
                    logger.info(f"Archived document {doc.id} ({doc.name}) per policy {policy.name}")
            
            # Check for deletion after archival
            if policy.auto_delete and policy.delete_after_days and doc.archived_at:
                archive_age_days = (datetime.now() - doc.archived_at.replace(tzinfo=None)).days
                
                if archive_age_days >= policy.delete_after_days:
                    # Log before deletion
                    log = DocumentRetentionLog(
                        document_id=doc.id,
                        policy_id=policy.id,
                        action="deleted",
                        reason=f"Auto-deleted by policy: {policy.name}",
                        performed_by=None  # System action
                    )
                    db.add(log)
                    await db.flush()  # Ensure log is saved before deletion
                    
                    # Delete document
                    await db.delete(doc)
                    deleted_count += 1
                    
                    logger.warning(f"Deleted document {doc.id} ({doc.name}) per policy {policy.name}")
        
        return archived_count, deleted_count
    
    @staticmethod
    async def restore_document(db: AsyncSession, document_id: int, user_id: int) -> bool:
        """
        Restore an archived document.
        
        Args:
            db: Database session
            document_id: ID of document to restore
            user_id: ID of user performing the restore
            
        Returns:
            True if successful, False otherwise
        """
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        
        if not doc:
            return False
        
        if not doc.archived_at:
            # Already active
            return True
        
        # Restore document
        doc.archived_at = None
        
        # Log action
        log = DocumentRetentionLog(
            document_id=doc.id,
            policy_id=None,
            action="restored",
            reason="Manually restored by user",
            performed_by=user_id
        )
        db.add(log)
        
        await db.commit()
        
        logger.info(f"Restored document {doc.id} by user {user_id}")
        
        return True
    
    @staticmethod
    async def get_documents_pending_archival(
        db: AsyncSession,
        days_threshold: int = 30
    ) -> List[Dict]:
        """
        Get documents that will be archived soon.
        
        Args:
            db: Database session
            days_threshold: Days until archival to include
            
        Returns:
            List of documents pending archival
        """
        # Get all active retention policies
        result = await db.execute(
            select(RetentionPolicy)
            .where(RetentionPolicy.is_active == True)
            .order_by(RetentionPolicy.priority.desc())
        )
        policies = result.scalars().all()
        
        pending_docs = []
        
        for policy in policies:
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=policy.retention_days - days_threshold)
            
            # Find documents approaching retention age
            query = select(Document).where(
                and_(
                    Document.archived_at.is_(None),
                    Document.created_at <= cutoff_date
                )
            )
            
            if policy.document_type:
                query = query.where(Document.document_type == policy.document_type)
            
            result = await db.execute(query)
            docs = result.scalars().all()
            
            for doc in docs:
                doc_age_days = (datetime.now() - doc.created_at.replace(tzinfo=None)).days
                days_until_archive = policy.retention_days - doc_age_days
                
                if days_until_archive <= days_threshold and days_until_archive >= 0:
                    pending_docs.append({
                        "document_id": doc.id,
                        "document_name": doc.name,
                        "document_type": doc.document_type,
                        "created_at": doc.created_at.isoformat(),
                        "policy_name": policy.name,
                        "days_until_archive": days_until_archive
                    })
        
        return pending_docs
    
    @staticmethod
    async def get_retention_log(
        db: AsyncSession,
        document_id: int = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get retention policy action log.
        
        Args:
            db: Database session
            document_id: Optional document ID to filter by
            limit: Maximum number of records to return
            
        Returns:
            List of log entries
        """
        query = select(DocumentRetentionLog).order_by(DocumentRetentionLog.performed_at.desc())
        
        if document_id:
            query = query.where(DocumentRetentionLog.document_id == document_id)
        
        query = query.limit(limit)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        return [
            {
                "id": log.id,
                "document_id": log.document_id,
                "policy_id": log.policy_id,
                "action": log.action,
                "reason": log.reason,
                "performed_by": log.performed_by,
                "performed_at": log.performed_at.isoformat()
            }
            for log in logs
        ]
