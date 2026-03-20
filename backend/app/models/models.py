from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Text, Float, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum

# Association table for task dependencies
task_dependencies = Table(
    'task_dependencies',
    Base.metadata,
    Column('predecessor_id', Integer, ForeignKey('tasks.id'), primary_key=True),
    Column('successor_id', Integer, ForeignKey('tasks.id'), primary_key=True),
    Column('dependency_type', String, default='finish_to_start')  # finish_to_start, start_to_start, finish_to_finish, start_to_finish
)

# Association tables for RBAC (defined early so they can be used by models)
role_permission_association = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)

user_role_association = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    TEAM_MEMBER = "team_member"
    STAKEHOLDER = "stakeholder"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String)
    hashed_password = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.TEAM_MEMBER)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    department = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    projects = relationship("Project", back_populates="owner")
    tasks = relationship("Task", back_populates="assignee")
    comments = relationship("Comment", back_populates="author")
    assigned_roles = relationship(
        'Role',
        secondary=user_role_association,
        back_populates='users'
    )

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="planning")  # planning, active, on_hold, completed, cancelled
    priority = Column(String, default="medium")  # low, medium, high, critical
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    budget = Column(Integer)
    actual_cost = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="project", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"))
    assignee_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="todo")  # todo, in_progress, review, done
    priority = Column(String, default="medium")
    due_date = Column(DateTime(timezone=True))
    estimated_hours = Column(Float)
    actual_hours = Column(Float, default=0)
    progress = Column(Integer, default=0)
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    
    # Recurring task fields
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String)  # daily, weekly, monthly, yearly
    recurrence_interval = Column(Integer, default=1)
    recurrence_end_date = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[id], backref="subtasks")
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    documents = relationship("TaskDocument", back_populates="task", cascade="all, delete-orphan")
    time_logs = relationship("TimeLog", back_populates="task", cascade="all, delete-orphan")
    
    # Task dependencies
    predecessors = relationship(
        "Task",
        secondary=task_dependencies,
        primaryjoin=id==task_dependencies.c.successor_id,
        secondaryjoin=id==task_dependencies.c.predecessor_id,
        backref="successors"
    )

class Risk(Base):
    __tablename__ = "risks"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String, nullable=False)
    description = Column(Text)
    probability = Column(Integer)  # 1-5
    impact = Column(Integer)  # 1-5
    risk_score = Column(Integer)  # probability * impact
    mitigation_plan = Column(Text)
    status = Column(String, default="identified")  # identified, mitigated, occurred, closed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="risks")

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    task = relationship("Task", back_populates="comments")
    author = relationship("User", back_populates="comments")

class TaskDocument(Base):
    __tablename__ = "task_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    file_type = Column(String)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    task = relationship("Task", back_populates="documents")
    uploader = relationship("User")

class TimeLog(Base):
    __tablename__ = "time_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    hours = Column(Float, nullable=False)
    date = Column(DateTime(timezone=True), default=func.now())
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    task = relationship("Task", back_populates="time_logs")
    user = relationship("User")

class TaskDependency(Base):
    __tablename__ = "task_dependencies_detail"
    
    id = Column(Integer, primary_key=True, index=True)
    predecessor_id = Column(Integer, ForeignKey("tasks.id"))
    successor_id = Column(Integer, ForeignKey("tasks.id"))
    dependency_type = Column(String, default="finish_to_start")
    lag_days = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Milestone(Base):
    __tablename__ = "milestones"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    target_date = Column(DateTime(timezone=True), nullable=False)
    actual_date = Column(DateTime(timezone=True))
    status = Column(String, default="pending")  # pending, achieved, missed, at_risk
    is_critical = Column(Boolean, default=False)  # Part of critical path
    progress = Column(Integer, default=0)  # 0-100
    order = Column(Integer, default=0)  # Display order in timeline
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="milestones")


# Workflow Models
class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.DRAFT)
    is_template = Column(Boolean, default=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="workflows")
    creator = relationship("User")
    stages = relationship("WorkflowStage", back_populates="workflow", cascade="all, delete-orphan")
    transitions = relationship("WorkflowTransition", back_populates="workflow", cascade="all, delete-orphan")
    instances = relationship("WorkflowInstance", back_populates="workflow")


class WorkflowStage(Base):
    __tablename__ = "workflow_stages"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    stage_type = Column(String, default="task")  # task, approval, condition, start, end
    requires_approval = Column(Boolean, default=False)
    approver_role = Column(String)  # Role required for approval
    approver_user_id = Column(Integer, ForeignKey("users.id"))
    auto_assign = Column(Boolean, default=False)
    assignment_rule = Column(JSON)  # Rules for automatic task assignment
    position_x = Column(Float, default=0)  # X position in workflow designer
    position_y = Column(Float, default=0)  # Y position in workflow designer
    order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workflow = relationship("Workflow", back_populates="stages")
    approver = relationship("User")
    outgoing_transitions = relationship("WorkflowTransition", foreign_keys="[WorkflowTransition.from_stage_id]", back_populates="from_stage")
    incoming_transitions = relationship("WorkflowTransition", foreign_keys="[WorkflowTransition.to_stage_id]", back_populates="to_stage")


class WorkflowTransition(Base):
    __tablename__ = "workflow_transitions"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    from_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    to_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    name = Column(String)  # Transition label
    condition_type = Column(String, default="always")  # always, approved, rejected, conditional
    condition_logic = Column(JSON)  # JSON condition rules
    order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workflow = relationship("Workflow", back_populates="transitions")
    from_stage = relationship("WorkflowStage", foreign_keys=[from_stage_id], back_populates="outgoing_transitions")
    to_stage = relationship("WorkflowStage", foreign_keys=[to_stage_id], back_populates="incoming_transitions")


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))
    current_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    status = Column(String, default="in_progress")  # in_progress, completed, cancelled, failed
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    started_by = Column(Integer, ForeignKey("users.id"))
    instance_metadata = Column(JSON)  # Additional instance data
    
    # Relationships
    workflow = relationship("Workflow", back_populates="instances")
    task = relationship("Task", backref="workflow_instances")
    current_stage = relationship("WorkflowStage")
    starter = relationship("User")
    approvals = relationship("WorkflowApproval", back_populates="instance", cascade="all, delete-orphan")
    history = relationship("WorkflowHistory", back_populates="instance", cascade="all, delete-orphan")


