"""Seed test data for Document Management feature."""
import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import (
    Document, DocumentVersion, DocumentApproval,
    RetentionPolicy, DocumentRetentionLog, Base
)
from datetime import datetime, timezone

engine = create_engine('sqlite:///./pms_dev.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
db = Session()

now = datetime.now(timezone.utc)

docs_data = [
    {
        'project_id': 1, 'name': 'Project Charter - Alpha',
        'description': 'Project charter defining scope, goals and stakeholders for Alpha project',
        'document_type': 'charter', 'status': 'approved',
        'tags': ['charter', 'phase-1', 'critical'],
        'is_public': True, 'requires_approval': True,
        'owner_id': 1, 'created_by': 1, 'retention_days': 365
    },
    {
        'project_id': 1, 'name': 'Requirements Specification v2',
        'description': 'Software requirements specification for Alpha modules',
        'document_type': 'specification', 'status': 'under_review',
        'tags': ['requirements', 'SRS', 'phase-1'],
        'is_public': False, 'requires_approval': True,
        'owner_id': 1, 'created_by': 1, 'retention_days': 730
    },
    {
        'project_id': 1, 'name': 'Weekly Status Report - Week 12',
        'description': 'Status report covering sprint progress, blockers and next steps',
        'document_type': 'report', 'status': 'draft',
        'tags': ['status', 'weekly', 'sprint-6'],
        'is_public': True, 'requires_approval': False,
        'owner_id': 2, 'created_by': 2
    },
    {
        'project_id': 2, 'name': 'Architecture Design Document',
        'description': 'High-level and detailed system architecture with diagrams',
        'document_type': 'design', 'status': 'approved',
        'tags': ['architecture', 'design', 'technical'],
        'is_public': False, 'requires_approval': True,
        'owner_id': 1, 'created_by': 1, 'retention_days': 1095
    },
    {
        'project_id': 2, 'name': 'Test Plan - Integration Phase',
        'description': 'Test plan covering integration test cases and acceptance criteria',
        'document_type': 'test_plan', 'status': 'draft',
        'tags': ['testing', 'integration', 'QA'],
        'is_public': False, 'requires_approval': True,
        'owner_id': 3, 'created_by': 3
    },
    {
        'project_id': 3, 'name': 'Vendor Contract - CloudOps',
        'description': 'Service level agreement with CloudOps hosting provider',
        'document_type': 'contract', 'status': 'approved',
        'tags': ['contract', 'vendor', 'SLA'],
        'is_public': False, 'requires_approval': True,
        'owner_id': 1, 'created_by': 1, 'retention_days': 1825
    },
    {
        'project_id': 3, 'name': 'Meeting Minutes - Sprint Review',
        'description': 'Minutes from sprint review meeting with stakeholders',
        'document_type': 'minutes', 'status': 'approved',
        'tags': ['meeting', 'sprint', 'review'],
        'is_public': True, 'requires_approval': False,
        'owner_id': 2, 'created_by': 2
    },
    {
        'project_id': 1, 'name': 'Change Request CR-042',
        'description': 'Change request for adding OAuth2 authentication module',
        'document_type': 'change_request', 'status': 'under_review',
        'tags': ['CR', 'auth', 'security'],
        'is_public': False, 'requires_approval': True,
        'owner_id': 1, 'created_by': 4
    },
    {
        'project_id': 2, 'name': 'Risk Register Q1 2026',
        'description': 'Comprehensive project risk register for Q1 2026',
        'document_type': 'general', 'status': 'approved',
        'tags': ['risk', 'register', 'Q1'],
        'is_public': True, 'requires_approval': False,
        'owner_id': 1, 'created_by': 1
    },
    {
        'project_id': 5, 'name': 'Lessons Learned - Phase 1',
        'description': 'Lessons learned from phase 1 delivery',
        'document_type': 'general', 'status': 'draft',
        'tags': ['lessons', 'retrospective', 'phase-1'],
        'is_public': True, 'requires_approval': False,
        'owner_id': 2, 'created_by': 2
    },
]

for i, dd in enumerate(docs_data):
    safe_name = dd['name'].replace(' ', '_').lower()[:30]
    doc = Document(
        project_id=dd['project_id'],
        name=dd['name'],
        description=dd['description'],
        document_type=dd['document_type'],
        status=dd['status'],
        tags=dd['tags'],
        is_public=dd['is_public'],
        requires_approval=dd['requires_approval'],
        owner_id=dd['owner_id'],
        created_by=dd['created_by'],
        current_version=1,
        current_file_path=f"documents/{dd['project_id']}/{safe_name}",
        current_file_size=(i + 1) * 15000,
        retention_days=dd.get('retention_days'),
    )
    db.add(doc)
db.flush()

all_docs = db.query(Document).all()
print(f"Created {len(all_docs)} documents")

# Seed versions
ver_count = 0
for doc in all_docs:
    v1 = DocumentVersion(
        document_id=doc.id, version_number=1, version_type='major',
        file_path=f"documents/{doc.project_id}/v1/{doc.name[:20].replace(' ','_')}",
        file_size=doc.current_file_size or 10000,
        change_summary='Initial version',
        changed_by=doc.created_by,
    )
    db.add(v1)
    ver_count += 1

    if doc.status in ('approved', 'under_review'):
        v2 = DocumentVersion(
            document_id=doc.id, version_number=2, version_type='minor',
            file_path=f"documents/{doc.project_id}/v2/{doc.name[:20].replace(' ','_')}",
            file_size=(doc.current_file_size or 10000) + 5000,
            change_summary='Updated based on review feedback',
            changed_by=doc.owner_id,
        )
        db.add(v2)
        ver_count += 1
        doc.current_version = 2

        if doc.status == 'approved':
            v3 = DocumentVersion(
                document_id=doc.id, version_number=3, version_type='major',
                file_path=f"documents/{doc.project_id}/v3/{doc.name[:20].replace(' ','_')}",
                file_size=(doc.current_file_size or 10000) + 12000,
                change_summary='Final approved version',
                changed_by=doc.owner_id,
            )
            db.add(v3)
            ver_count += 1
            doc.current_version = 3
db.flush()
print(f"Created {ver_count} document versions")

# Seed approvals
appr_count = 0
for doc in all_docs:
    if doc.requires_approval:
        a = DocumentApproval(
            document_id=doc.id,
            version_id=None,
            approver_id=1,
            status='approved' if doc.status == 'approved' else 'pending',
            comments='Approved - meets standards' if doc.status == 'approved' else 'Pending review',
            approved_at=now if doc.status == 'approved' else None,
        )
        db.add(a)
        appr_count += 1
db.flush()
print(f"Created {appr_count} approvals")

# Retention policies
policies_data = [
    {
        'name': 'Standard Document Retention',
        'description': 'Default policy for general documents',
        'document_type': 'general', 'retention_days': 365,
        'auto_archive': True, 'auto_delete': False, 'priority': 0
    },
    {
        'name': 'Contract Long-term Retention',
        'description': 'Extended retention for legal contracts',
        'document_type': 'contract', 'retention_days': 2555,
        'auto_archive': True, 'auto_delete': False,
        'legal_hold': True, 'priority': 10
    },
    {
        'name': 'Report Quarterly Cleanup',
        'description': 'Archive status reports after 90 days',
        'document_type': 'report', 'retention_days': 90,
        'auto_archive': True, 'auto_delete': True,
        'delete_after_days': 180, 'priority': 5
    },
]
for pd in policies_data:
    rp = RetentionPolicy(
        name=pd['name'], description=pd['description'],
        document_type=pd.get('document_type'),
        retention_days=pd['retention_days'],
        auto_archive=pd.get('auto_archive', True),
        auto_delete=pd.get('auto_delete', False),
        delete_after_days=pd.get('delete_after_days'),
        legal_hold=pd.get('legal_hold', False),
        priority=pd.get('priority', 0),
        created_by=1,
    )
    db.add(rp)
print(f"Created {len(policies_data)} retention policies")

db.commit()
db.close()
print("Document test data seeded successfully!")
