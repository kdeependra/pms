from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

# User Schemas
class UserRole(str, Enum):
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    TEAM_MEMBER = "team_member"
    STAKEHOLDER = "stakeholder"

class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.TEAM_MEMBER
    department: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    department: Optional[str] = None

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

class TokenData(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None

# Project Schemas
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "planning"
    priority: str = "medium"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    budget: Optional[int] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    end_date: Optional[datetime] = None
    budget: Optional[int] = None
    progress: Optional[int] = None

class ProjectResponse(ProjectBase):
    id: int
    owner_id: int
    actual_cost: Optional[int] = None
    progress: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Task Schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: int
    assignee_id: Optional[int] = None
    status: str = "todo"
    priority: str = "medium"
    due_date: Optional[datetime] = None
    estimated_hours: Optional[float] = None
    parent_task_id: Optional[int] = None
    is_recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None
    recurrence_interval: Optional[int] = 1
    recurrence_end_date: Optional[datetime] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    actual_hours: Optional[float] = None
    progress: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None
    recurrence_interval: Optional[int] = None
    recurrence_end_date: Optional[datetime] = None

class TaskResponse(TaskBase):
    id: int
    actual_hours: Optional[float] = None
    progress: int
    is_recurring: Optional[bool] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Comment Schemas
class CommentBase(BaseModel):
    content: str

class CommentCreate(CommentBase):
    task_id: int

class CommentResponse(CommentBase):
    id: int
    task_id: int
    author_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Document Schemas
class TaskDocumentResponse(BaseModel):
    id: int
    task_id: int
    filename: str
    file_size: int
    file_type: str
    uploaded_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Time Log Schemas
class TimeLogBase(BaseModel):
    hours: float
    description: Optional[str] = None

class TimeLogCreate(TimeLogBase):
    task_id: int
    date: Optional[datetime] = None

class TimeLogResponse(TimeLogBase):
    id: int
    task_id: int
    user_id: int
    date: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True

# Task Dependency Schemas
class TaskDependencyBase(BaseModel):
    predecessor_id: int
    successor_id: int
    dependency_type: str = "finish_to_start"
    lag_days: int = 0

class TaskDependencyCreate(TaskDependencyBase):
    pass

class TaskDependencyResponse(TaskDependencyBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# Risk Schemas
class RiskBase(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    mitigation_plan: Optional[str] = None
    status: str = "identified"

class RiskCreate(RiskBase):
    pass

class RiskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    probability: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)
    mitigation_plan: Optional[str] = None
    status: Optional[str] = None

class RiskResponse(RiskBase):
    id: int
    risk_score: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# AI Prediction Schemas
class TimelinePrediction(BaseModel):
    project_id: int
    predicted_completion_date: datetime
    confidence_score: float
    potential_delays: List[str]
    recommendations: List[str]

class ResourceOptimization(BaseModel):
    project_id: int
    over_allocated_resources: List[dict]
    under_utilized_resources: List[dict]
    optimization_suggestions: List[str]

class RiskPrediction(BaseModel):
    project_id: int
    predicted_risks: List[dict]
    risk_level: str
    mitigation_strategies: List[str]

# Milestone Schemas
class MilestoneBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_date: datetime
    is_critical: bool = False
    progress: int = Field(default=0, ge=0, le=100)
    order: int = 0

class MilestoneCreate(MilestoneBase):
    project_id: int

class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[datetime] = None
    actual_date: Optional[datetime] = None
    status: Optional[str] = None
    is_critical: Optional[bool] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    order: Optional[int] = None

class MilestoneResponse(MilestoneBase):
    id: int
    project_id: int
    actual_date: Optional[datetime] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class MilestoneAnalytics(BaseModel):
    total_milestones: int
    achieved_milestones: int
    pending_milestones: int
    missed_milestones: int
    at_risk_milestones: int
    critical_path_milestones: List[MilestoneResponse]
    upcoming_milestones: List[MilestoneResponse]
    achievement_rate: float


# Workflow Schemas
class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class AssignmentRule(BaseModel):
    rule_type: str  # role, department, round_robin, workload_based
    target_role: Optional[str] = None
    target_department: Optional[str] = None
    conditions: Optional[dict] = None


class ConditionLogic(BaseModel):
    field: str  # task field to evaluate
    operator: str  # equals, not_equals, greater_than, less_than, contains
    value: str
    next_stage_id: Optional[int] = None


class WorkflowStageBase(BaseModel):
    name: str
    description: Optional[str] = None
    stage_type: str = "task"  # task, approval, condition, start, end
    requires_approval: bool = False
    approver_role: Optional[str] = None
    approver_user_id: Optional[int] = None
    auto_assign: bool = False
    assignment_rule: Optional[dict] = None
    position_x: float = 0
    position_y: float = 0
    order: int = 0


class WorkflowStageCreate(WorkflowStageBase):
    workflow_id: int


class WorkflowStageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stage_type: Optional[str] = None
    requires_approval: Optional[bool] = None
    approver_role: Optional[str] = None
    approver_user_id: Optional[int] = None
    auto_assign: Optional[bool] = None
    assignment_rule: Optional[dict] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    order: Optional[int] = None


class WorkflowStageResponse(WorkflowStageBase):
    id: int
    workflow_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowTransitionBase(BaseModel):
    from_stage_id: int
    to_stage_id: int
    name: Optional[str] = None
    condition_type: str = "always"  # always, approved, rejected, conditional
    condition_logic: Optional[dict] = None
    order: int = 0


class WorkflowTransitionCreate(WorkflowTransitionBase):
    workflow_id: int


class WorkflowTransitionUpdate(BaseModel):
    name: Optional[str] = None
    condition_type: Optional[str] = None
    condition_logic: Optional[dict] = None
    order: Optional[int] = None


class WorkflowTransitionResponse(WorkflowTransitionBase):
    id: int
    workflow_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[int] = None
    status: WorkflowStatus = WorkflowStatus.DRAFT
    is_template: bool = False


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[WorkflowStatus] = None
    is_template: Optional[bool] = None


class WorkflowResponse(WorkflowBase):
    id: int
    created_by: int
    version: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    stages: List[WorkflowStageResponse] = []
    transitions: List[WorkflowTransitionResponse] = []
    
    class Config:
        from_attributes = True


class WorkflowInstanceBase(BaseModel):
    workflow_id: int
    task_id: int
    instance_metadata: Optional[dict] = None


class WorkflowInstanceCreate(WorkflowInstanceBase):
    pass


class WorkflowInstanceUpdate(BaseModel):
    current_stage_id: Optional[int] = None
    status: Optional[str] = None
    instance_metadata: Optional[dict] = None


class WorkflowApprovalBase(BaseModel):
    comments: Optional[str] = None


class WorkflowApprovalCreate(WorkflowApprovalBase):
    instance_id: int
    stage_id: int


class WorkflowApprovalAction(BaseModel):
    status: str  # approved, rejected
    comments: Optional[str] = None


class WorkflowApprovalResponse(WorkflowApprovalBase):
    id: int
    instance_id: int
    stage_id: int
    approver_id: int
    status: str
    requested_at: datetime
    responded_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class WorkflowHistoryResponse(BaseModel):
    id: int
    instance_id: int
    from_stage_id: Optional[int] = None
    to_stage_id: Optional[int] = None
    action: str
    performed_by: int
    comments: Optional[str] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True


class WorkflowInstanceResponse(WorkflowInstanceBase):
    id: int
    current_stage_id: Optional[int] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    started_by: int
    approvals: List[WorkflowApprovalResponse] = []
    history: List[WorkflowHistoryResponse] = []
    
    class Config:
        from_attributes = True


# Resource Management Schemas

# Skill Schemas
class SkillBase(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None

class SkillCreate(SkillBase):
    pass

class SkillResponse(SkillBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Resource Skill Assignment Schemas
class ResourceSkillAssign(BaseModel):
    skill_id: int
    proficiency_level: str = "beginner"  # beginner/intermediate/advanced/expert
    years_experience: float = 0.0

class ResourceSkillUpdate(BaseModel):
    proficiency_level: Optional[str] = None
    years_experience: Optional[float] = None

class ResourceSkillResponse(BaseModel):
    skill_id: int
    skill_name: str
    skill_category: Optional[str] = None
    proficiency_level: str
    years_experience: float

class SkillMatrixResource(BaseModel):
    resource_id: int
    resource_name: str
    role: Optional[str] = None
    department: Optional[str] = None
    skills: List[ResourceSkillResponse] = []


# Resource Schemas
class ResourceBase(BaseModel):
    user_id: int
    role: Optional[str] = None
    department: Optional[str] = None
    cost_per_hour: float = 0
    availability_percentage: float = 100
    is_available: bool = True
    vacation_days_remaining: float = 0

class ResourceCreate(ResourceBase):
    pass

class ResourceUpdate(BaseModel):
    role: Optional[str] = None
    department: Optional[str] = None
    cost_per_hour: Optional[float] = None
    availability_percentage: Optional[float] = None
    is_available: Optional[bool] = None
    vacation_days_remaining: Optional[float] = None

class ResourceResponse(ResourceBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Resource Allocation Schemas
class ResourceAllocationBase(BaseModel):
    resource_id: int
    project_id: int
    task_id: Optional[int] = None
    allocation_percentage: float = 100
    start_date: datetime
    end_date: datetime
    notes: Optional[str] = None

class ResourceAllocationCreate(ResourceAllocationBase):
    pass

class ResourceAllocationUpdate(BaseModel):
    allocation_percentage: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class ResourceAllocationResponse(ResourceAllocationBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    created_by: int
    
    class Config:
        from_attributes = True


# Timesheet Schemas
class TimesheetBase(BaseModel):
    resource_id: int
    project_id: int
    task_id: Optional[int] = None
    date: datetime
    hours: float
    is_billable: bool = True
    description: Optional[str] = None

class TimesheetCreate(TimesheetBase):
    pass

class TimesheetUpdate(BaseModel):
    hours: Optional[float] = None
    is_billable: Optional[bool] = None
    description: Optional[str] = None
    status: Optional[str] = None

class TimesheetResponse(TimesheetBase):
    id: int
    status: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Leave Request Schemas
class LeaveRequestBase(BaseModel):
    resource_id: int
    leave_type: str
    start_date: datetime
    end_date: datetime
    days_count: float
    reason: Optional[str] = None

class LeaveRequestCreate(LeaveRequestBase):
    pass

class LeaveRequestUpdate(BaseModel):
    status: Optional[str] = None
    rejection_reason: Optional[str] = None

class LeaveRequestResponse(LeaveRequestBase):
    id: int
    status: str
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Workload Analytics Schemas
class ResourceUtilization(BaseModel):
    resource_id: int
    resource_name: str
    department: str
    allocated_hours: float
    available_hours: float
    utilization_percentage: float
    is_overallocated: bool


class WorkloadHeatmap(BaseModel):
    date: datetime
    resources: List[ResourceUtilization]


class CapacityForecast(BaseModel):
    period: str
    total_capacity: float
    allocated_capacity: float
    available_capacity: float
    utilization_percentage: float


class OverallocationAlert(BaseModel):
    resource_id: int
    resource_name: str
    department: Optional[str] = None
    role: Optional[str] = None
    current_utilization: float
    excess_percentage: float
    overloaded_projects: List[dict] = []
    recommendations: List[str] = []
    alternative_resources: List[dict] = []


class HRMSSyncResult(BaseModel):
    status: str  # success / partial / error
    synced_count: int
    skipped_count: int
    errors: List[str] = []
    last_sync_at: Optional[datetime] = None
    message: str


# Budget and Financial Management Schemas
class BudgetCategoryBase(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    category_type: str = "labor"

class BudgetCategoryCreate(BudgetCategoryBase):
    pass

class BudgetCategoryResponse(BudgetCategoryBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class BudgetItemBase(BaseModel):
    project_id: int
    category_id: int
    description: str
    planned_amount: float
    gl_code: Optional[str] = None
    cost_center: Optional[str] = None
    purchase_order_number: Optional[str] = None
    is_billable: bool = False
    fiscal_year: Optional[str] = None
    quarter: Optional[str] = None

class BudgetItemCreate(BudgetItemBase):
    pass

class BudgetItemUpdate(BaseModel):
    description: Optional[str] = None
    planned_amount: Optional[float] = None
    actual_amount: Optional[float] = None
    committed_amount: Optional[float] = None
    gl_code: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class BudgetItemResponse(BudgetItemBase):
    id: int
    actual_amount: float
    committed_amount: float
    variance: float
    variance_percentage: float
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class BudgetTransactionBase(BaseModel):
    budget_item_id: int
    transaction_date: datetime
    transaction_type: str
    amount: float
    description: str
    reference_number: Optional[str] = None
    vendor_name: Optional[str] = None

class BudgetTransactionCreate(BudgetTransactionBase):
    pass

class BudgetTransactionResponse(BudgetTransactionBase):
    id: int
    payment_status: str
    approved_by: Optional[int] = None
    created_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class CashFlowProjectionResponse(BaseModel):
    id: int
    project_id: int
    period: datetime
    projected_inflow: float
    projected_outflow: float
    net_cash_flow: float
    cumulative_cash_flow: float
    confidence_level: Optional[float] = None
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class BudgetSummary(BaseModel):
    total_budget: float
    total_actual: float
    total_committed: float
    total_variance: float
    variance_percentage: float
    budget_items_count: int
    categories_breakdown: List[dict]


# Issue Management Schemas
class IssueCategory(str, Enum):
    TECHNICAL = "technical"
    RESOURCE = "resource"
    BUDGET = "budget"
    SCOPE = "scope"
    QUALITY = "quality"
    STAKEHOLDER = "stakeholder"
    OTHER = "other"

class IssueSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class IssueStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class IssueBase(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    title: str
    description: str
    category: IssueCategory = IssueCategory.OTHER
    severity: IssueSeverity = IssueSeverity.MEDIUM
    priority: int = 3
    assigned_to: Optional[int] = None

class IssueCreate(IssueBase):
    pass

class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[IssueCategory] = None
    severity: Optional[IssueSeverity] = None
    status: Optional[IssueStatus] = None
    priority: Optional[int] = None
    assigned_to: Optional[int] = None
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    remedy_ticket_id: Optional[str] = None

class IssueResponse(IssueBase):
    id: int
    status: IssueStatus
    reported_by: int
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    resolution_date: Optional[datetime] = None
    sla_due_date: Optional[datetime] = None
    sla_status: str
    remedy_ticket_id: Optional[str] = None
    days_open: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class IssueCommentBase(BaseModel):
    content: str
    is_internal: bool = False

class IssueCommentCreate(IssueCommentBase):
    pass

class IssueCommentResponse(IssueCommentBase):
    id: int
    issue_id: int
    author_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Document Management Schemas
class DocumentStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ARCHIVED = "archived"


class DocumentBase(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    document_type: Optional[str] = None
    tags: Optional[List[str]] = None
    is_public: bool = False
    requires_approval: bool = False

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    status: Optional[DocumentStatus] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None

class DocumentResponse(DocumentBase):
    id: int
    status: DocumentStatus
    current_version: int
    current_file_path: Optional[str] = None
    current_file_size: Optional[int] = None


# ==================== Sentiment Analysis & Stakeholder Feedback Schemas ====================

# Survey Schemas
class SurveySentiment(str, Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class SurveyQuestionBase(BaseModel):
    question: str
    question_type: str  # text, rating, multiple_choice, nps
    category: Optional[str] = None
    order: int = 0
    is_required: bool = True

class SurveyQuestionCreate(SurveyQuestionBase):
    project_id: int
    options: Optional[List[str]] = None  # For multiple choice

class SurveyQuestionResponse(SurveyQuestionBase):
    id: int
    project_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class SurveyResponseBase(BaseModel):
    survey_id: int
    respondent_id: int
    respondent_email: Optional[str] = None
    respondent_name: Optional[str] = None
    respondent_role: Optional[str] = None  # stakeholder, team_member, manager, etc.

class SurveyResponseCreate(SurveyResponseBase):
    pass

class SurveyResponseUpdate(BaseModel):
    sentiment_score: Optional[float] = None
    feedback_text: Optional[str] = None
    action_items: Optional[List[str]] = None

class SurveyResponseResponse(SurveyResponseBase):
    id: int
    sentiment_score: float
    sentiment_category: SurveySentiment
    feedback_text: Optional[str] = None
    action_items: Optional[List[str]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class SurveyBase(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    survey_type: str  # general, satisfaction, engagement, stakeholder, post_mortem
    status: str = "draft"  # draft, active, closed
    target_audience: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class SurveyCreate(SurveyBase):
    pass

class SurveyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    end_date: Optional[datetime] = None

class SurveyResponse(SurveyBase):
    id: int
    created_by: int
    total_responses: int = 0
    avg_rating: float = 0.0
    response_rate: float = 0.0
    nps_score: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    questions: List[SurveyQuestionResponse] = []
    responses: List[SurveyResponseResponse] = []
    
    class Config:
        from_attributes = True


class SurveyAnalyticsResponse(BaseModel):
    survey_id: int
    total_surveys: int
    avg_rating: float
    response_rate: float
    nps_score: int
    positive_percentage: float
    neutral_percentage: float
    negative_percentage: float
    category_breakdown: List[dict]
    weekly_trend: List[dict]
    sentiment_distribution: dict


# Stakeholder Feedback Schemas
class FeedbackBase(BaseModel):
    project_id: int
    feedback_type: str  # general, requirement, issue, compliment, suggestion
    content: str
    stakeholder_id: Optional[int] = None
    stakeholder_email: Optional[str] = None
    stakeholder_name: Optional[str] = None
    stakeholder_role: Optional[str] = None
    is_anonymous: bool = False
    attachments: Optional[List[str]] = None

class FeedbackCreate(FeedbackBase):
    pass

class FeedbackUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    resolution: Optional[str] = None
    action_items: Optional[List[str]] = None

class FeedbackResponse(FeedbackBase):
    id: int
    status: str = "open"  # open, in_progress, resolved, closed
    sentiment: SurveySentiment
    sentiment_score: float
    key_topics: List[str]
    action_items: List[str]
    assigned_to: Optional[int] = None
    resolution: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class FeedbackAnalyticsResponse(BaseModel):
    total_feedback: int
    open_feedback: int
    resolved_feedback: int
    avg_sentiment_score: float
    sentiment_distribution: dict
    top_topics: List[dict]
    feedback_by_type: dict
    feedback_trend: List[dict]
    action_item_status: dict


# Communication Sentiment Analysis
class CommunicationSentimentAnalysis(BaseModel):
    communication_type: str  # email, message, meeting, comment
    total_communications: int
    positive_percentage: float
    neutral_percentage: float
    negative_percentage: float
    overall_sentiment: float  # -1.0 to 1.0
    daily_sentiment: List[dict]
    sentiment_keywords: dict


# Stakeholder Satisfaction Tracking
class StakeholderSatisfactionBase(BaseModel):
    project_id: int
    stakeholder_id: Optional[int] = None
    stakeholder_email: Optional[str] = None
    satisfaction_score: float = Field(ge=0, le=5)
    confidence_level: float = Field(ge=0, le=1)
    key_areas: dict  # {area: score}
    last_updated: datetime

class StakeholderSatisfactionResponse(StakeholderSatisfactionBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Action Item from Feedback
class ActionItemBase(BaseModel):
    feedback_id: Optional[int] = None
    survey_response_id: Optional[int] = None
    project_id: int
    title: str
    description: Optional[str] = None
    priority: str = "medium"  # low, medium, high, critical
    assigned_to: Optional[int] = None
    due_date: Optional[datetime] = None
    status: str = "open"  # open, in_progress, completed, cancelled

class ActionItemCreate(ActionItemBase):
    pass

class ActionItemUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    completion_notes: Optional[str] = None

class ActionItemResponse(ActionItemBase):
    id: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    
    class Config:
        from_attributes = True


# Sentiment Analysis Summary
class SentimentAnalysisSummary(BaseModel):
    period: str  # "last_7_days", "last_30_days", "last_90_days"
    overall_sentiment: float
    trend: str  # "improving", "declining", "stable"
    positive_count: int
    neutral_count: int
    negative_count: int
    key_themes: List[dict]
    areas_of_concern: List[dict]
    opportunities: List[dict]
    sharepoint_url: Optional[str] = None
    owner_id: int
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class DocumentVersionBase(BaseModel):
    version_number: int
    version_type: str = "minor"
    change_summary: Optional[str] = None

class DocumentVersionCreate(DocumentVersionBase):
    file_path: str
    file_size: int

class DocumentVersionResponse(DocumentVersionBase):
    id: int
    document_id: int
    file_path: str
    file_size: int
    file_hash: Optional[str] = None
    is_checked_out: bool
    checked_out_by: Optional[int] = None
    checked_out_at: Optional[datetime] = None
    changed_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentApprovalBase(BaseModel):
    status: str = "pending"
    comments: Optional[str] = None

class DocumentApprovalCreate(DocumentApprovalBase):
    pass

class DocumentApprovalResponse(DocumentApprovalBase):
    id: int
    document_id: int
    version_id: int
    approver_id: int
    approved_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# Kanban Board Schemas
class KanbanColumnBase(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    order: int = 0
    wip_limit: Optional[int] = None
    task_status_mapping: Optional[str] = None
    is_done_column: bool = False

class KanbanColumnCreate(KanbanColumnBase):
    pass

class KanbanColumnResponse(KanbanColumnBase):
    id: int
    board_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class KanbanBoardBase(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    is_default: bool = False

class KanbanBoardCreate(KanbanBoardBase):
    columns: Optional[List[KanbanColumnCreate]] = None

class KanbanBoardResponse(KanbanBoardBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    columns: List[KanbanColumnResponse] = []
    
    class Config:
        from_attributes = True


# Gantt Chart Schemas
class GanttViewBase(BaseModel):
    project_id: int
    name: str
    description: Optional[str] = None
    view_type: str = "timeline"
    zoom_level: str = "day"
    show_critical_path: bool = True
    show_milestones: bool = True
    show_dependencies: bool = True
    show_progress: bool = True
    color_by: str = "status"
    is_default: bool = False

class GanttViewCreate(GanttViewBase):
    filters: Optional[dict] = None

class GanttViewResponse(GanttViewBase):
    id: int
    baseline_date: Optional[datetime] = None
    filters: Optional[dict] = None
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ==================== RBAC (Role-Based Access Control) Schemas ====================

class PermissionBase(BaseModel):
    name: str
    resource: str
    action: str
    description: Optional[str] = None
    category: str = "general"

class PermissionCreate(PermissionBase):
    pass

class PermissionUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

class PermissionResponse(BaseModel):
    id: int
    name: str
    resource: str = "general"
    action: str = "read"
    description: Optional[str] = None
    category: Optional[str] = "general"
    is_active: Optional[bool] = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None

class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    description: Optional[str] = None
    is_active: Optional[bool] = None

class RolePermissionUpdate(BaseModel):
    permissions: List[int]  # List of permission IDs

class RoleResponse(RoleBase):
    id: int
    is_system_role: bool
    is_active: bool
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    permissions: List[PermissionResponse] = []

    class Config:
        from_attributes = True


class RoleDetailResponse(RoleResponse):
    pass


class UserRoleAssignment(BaseModel):
    role_id: int

class UserRoleRemoval(BaseModel):
    role_id: int


class UserWithRoles(UserResponse):
    assigned_roles: List[RoleResponse] = []

    class Config:
        from_attributes = True


class AdminRoleManagementResponse(BaseModel):
    message: str
    status: str  # success, error
    data: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Communication Analysis Schemas
class CommunicationMessageBase(BaseModel):
    project_id: int
    sender_id: int
    message_type: str  # email, chat, comment, thread
    channel: Optional[str] = None
    subject: Optional[str] = None
    content: str
    recipient_ids: Optional[dict] = None

class CommunicationMessageCreate(CommunicationMessageBase):
    pass

class CommunicationMessageResponse(CommunicationMessageBase):
    id: int
    sentiment_score: Optional[float] = None
    sentiment_category: Optional[str] = None
    confidence: Optional[float] = None
    tone: Optional[str] = None
    mentions: Optional[dict] = None
    key_topics: Optional[list] = None
    action_items: Optional[list] = None
    contains_conflict: bool
    conflict_score: float
    conflict_type: Optional[str] = None
    reply_count: int = 0
    response_time_minutes: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class CollaborationMetricsBase(BaseModel):
    project_id: int
    team_member_id: int
    period_date: datetime
    period_type: str = "daily"

class CollaborationMetricsResponse(CollaborationMetricsBase):
    id: int
    messages_sent: int
    messages_received: int
    avg_message_length: float
    avg_response_time: float
    messages_with_response: int
    response_rate: float
    topics_discussed: Optional[list] = None
    mentions_received: int
    replied_to_count: int
    collaboration_score: float
    avg_sentiment: float
    positive_messages: int
    negative_messages: int
    neutral_messages: int
    involved_in_conflicts: int
    conflict_resolution_rate: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConflictAlertBase(BaseModel):
    project_id: int
    severity: str = "low"  # low, medium, high, critical
    type: str
    involved_users: list
    message_id: Optional[int] = None

class ConflictAlertCreate(ConflictAlertBase):
    pass

class ConflictAlertUpdate(BaseModel):
    severity: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    resolution_notes: Optional[str] = None

class ConflictAlertResponse(ConflictAlertBase):
    id: int
    status: str
    assigned_to: Optional[int] = None
    resolution_notes: Optional[str] = None
    confidence_score: float
    negative_sentiment_count: int
    escalation_count: int
    created_at: datetime
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CommunicationAnalyticsRequest(BaseModel):
    project_id: int
    start_date: datetime
    end_date: datetime
    message_type: Optional[str] = None
    channel: Optional[str] = None


class CommunicationAnalyticsResponse(BaseModel):
    project_id: int
    period: str
    total_messages: int
    message_breakdown: dict  # {type: count}
    avg_sentiment: float
    sentiment_distribution: dict  # {category: count}
    
    # Conflict Metrics
    conflict_alerts: int
    critical_conflicts: int
    resolved_conflicts: int
    
    # Participation
    active_participants: int
    most_active_users: list  # [{user_id, user_name, message_count}]
    
    # Topics
    top_topics: list  # [{topic, count, sentiment}]
    
    # Collaboration Health
    avg_response_time: float
    collaboration_score: float
    
    # Recommendations
    recommendations: list  # Suggested actions


class ConflictDetectionRequest(BaseModel):
    message_id: int
    text: str
    
class ConflictDetectionResponse(BaseModel):
    contains_conflict: bool
    conflict_score: float  # 0.0 to 1.0
    conflict_type: Optional[str] = None
    affected_users: list
    recommended_action: str
    confidence: float


# Intelligent Alerts & Status Updates Schemas
class AlertCreate(BaseModel):
    project_id: int
    template_id: int
    alert_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    context_data: Optional[dict] = None
    priority: str = "medium"
    recipient_id: int
    is_predictive: bool = False
    prediction_confidence: Optional[float] = None


class AlertResponse(BaseModel):
    id: int
    project_id: int
    alert_type: str
    title: str
    description: Optional[str] = None
    priority: str
    urgency_score: float
    delivery_status: str
    is_predictive: bool
    prediction_confidence: Optional[float] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AlertPreferenceCreate(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = False
    inapp_enabled: bool = True
    teams_enabled: bool = False
    push_enabled: bool = True
    batching_enabled: bool = True
    batch_interval: int = 300
    quiet_hours_enabled: bool = True
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    max_daily_alerts: int = 20
    suppress_duplicate_duration: int = 3600


class AlertPreferenceResponse(AlertPreferenceCreate):
    id: int
    user_id: int
    project_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class PredictiveInsightResponse(BaseModel):
    id: int
    project_id: int
    insight_type: str
    risk_level: str
    confidence_score: float
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    predicted_issue: str
    risk_factors: Optional[list] = None
    recommended_actions: Optional[list] = None
    prediction_date: datetime
    expected_occurrence: Optional[datetime] = None
    actual_issue_occurred: Optional[bool] = None
    
    class Config:
        from_attributes = True


class AlertBatchResponse(BaseModel):
    id: int
    project_id: int
    batch_type: str
    status: str
    alert_count: int
    alert_ids: list
    batching_score: float
    estimated_reduction: float
    created_at: datetime
    sent_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AlertAnalyticsResponse(BaseModel):
    period_days: int
    total_alerts: int
    sent_alerts: int
    opened_alerts: int
    open_rate: float
    by_priority: list
    by_type: list
    predictive_alerts: int
    batched_alerts: int