class WorkflowApproval(Base):
    __tablename__ = "workflow_approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("workflow_instances.id"))
    stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    approver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # pending, approved, rejected
    comments = Column(Text)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    responded_at = Column(DateTime(timezone=True))
    
    # Relationships
    instance = relationship("WorkflowInstance", back_populates="approvals")
    stage = relationship("WorkflowStage")
    approver = relationship("User")


class WorkflowHistory(Base):
    __tablename__ = "workflow_history"
    
    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("workflow_instances.id"))
    from_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    to_stage_id = Column(Integer, ForeignKey("workflow_stages.id"))
    transition_id = Column(Integer, ForeignKey("workflow_transitions.id"))
    action = Column(String)  # transitioned, approved, rejected, assigned
    performed_by = Column(Integer, ForeignKey("users.id"))
    comments = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    instance = relationship("WorkflowInstance", back_populates="history")
    from_stage = relationship("WorkflowStage", foreign_keys=[from_stage_id])
    to_stage = relationship("WorkflowStage", foreign_keys=[to_stage_id])
    transition = relationship("WorkflowTransition")
    performer = relationship("User")


# Resource Management Models

# Resource Skill Association Table
resource_skills = Table(
    'resource_skills',
    Base.metadata,
    Column('resource_id', Integer, ForeignKey('resources.id'), primary_key=True),
    Column('skill_id', Integer, ForeignKey('skills.id'), primary_key=True),
    Column('proficiency_level', String, default='intermediate'),  # beginner, intermediate, advanced, expert
    Column('years_experience', Float, default=0)
)


class Skill(Base):
    __tablename__ = "skills"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    category = Column(String)  # technical, soft_skill, domain, certification
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    resources = relationship("Resource", secondary=resource_skills, back_populates="skills")


class Resource(Base):
    __tablename__ = "resources"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    role = Column(String)  # Developer, Designer, PM, QA, etc.
    department = Column(String)
    cost_per_hour = Column(Float, default=0)
    availability_percentage = Column(Float, default=100)  # 0-100
    is_available = Column(Boolean, default=True)
    vacation_days_remaining = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User")
    skills = relationship("Skill", secondary=resource_skills, back_populates="resources")
    allocations = relationship("ResourceAllocation", back_populates="resource")
    timesheets = relationship("Timesheet", back_populates="resource")
    leave_requests = relationship("LeaveRequest", back_populates="resource")


class ResourceAllocation(Base):
    __tablename__ = "resource_allocations"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    allocation_percentage = Column(Float, default=100)  # % of time allocated
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="planned")  # planned, active, completed, cancelled
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    resource = relationship("Resource", back_populates="allocations")
    project = relationship("Project")
    task = relationship("Task")
    creator = relationship("User", foreign_keys=[created_by])


class Timesheet(Base):
    __tablename__ = "timesheets"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    date = Column(DateTime(timezone=True), nullable=False)
    hours = Column(Float, nullable=False)
    is_billable = Column(Boolean, default=True)
    description = Column(Text)
    status = Column(String, default="draft")  # draft, submitted, approved, rejected
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    resource = relationship("Resource", back_populates="timesheets")
    project = relationship("Project")
    task = relationship("Task")
    approver = relationship("User", foreign_keys=[approved_by])


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"))
    leave_type = Column(String, nullable=False)  # annual, sick, unpaid, public_holiday
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    days_count = Column(Float, nullable=False)
    reason = Column(Text)
    status = Column(String, default="pending")  # pending, approved, rejected, cancelled
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    resource = relationship("Resource", back_populates="leave_requests")
    approver = relationship("User", foreign_keys=[approved_by])


class ResourceCapacity(Base):
    __tablename__ = "resource_capacity"
    
    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"))
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    available_hours = Column(Float, default=8)  # Default working hours per day
    allocated_hours = Column(Float, default=0)
    utilization_percentage = Column(Float, default=0)  # allocated/available * 100
    is_overallocated = Column(Boolean, default=False)
    notes = Column(Text)
    
    # Relationships
    resource = relationship("Resource")


# Budget and Financial Management Models
class BudgetCategory(Base):
    __tablename__ = "budget_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True)  # For FMIS integration
    description = Column(Text)
    category_type = Column(String, default="labor")  # labor, materials, services, other
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    budget_items = relationship("BudgetItem", back_populates="category")


class BudgetItem(Base):
    __tablename__ = "budget_items"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    category_id = Column(Integer, ForeignKey("budget_categories.id"))
    description = Column(String, nullable=False)
    planned_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, default=0)
    committed_amount = Column(Float, default=0)  # Purchase orders
    variance = Column(Float, default=0)  # actual - planned
    variance_percentage = Column(Float, default=0)
    gl_code = Column(String)  # General Ledger code for FMIS
    cost_center = Column(String)
    purchase_order_number = Column(String)  # Link to Ivalua
    is_billable = Column(Boolean, default=False)
    fiscal_year = Column(String)
    quarter = Column(String)
    status = Column(String, default="planned")  # planned, approved, spent, closed
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="budget_items")
    category = relationship("BudgetCategory", back_populates="budget_items")
    transactions = relationship("BudgetTransaction", back_populates="budget_item", cascade="all, delete-orphan")


class BudgetTransaction(Base):
    __tablename__ = "budget_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    budget_item_id = Column(Integer, ForeignKey("budget_items.id"))
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    transaction_type = Column(String, nullable=False)  # expense, commitment, adjustment, refund
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    reference_number = Column(String)  # Invoice number, PO number, etc.
    vendor_name = Column(String)
    payment_status = Column(String, default="pending")  # pending, paid, cancelled
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    budget_item = relationship("BudgetItem", back_populates="transactions")
    approver = relationship("User", foreign_keys=[approved_by])
    creator = relationship("User", foreign_keys=[created_by])


class CashFlowProjection(Base):
    __tablename__ = "cash_flow_projections"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    period = Column(DateTime(timezone=True), nullable=False)  # Month or week
    projected_inflow = Column(Float, default=0)
    projected_outflow = Column(Float, default=0)
    net_cash_flow = Column(Float, default=0)
    cumulative_cash_flow = Column(Float, default=0)
    confidence_level = Column(Float)  # 0-100 AI confidence in projection
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="cash_flow_projections")


# Issue Management Models
class IssueCategory(str, enum.Enum):
    TECHNICAL = "technical"
    RESOURCE = "resource"
    BUDGET = "budget"
    SCOPE = "scope"
    QUALITY = "quality"
    STAKEHOLDER = "stakeholder"
    OTHER = "other"


class IssueSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class Issue(Base):
    __tablename__ = "issues"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SQLEnum(IssueCategory), default=IssueCategory.OTHER)
    severity = Column(SQLEnum(IssueSeverity), default=IssueSeverity.MEDIUM)
    status = Column(SQLEnum(IssueStatus), default=IssueStatus.OPEN)
    priority = Column(Integer, default=3)  # 1-5
    
    # People
    reported_by = Column(Integer, ForeignKey("users.id"))
    assigned_to = Column(Integer, ForeignKey("users.id"))
    
    # Root cause analysis
    root_cause = Column(Text)
    resolution = Column(Text)
    resolution_date = Column(DateTime(timezone=True))
    
    # SLA tracking
    sla_due_date = Column(DateTime(timezone=True))
    sla_status = Column(String, default="on_track")  # on_track, at_risk, breached
    
    # BMC Remedy integration
    remedy_ticket_id = Column(String)  # Link to BMC Remedy incident
    
    # Aging
    days_open = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="issues")
    task = relationship("Task", backref="issues")
    reporter = relationship("User", foreign_keys=[reported_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
    comments = relationship("IssueComment", back_populates="issue", cascade="all, delete-orphan")
    attachments = relationship("IssueAttachment", back_populates="issue", cascade="all, delete-orphan")


class IssueComment(Base):
    __tablename__ = "issue_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    issue_id = Column(Integer, ForeignKey("issues.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)  # Internal vs stakeholder visible
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    issue = relationship("Issue", back_populates="comments")
    author = relationship("User")


class IssueAttachment(Base):
    __tablename__ = "issue_attachments"
    
    id = Column(Integer, primary_key=True, index=True)
    issue_id = Column(Integer, ForeignKey("issues.id"))
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    file_type = Column(String)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    issue = relationship("Issue", back_populates="attachments")
    uploader = relationship("User")


# Document Management with Version Control
class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    document_type = Column(String)  # charter, report, specification, contract, etc.
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.DRAFT)
    
    # Current version info (denormalized for quick access)
    current_version = Column(Integer, default=1)
    current_file_path = Column(String)
    current_file_size = Column(Integer)
    
    # Metadata
    tags = Column(JSON)  # List of tags for categorization
    document_metadata = Column(JSON)  # Additional custom metadata (renamed from metadata to avoid SQLAlchemy conflict)
    
    # Permissions
    is_public = Column(Boolean, default=False)
    requires_approval = Column(Boolean, default=False)
    
    # SharePoint integration
    sharepoint_url = Column(String)
    sharepoint_id = Column(String)
    
    # Ownership
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    
    # Retention policy
    retention_days = Column(Integer)  # Days before archival
    archived_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="documents")
    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by])
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    approvals = relationship("DocumentApproval", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    version_number = Column(Integer, nullable=False)
    version_type = Column(String, default="minor")  # major, minor, patch
    file_path = Column(String, nullable=False)
    file_size = Column(Integer)
    file_hash = Column(String)  # For integrity checking
    
    # Change tracking
    change_summary = Column(Text)
    changed_by = Column(Integer, ForeignKey("users.id"))
    
    # Check-in/Check-out
    is_checked_out = Column(Boolean, default=False)
    checked_out_by = Column(Integer, ForeignKey("users.id"))
    checked_out_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="versions")
    author = relationship("User", foreign_keys=[changed_by])
    checkout_user = relationship("User", foreign_keys=[checked_out_by])


class DocumentApproval(Base):
    __tablename__ = "document_approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    version_id = Column(Integer, ForeignKey("document_versions.id"))
    approver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # pending, approved, rejected
    comments = Column(Text)
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="approvals")
    version = relationship("DocumentVersion")
    approver = relationship("User")


# Kanban Board Configuration
class KanbanBoard(Base):
    __tablename__ = "kanban_boards"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    is_default = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="kanban_boards")
    creator = relationship("User")
    columns = relationship("KanbanColumn", back_populates="board", cascade="all, delete-orphan", order_by="KanbanColumn.order")


class KanbanColumn(Base):
    __tablename__ = "kanban_columns"
    
    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("kanban_boards.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    color = Column(String)  # Hex color code
    order = Column(Integer, default=0)
    wip_limit = Column(Integer)  # Work in Progress limit
    task_status_mapping = Column(String)  # Maps to Task.status (todo, in_progress, etc.)
    is_done_column = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    board = relationship("KanbanBoard", back_populates="columns")


# Gantt Chart View Configuration
class GanttView(Base):
    __tablename__ = "gantt_views"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    view_type = Column(String, default="timeline")  # timeline, resource, baseline
    zoom_level = Column(String, default="day")  # hour, day, week, month, quarter
    show_critical_path = Column(Boolean, default=True)
    show_milestones = Column(Boolean, default=True)
    show_dependencies = Column(Boolean, default=True)
    show_progress = Column(Boolean, default=True)
    color_by = Column(String, default="status")  # status, priority, assignee, phase
    baseline_date = Column(DateTime(timezone=True))  # For baseline comparison
    filters = Column(JSON)  # Saved filter configuration
    created_by = Column(Integer, ForeignKey("users.id"))
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="gantt_views")
    creator = relationship("User")


class ProjectBaseline(Base):
    __tablename__ = "project_baselines"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    baseline_date = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", backref="baselines")
    creator = relationship("User")
    task_baselines = relationship("TaskBaseline", back_populates="baseline", cascade="all, delete-orphan")
    milestone_baselines = relationship("MilestoneBaseline", back_populates="baseline", cascade="all, delete-orphan")


class TaskBaseline(Base):
    __tablename__ = "task_baselines"
    
    id = Column(Integer, primary_key=True, index=True)
    baseline_id = Column(Integer, ForeignKey("project_baselines.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    baseline_start_date = Column(DateTime(timezone=True))
    baseline_end_date = Column(DateTime(timezone=True))
    baseline_duration = Column(Integer)  # in days
    baseline_estimated_hours = Column(Float)
    baseline_status = Column(String)
    baseline_progress = Column(Integer, default=0)
    
    # Relationships
    baseline = relationship("ProjectBaseline", back_populates="task_baselines")
    task = relationship("Task", backref="baselines")


class MilestoneBaseline(Base):
    __tablename__ = "milestone_baselines"
    
    id = Column(Integer, primary_key=True, index=True)
    baseline_id = Column(Integer, ForeignKey("project_baselines.id"), nullable=False)
    milestone_id = Column(Integer, ForeignKey("milestones.id"), nullable=False)
    baseline_due_date = Column(DateTime(timezone=True))
    baseline_status = Column(String)
    
    # Relationships
    baseline = relationship("ProjectBaseline", back_populates="milestone_baselines")
    milestone = relationship("Milestone", backref="baselines")


# ==================== Sentiment Analysis & Stakeholder Feedback Models ====================

class Survey(Base):
    __tablename__ = "surveys"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    survey_type = Column(String, default="general")  # general, satisfaction, engagement, stakeholder, post_mortem
    status = Column(String, default="draft")  # draft, active, closed
    target_audience = Column(String)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="surveys")
    creator = relationship("User")
    questions = relationship("SurveyQuestion", back_populates="survey", cascade="all, delete-orphan")
    responses = relationship("SurveyResponseData", back_populates="survey", cascade="all, delete-orphan")


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    question = Column(String, nullable=False)
    question_type = Column(String)  # text, rating, multiple_choice, nps
    category = Column(String)
    options = Column(JSON)  # For multiple choice
    order = Column(Integer, default=0)
    is_required = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    survey = relationship("Survey", back_populates="questions")
    project = relationship("Project", backref="survey_questions")


class SurveyResponseData(Base):
    __tablename__ = "survey_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("surveys.id"), nullable=False)
    respondent_id = Column(Integer, ForeignKey("users.id"))
    respondent_email = Column(String)
    respondent_name = Column(String)
    respondent_role = Column(String)
    sentiment_score = Column(Float, default=0.0)  # -1.0 to 1.0
    sentiment_category = Column(String, default="neutral")
    feedback_text = Column(Text)
    action_items = Column(JSON)  # List of action items extracted from feedback
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    survey = relationship("Survey", back_populates="responses")
    respondent = relationship("User")


class StakeholderFeedback(Base):
    __tablename__ = "stakeholder_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    feedback_type = Column(String)  # general, requirement, issue, compliment, suggestion
    content = Column(Text, nullable=False)
    stakeholder_id = Column(Integer, ForeignKey("users.id"))
    stakeholder_email = Column(String)
    stakeholder_name = Column(String)
    stakeholder_role = Column(String)
    is_anonymous = Column(Boolean, default=False)
    status = Column(String, default="open")  # open, in_progress, resolved, closed
    sentiment = Column(String, default="neutral")
    sentiment_score = Column(Float, default=0.0)  # -1.0 to 1.0
    key_topics = Column(JSON)  # Extracted topics from feedback text
    action_items = Column(JSON)  # Generated action items
    assigned_to = Column(Integer, ForeignKey("users.id"))
    resolution = Column(Text)
    attachments = Column(JSON)  # List of attachment paths/urls
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="stakeholder_feedback")
    stakeholder = relationship("User", foreign_keys=[stakeholder_id], backref="submitted_feedback")
    assigned_user = relationship("User", foreign_keys=[assigned_to], backref="assigned_feedback")


class StakeholderSatisfaction(Base):
    __tablename__ = "stakeholder_satisfaction"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stakeholder_id = Column(Integer, ForeignKey("users.id"))
    stakeholder_email = Column(String)
    satisfaction_score = Column(Float)  # 0-5
    confidence_level = Column(Float)  # 0-1
    key_areas = Column(JSON)  # {area: score}
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", backref="stakeholder_satisfaction")
    stakeholder = relationship("User", backref="satisfaction_records")


class FeedbackActionItem(Base):
    __tablename__ = "feedback_action_items"
    
    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("stakeholder_feedback.id"))
    survey_response_id = Column(Integer, ForeignKey("survey_responses.id"))
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    priority = Column(String, default="medium")  # low, medium, high, critical
    assigned_to = Column(Integer, ForeignKey("users.id"))
    due_date = Column(DateTime(timezone=True))
    status = Column(String, default="open")  # open, in_progress, completed, cancelled
    completion_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    feedback = relationship("StakeholderFeedback", backref="generated_action_items")
    survey_response = relationship("SurveyResponseData", backref="generated_action_items")
    project = relationship("Project", backref="feedback_action_items")
    assigned_user = relationship("User", backref="assigned_action_items")


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    document_type = Column(String)  # Apply to specific document types
    project_status = Column(String)  # Apply when project reaches certain status
    retention_days = Column(Integer, nullable=False)  # Days before archival
    auto_archive = Column(Boolean, default=True)
    auto_delete = Column(Boolean, default=False)
    delete_after_days = Column(Integer)  # Days after archival before deletion
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher priority policies override lower
    
    # Legal hold
    legal_hold = Column(Boolean, default=False)  # Prevent archival/deletion
    
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    creator = relationship("User")


class DocumentRetentionLog(Base):
    __tablename__ = "document_retention_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    policy_id = Column(Integer, ForeignKey("retention_policies.id"))
    action = Column(String, nullable=False)  # archived, restored, deleted, policy_applied
    reason = Column(Text)
    performed_by = Column(Integer, ForeignKey("users.id"))
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document")
    policy = relationship("RetentionPolicy")
    user = relationship("User")


# RBAC Models
class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text)
    is_system_role = Column(Boolean, default=False)  # System roles can't be deleted
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship(
        'User',
        secondary=user_role_association,
        back_populates='assigned_roles'
    )
    permissions = relationship(
        'Permission',
        secondary=role_permission_association,
        back_populates='roles'
    )
    creator = relationship("User", foreign_keys=[created_by])


class Permission(Base):
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    resource = Column(String, nullable=False)  # projects, tasks, users, etc.
    action = Column(String, nullable=False)  # create, read, update, delete, approve, etc.
    description = Column(Text)
    category = Column(String, default="general")  # general, admin, resource, approval
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    roles = relationship(
        'Role',
        secondary=role_permission_association,
        back_populates='permissions'
    )


# Communication Analysis Models
class CommunicationMessage(Base):
    """Represents email, chat, or communication messages for analysis"""
    __tablename__ = "communication_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_ids = Column(JSON)  # {"users": [id1, id2], "teams": [team_id1]}
    message_type = Column(String, nullable=False)  # email, chat, comment, thread
    channel = Column(String)  # channel name for chat (e.g., "general", "project-x")
    subject = Column(String)  # for emails
    content = Column(Text, nullable=False)
    
    # Sentiment Analysis Fields
    sentiment_score = Column(Float)  # -1.0 to 1.0
    sentiment_category = Column(String)  # very_positive, positive, neutral, negative, very_negative
    confidence = Column(Float)  # 0.0 to 1.0
    
    # Communication Analysis Fields
    tone = Column(String)  # professional, informal, urgent, supportive, critical
    mentions = Column(JSON)  # {users: [id1, id2], topics: ["performance", "timeline"]}
    key_topics = Column(JSON)  # [{topic: "performance", score: 0.92}]
    action_items = Column(JSON)  # Extracted action items from message
    
    # Conflict Detection
    contains_conflict = Column(Boolean, default=False)
    conflict_score = Column(Float, default=0.0)  # 0.0 to 1.0
    conflict_type = Column(String)  # disagreement, escalation, complaint, concern
    
    reply_count = Column(Integer, default=0)
    response_time_minutes = Column(Integer)  # Time taken to respond
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="communication_messages")
    sender = relationship("User", foreign_keys=[sender_id], backref="sent_messages")


class CollaborationMetrics(Base):
    """Tracks team collaboration patterns and health"""
    __tablename__ = "collaboration_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    team_member_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Time period (daily/weekly/monthly)
    period_date = Column(DateTime(timezone=True), nullable=False)
    period_type = Column(String, default="daily")  # daily, weekly, monthly
    
    # Participation Metrics
    messages_sent = Column(Integer, default=0)
    messages_received = Column(Integer, default=0)
    avg_message_length = Column(Float, default=0.0)  # words
    
    # Response Metrics
    avg_response_time = Column(Float, default=0.0)  # minutes
    messages_with_response = Column(Integer, default=0)
    response_rate = Column(Float, default=0.0)  # percentage
    
    # Engagement Metrics
    topics_discussed = Column(JSON)  # ["topic1", "topic2"]
    mentions_received = Column(Integer, default=0)  # times mentioned
    replied_to_count = Column(Integer, default=0)  # times responded to
    collaboration_score = Column(Float, default=0.0)  # 0.0 to 1.0
    
    # Sentiment Metrics
    avg_sentiment = Column(Float, default=0.0)  # -1.0 to 1.0
    positive_messages = Column(Integer, default=0)
    negative_messages = Column(Integer, default=0)
    neutral_messages = Column(Integer, default=0)
    
    # Conflict Involvement
    involved_in_conflicts = Column(Integer, default=0)
    conflict_resolution_rate = Column(Float, default=0.0)  # percentage resolved
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="collaboration_metrics")
    team_member = relationship("User", backref="collaboration_metrics")


class ConflictAlert(Base):
    """Tracks potential conflicts and escalations in communication"""
    __tablename__ = "conflict_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    
    # Conflict Details
    severity = Column(String, default="low")  # low, medium, high, critical
    type = Column(String)  # disagreement, escalation, complaint, concern, tension
    involved_users = Column(JSON)  # [user_id1, user_id2, ...]
    
    # Source Information
    message_id = Column(Integer, ForeignKey("communication_messages.id"))
    thread_context = Column(JSON)  # Recent messages in thread for context
    
    # Resolution Tracking
    status = Column(String, default="open")  # open, acknowledged, in_progress, resolved, false_alarm
    assigned_to = Column(Integer, ForeignKey("users.id"))  # Manager or mediator
    resolution_notes = Column(Text)
    
    # Metrics
    confidence_score = Column(Float, default=0.0)  # How confident is this a real conflict
    negative_sentiment_count = Column(Integer, default=0)
    escalation_count = Column(Integer, default=0)  # Number of escalations in thread
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="conflict_alerts")
    message = relationship("CommunicationMessage", backref="conflict_alerts")
    assigned_user = relationship("User", foreign_keys=[assigned_to], backref="assigned_conflicts")


# Automated Alerts & Status Updates Models
class AlertTemplate(Base):
    """Predefined alert templates for consistent alerts"""
    __tablename__ = "alert_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # e.g., "task_overdue", "budget_exceeded"
    category = Column(String, nullable=False)  # task_delay, conflict_predicted, budget_alert, scope_creep, team_risk
    description = Column(Text)
    
    # Alert Configuration
    default_priority = Column(String, default="medium")  # low, medium, high, critical
    prediction_type = Column(String)  # predictive, threshold, anomaly, sentiment_based
    enabled_by_default = Column(Boolean, default=True)
    
    # Message Templates
    email_subject = Column(String, nullable=False)
    email_body = Column(Text, nullable=False)  # HTML template with {placeholders}
    in_app_title = Column(String, nullable=False)
    in_app_message = Column(String, nullable=False)  # Shorter version for in-app
    
    # Delivery Configuration
    allowed_channels = Column(JSON, default='["email", "inapp"]')  # email, sms, inapp, teams
    batching_enabled = Column(Boolean, default=True)
    min_batch_size = Column(Integer, default=1)
    max_wait_time = Column(Integer, default=300)  # seconds
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Alert(Base):
    """Individual alert instances"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("alert_templates.id"), nullable=False)
    
    # Alert Context
    alert_type = Column(String, nullable=False)  # task_delay, conflict_predicted, etc.
    entity_type = Column(String)  # task, project, user, team
    entity_id = Column(Integer)  # ID of the linked entity
    
    # Alert Data
    title = Column(String, nullable=False)
    description = Column(Text)
    context_data = Column(JSON)  # Additional context {"task_id": 5, "deadline": "2026-03-20"}
    
    # Priority & Status
    priority = Column(String, default="medium")  # low, medium, high, critical
    urgency_score = Column(Float, default=0.5)  # 0.0 to 1.0, calculated from context
    severity = Column(String, default="medium")  # user-perceived severity
    
    # Recipient
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Prediction (if predictive)
    is_predictive = Column(Boolean, default=False)
    prediction_confidence = Column(Float)  # 0.0 to 1.0
    predicted_issue = Column(String)  # What issue is predicted
    
    # Delivery
    should_batch = Column(Boolean, default=True)  # Can be batched with others
    batch_id = Column(Integer)  # Group ID if batched with others
    delivery_status = Column(String, default="pending")  # pending, scheduled, sent, opened, archived
    delivery_channels = Column(JSON, default='["email", "inapp"]')
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_at = Column(DateTime(timezone=True))  # When to send (for batched)
    sent_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    archived_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))  # Auto-archive after this time
    
    # Relationships
    project = relationship("Project", backref="alerts")
    template = relationship("AlertTemplate", backref="alerts")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="alerts_received")


class AlertPreference(Base):
    """User alert preferences and notification settings"""
    __tablename__ = "alert_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))  # NULL = global preferences
    
    # Channel Preferences
    email_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=False)
    inapp_enabled = Column(Boolean, default=True)
    teams_enabled = Column(Boolean, default=False)
    push_enabled = Column(Boolean, default=True)
    
    # Contact Information
    phone_number = Column(String)  # For SMS
    teams_webhook_url = Column(String)  # For Teams integration
    
    # Alert Type Preferences
    enabled_alert_types = Column(JSON, default='["task_delay", "conflict_predicted", "budget_alert"]')
    disabled_alert_types = Column(JSON, default='[]')
    priority_filter = Column(String, default="medium")  # Only receive: medium, high, critical +
    
    # Batching Preferences
    batching_enabled = Column(Boolean, default=True)
    batch_interval = Column(Integer, default=300)  # seconds, preferred batching interval
    
    # Time-based Preferences
    quiet_hours_enabled = Column(Boolean, default=True)
    quiet_hours_start = Column(String, default="22:00")  # Format: HH:MM
    quiet_hours_end = Column(String, default="08:00")
    
    # Other Preferences
    max_daily_alerts = Column(Integer, default=50)
    frequency_preference = Column(String, default="immediate")  # immediate, daily, weekly
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============ PHASE 4: AUTOMATED STATUS UPDATES MODELS ============

class StatusUpdateTemplate(Base):
    """Templates for auto-generating status updates"""
    __tablename__ = "status_update_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # NULL = global template
    
    # Schedule
    frequency = Column(String, default="weekly")  # daily, weekly, biweekly, monthly
    day_of_week = Column(String)  # For weekly: monday, tuesday, etc.
    time_of_day = Column(String, default="09:00")  # Format: HH:MM
    
    # Content Configuration
    include_progress = Column(Boolean, default=True)
    include_risks = Column(Boolean, default=True)
    include_budget = Column(Boolean, default=True)
    include_timeline = Column(Boolean, default=True)
    include_blockers = Column(Boolean, default=True)
    include_recommendations = Column(Boolean, default=True)
    
    # Recipients
    recipient_roles = Column(JSON, default='["project_manager", "stakeholder"]')  # Which roles receive this
    additional_recipients = Column(JSON, default='[]')  # User IDs
    
    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="status_templates")


class StatusUpdate(Base):
    """Auto-generated status updates for projects"""
    __tablename__ = "status_updates"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("status_update_templates.id"), nullable=True)
    
    # Status Info
    status = Column(String, default="on_track")  # on_track, at_risk, off_track, blocked, completed
    health = Column(String, default="green")  # green, yellow, red
    
    # Progress Metrics
    overall_progress = Column(Integer, default=0)  # 0-100%
    task_progress = Column(Integer, default=0)  # Calculated from tasks
    schedule_variance = Column(Float, default=0)  # +/- days
    budget_variance = Column(Float, default=0)  # +/- percentage
    
    # Summary
    summary = Column(Text)  # Main status message
    highlights = Column(JSON, default='[]')  # Positive updates
    concerns = Column(JSON, default='[]')  # Issues to address
    
    # Generation Info
    generated_by = Column(String, default="automated")  # automated, manual
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    effective_date = Column(DateTime(timezone=True), default=func.now())
    
    # Delivery
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime(timezone=True))
    published_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    project = relationship("Project", backref="status_updates")
    template = relationship("StatusUpdateTemplate")
    publisher = relationship("User", foreign_keys=[published_by])


class ProgressUpdate(Base):
    """Detailed progress tracking for auto-calculation"""
    __tablename__ = "progress_updates"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    
    # Total Tasks tracking
    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    in_progress_tasks = Column(Integer, default=0)
    blocked_tasks = Column(Integer, default=0)
    
    # Weighted Progress
    weighted_progress = Column(Float, default=0)  # 0-100%
    calculated_progress = Column(Float, default=0)  # From subtask estimates
    
    # Timeline Tracking
    tasks_on_schedule = Column(Integer, default=0)
    tasks_at_risk = Column(Integer, default=0)
    tasks_overdue = Column(Integer, default=0)
    
    # Resource Tracking
    hours_estimated = Column(Float, default=0)
    hours_logged = Column(Float, default=0)
    hours_remaining = Column(Float, default=0)
    
    # Burndown Data
    burndown = Column(JSON, default='[]')  # Array of {date, progress} for burndown chart
    
    # Metadata
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    calculation_timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", backref="progress_updates")


class StatusRecommendation(Base):
    """AI-generated recommendations for status changes"""
    __tablename__ = "status_recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status_update_id = Column(Integer, ForeignKey("status_updates.id"))
    
    # Recommendation Details
    recommendation_type = Column(String)  # status_change, risk_mitigation, resource_reallocation, timeline_adjustment
    current_status = Column(String)  # Current detected status
    recommended_status = Column(String)  # Recommended status change
    
    # Analysis
    reason = Column(Text)  # Why this recommendation
    confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    impact = Column(String, default="medium")  # low, medium, high
    
    # Action Items
    suggested_actions = Column(JSON, default='[]')  # List of recommended actions
    estimated_effort = Column(String)  # small, medium, large
    
    # Status
    is_accepted = Column(Boolean, default=False)
    accepted_by = Column(Integer, ForeignKey("users.id"))
    accepted_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    project = relationship("Project", backref="status_recommendations")
    status_update = relationship("StatusUpdate")
    acceptor = relationship("User", foreign_keys=[accepted_by])


class EscalationAlert(Base):
    """Escalation alerts triggered by status issues"""
    __tablename__ = "escalation_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status_update_id = Column(Integer, ForeignKey("status_updates.id"))
    
    # Escalation Details
    escalation_level = Column(String, default="level_1")  # level_1, level_2, level_3, executive
    escalation_reason = Column(String)  # risk_identified, delay_threshold_exceeded, budget_warning, etc.
    severity = Column(String, default="medium")  # low, medium, high, critical
    
    # Affected Stakeholders
    escalate_to_roles = Column(JSON, default='["project_manager", "stakeholder"]')
    escalate_to_users = Column(JSON, default='[]')  # User IDs
    
    # Details
    description = Column(Text)
    current_metrics = Column(JSON, default='{}')  # Metrics that triggered escalation
    thresholds_exceeded = Column(JSON, default='[]')  # Which thresholds
    
    # Actions
    recommended_actions = Column(JSON, default='[]')
    
    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(Integer, ForeignKey("users.id"))
    resolution_notes = Column(Text)
    
    # Tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    
    # Relationships
    project = relationship("Project", backref="escalations")
    status_update = relationship("StatusUpdate")
    resolver = relationship("User", foreign_keys=[resolved_by])
    acknowledger = relationship("User", foreign_keys=[acknowledged_by])


class NotificationLog(Base):
    """Logs of all stakeholder notifications sent"""
    __tablename__ = "notification_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    status_update_id = Column(Integer, ForeignKey("status_updates.id"))
    escalation_alert_id = Column(Integer, ForeignKey("escalation_alerts.id"))
    
    # Recipient
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_role = Column(String)
    
    # Notification Details
    notification_type = Column(String)  # status_update, escalation, recommendation
    channel = Column(String)  # email, inapp, sms, teams
    subject = Column(String)
    content = Column(Text)
    
    # Delivery Status
    delivery_status = Column(String, default="pending")  # pending, sent, failed, opened, read
    delivery_attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    
    # Engagement
    opened_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))
    clicked_at = Column(DateTime(timezone=True))
    
    # Timing
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    
    # Relationships
    status_update = relationship("StatusUpdate")
    escalation_alert = relationship("EscalationAlert")
    recipient = relationship("User", foreign_keys=[recipient_id])


class UpdateFrequency(Base):
    """Track update frequency history for escalation thresholds"""
    __tablename__ = "update_frequency"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    frequency_period = Column(String, default="daily")  # daily, weekly, monthly
    update_count = Column(Integer, default=0)
    average_update_size = Column(Float, default=0.0)
    status_change_frequency = Column(Integer, default=0)  # changes per period
    consecutive_red_updates = Column(Integer, default=0)  # consecutive red status count
    period_start = Column(DateTime(timezone=True), server_default=func.now())
    period_end = Column(DateTime(timezone=True))


# ============ PHASE 5: WHATIF SCENARIO PLANNING MODELS ============

class Scenario(Base):
    """What-if scenario for project planning"""
    __tablename__ = "scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Basic Info
    name = Column(String, nullable=False, index=True)
    description = Column(Text)
    scenario_type = Column(String, default="custom")  # custom, best_case, worst_case, most_likely, what_if
    
    # Comparisons
    baseline_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # For comparison
    comparison_scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)  # For chain comparisons
    
    # Status & Approval
    status = Column(String, default="draft")  # draft, approved, rejected, used
    is_default = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    executed_at = Column(DateTime(timezone=True))
    
    # Relationships
    project = relationship("Project", foreign_keys=[project_id], backref="scenarios")
    creator = relationship("User", foreign_keys=[created_by])
    baseline_project = relationship("Project", foreign_keys=[baseline_project_id])
    variables = relationship("ScenarioVariable", back_populates="scenario", cascade="all, delete-orphan")
    results = relationship("SimulationResult", back_populates="scenario", cascade="all, delete-orphan")


class ScenarioVariable(Base):
    """Variables that can be modified in scenarios"""
    __tablename__ = "scenario_variables"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    # Variable Definition
    name = Column(String, nullable=False)
    variable_type = Column(String, nullable=False)  # scope, resource, timeline, cost, quality
    
    # Baseline Value
    baseline_value = Column(Float, nullable=False)
    
    # Scenario Value (Change)
    scenario_value = Column(Float, nullable=False)
    change_percentage = Column(Float, nullable=False)  # % change from baseline
    change_type = Column(String, default="absolute")  # absolute, percentage, formula
    
    # Constraints
    min_value = Column(Float)
    max_value = Column(Float)
    unit = Column(String, default="units")  # units, hours, days, dollars, %
    
    # Impact Class
    impact_category = Column(String)  # High, Medium, Low
    is_critical = Column(Boolean, default=False)
    
    # Relationships
    scenario = relationship("Scenario", back_populates="variables")
    impacts = relationship("VariableImpact", back_populates="variable", cascade="all, delete-orphan")


class VariableImpact(Base):
    """Impact of variable changes on project metrics"""
    __tablename__ = "variable_impacts"
    
    id = Column(Integer, primary_key=True, index=True)
    variable_id = Column(Integer, ForeignKey("scenario_variables.id"), nullable=False)
    
    # What gets impacted
    impact_type = Column(String, nullable=False)  # timeline, budget, resources, scope, quality
    
    # Calculation
    impact_value = Column(Float, nullable=False)  # The calculated impact
    impact_unit = Column(String, default="units")
    calculation_formula = Column(String)  # Formula used to calculate impact
    
    # Probability
    probability = Column(Float, default=1.0)  # 0-1, probability of this impact occurring
    
    # Sensitivity Info
    sensitivity_score = Column(Float)  # How sensitive is this impact to small changes
    elasticity = Column(Float)  # % change in impact / % change in variable
    
    # Relationships
    variable = relationship("ScenarioVariable", back_populates="impacts")


class SimulationResult(Base):
    """Results from Monte Carlo or sensitivity analysis"""
    __tablename__ = "simulation_results"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    # Simulation Type
    simulation_type = Column(String, nullable=False)  # monte_carlo, sensitivity_analysis, what_if
    number_of_iterations = Column(Integer, default=1000)
    
    # Timeline Results
    expected_timeline = Column(Float)  # days
    timeline_best_case = Column(Float)
    timeline_worst_case = Column(Float)
    timeline_confidence_interval_95 = Column(Float)  # Range
    timeline_probability_success = Column(Float)  # 0-1
    
    # Budget Results
    expected_budget = Column(Float)  # total cost
    budget_best_case = Column(Float)
    budget_worst_case = Column(Float)
    budget_confidence_interval_95 = Column(Float)  # Range
    budget_probability_success = Column(Float)  # Within baseline
    
    # Resource Results
    expected_team_size = Column(Integer)
    peak_resource_demand = Column(Float)
    resource_constraints_identified = Column(Integer, default=0)
    
    # Quality Results
    expected_quality_score = Column(Float)  # 0-100
    quality_risk_events = Column(Integer, default=0)
    
    # Comprehensive Risk Analysis
    overall_risk_score = Column(Float)  # 0-100, higher = riskier
    critical_risk_count = Column(Integer, default=0)
    medium_risk_count = Column(Integer, default=0)
    low_risk_count = Column(Integer, default=0)
    
    # Distribution Data (for visualization)
    timeline_distribution = Column(JSON)  # Array of {value, probability} for histogram
    budget_distribution = Column(JSON)
    
    # Correlations
    budget_timeline_correlation = Column(Float)  # How correlated are budget and timeline changes
    
    # Key Findings
    risk_summary = Column(Text)
    recommendations = Column(JSON)  # Array of recommendation strings
    
    # Status & Metadata
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    execution_time_seconds = Column(Float)  # How long simulation took
    
    # Relationships
    scenario = relationship("Scenario", back_populates="results")


class SensitivityAnalysis(Base):
    """Sensitivity analysis showing which variables matter most"""
    __tablename__ = "sensitivity_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    simulation_result_id = Column(Integer, ForeignKey("simulation_results.id"), nullable=False)
    
    # Variable Being Analyzed
    variable_name = Column(String, nullable=False)
    baseline_value = Column(Float)
    
    # Sensitivity Metrics
    tornado_contribution = Column(Float)  # Its contribution to total variance (0-1)
    elasticity = Column(Float)  # % change in output / % change in input
    correlation_coefficient = Column(Float)  # How correlated with final outcome
    
    # Range Testing
    value_at_p10 = Column(Float)  # Value at 10th percentile
    value_at_p50 = Column(Float)  # Median value
    value_at_p90 = Column(Float)  # Value at 90th percentile
    
    # Impact Range
    impact_when_p10 = Column(Float)  # Outcome when variable at p10
    impact_when_p50 = Column(Float)  # Outcome when variable at p50
    impact_when_p90 = Column(Float)  # Outcome when variable at p90
    
    # Ranking
    importance_rank = Column(Integer)  # 1 = most important
    variance_contributed = Column(Float)  # % of total output variance
    
    # Relationships
    simulation_result = relationship("SimulationResult")


class ScenarioComparison(Base):
    """Comparison between multiple scenarios"""
    __tablename__ = "scenario_comparisons"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Comparison Definition
    name = Column(String, nullable=False)
    description = Column(Text)
    
    # Scenarios Being Compared (JSON array of scenario IDs)
    scenario_ids = Column(JSON, nullable=False)  # [id1, id2, id3, ...]
    
    # Comparison Results
    comparison_metrics = Column(JSON)  # Key metrics for each scenario
    winner_scenario_id = Column(Integer)  # Recommended scenario
    winner_reason = Column(Text)
    
    # Analysis
    comparative_results = Column(JSON)  # Detailed comparison data
    
    # Status
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="scenario_comparisons")
    creator = relationship("User", foreign_keys=[created_by])


class RiskDistribution(Base):
    """Distribution of risks across scenarios"""
    __tablename__ = "risk_distributions"
    
    id = Column(Integer, primary_key=True, index=True)
    simulation_result_id = Column(Integer, ForeignKey("simulation_results.id"), nullable=False)
    
    # Risk Category
    risk_type = Column(String, nullable=False)  # timeline, budget, resource, quality, scope
    
    # Distribution Points
    percentile_10 = Column(Float)
    percentile_25 = Column(Float)
    percentile_50 = Column(Float)  # Median
    percentile_75 = Column(Float)
    percentile_90 = Column(Float)
    
    # Statistics
    mean_value = Column(Float)
    std_deviation = Column(Float)
    skewness = Column(Float)
    kurtosis = Column(Float)
    
    # Distribution Type
    distribution_type = Column(String, default="normal")  # normal, lognormal, triangular
    
    # Relationships
    simulation_result = relationship("SimulationResult")


class WhatIfAnalysisLog(Base):
    """Audit log for what-if analysis runs"""
    __tablename__ = "whatif_analysis_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Analysis Info
    analysis_type = Column(String, nullable=False)  # monte_carlo, sensitivity, comparison
    
    # Details
    input_variables = Column(JSON)  # Variables modified
    parameters = Column(JSON)  # Simulation parameters
    
    # Results
    outcome = Column(String)  # success, failure, error
    duration_seconds = Column(Float)
    result_summary = Column(Text)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String)
    
    # Relationships
    scenario = relationship("Scenario")
    user = relationship("User")


class AlertDeliveryLog(Base):
    """Log of alert deliveries for tracking and analytics"""
    __tablename__ = "alert_delivery_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Delivery Details
    channel = Column(String, nullable=False)  # email, sms, inapp, teams, push
    status = Column(String, default="pending")  # pending, queued, sent, failed, bounced
    delivery_attempt = Column(Integer, default=1)
    
    # Results
    delivered_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))
    clicked_at = Column(DateTime(timezone=True))
    
    # Metadata
    device_type = Column(String)  # web, mobile, desktop (for in-app)
    user_agent = Column(String)  # Browser info
    ip_address = Column(String)
    error_message = Column(Text)  # If failed
    retry_count = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    alert = relationship("Alert", backref="delivery_logs")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="alert_deliveries")


class AlertBatch(Base):
    """Groups related alerts for intelligent batching"""
    __tablename__ = "alert_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Batch Metadata
    batch_type = Column(String)  # same_type, contextual, priority_grouped, smart_batch
    status = Column(String, default="pending")  # pending, scheduled, sent, opened
    
    # Alerts in Batch
    alert_count = Column(Integer, default=0)
    alert_ids = Column(JSON)  # [alert_id1, alert_id2, ...]
    
    # Batch Optimization
    ml_recommendation = Column(String)  # ML model predicted batching strategy
    batching_score = Column(Float)  # How good is this batch (0.0-1.0)
    estimated_reduction = Column(Float)  # Estimated % alert reduction
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    
    # Relationships
    project = relationship("Project", backref="alert_batches")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="alert_batches_received")


class PredictiveInsight(Base):
    """Stores predictions for proactive alerting"""
    __tablename__ = "predictive_insights"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    
    # Prediction Details
    insight_type = Column(String, nullable=False)  # task_delay, budget_overrun, conflict_escalation, scope_creep
    risk_level = Column(String)  # low, medium, high, critical
    confidence_score = Column(Float)  # 0.0 to 1.0
    
    # Target
    entity_type = Column(String)  # task, resource, team, project
    entity_id = Column(Integer)
    
    # Prediction
    predicted_issue = Column(String)  # Description of what might happen
    risk_factors = Column(JSON)  # [{factor: "low_resources", weight: 0.3}, ...]
    recommended_actions = Column(JSON)  # Suggested mitigation steps
    
    # Timeline
    prediction_date = Column(DateTime(timezone=True), server_default=func.now())
    expected_occurrence = Column(DateTime(timezone=True))  # When issue is predicted to occur
    
    # Validation
    alert_sent = Column(Boolean, default=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"))
    actual_issue_occurred = Column(Boolean)  # Did the prediction come true
    actual_occurrence_date = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", backref="predictive_insights")
    alert = relationship("Alert", backref="predictions")


