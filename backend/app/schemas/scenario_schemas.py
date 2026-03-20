"""
What-If Scenario Planning Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DistributionType(str, Enum):
    NORMAL = "normal"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    LOGNORMAL = "lognormal"


# ============ SIMULATION PARAMETER SCHEMAS ============

class SimulationParameterRequest(BaseModel):
    """Request for simulation parameter"""
    name: str
    baseline_value: float
    scenario_value: float
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    distribution_type: DistributionType = DistributionType.NORMAL


class SimulationParameterResponse(SimulationParameterRequest):
    """Response with simulation parameter"""
    pass


# ============ SIMULATION RESULT SCHEMAS ============

class PercentileData(BaseModel):
    """Percentile data from simulation"""
    percentile_10: float = Field(alias="10")
    percentile_25: float = Field(alias="25")
    percentile_50: float = Field(alias="50")
    percentile_75: float = Field(alias="75")
    percentile_90: float = Field(alias="90")
    
    class Config:
        allow_population_by_field_name = True


class SimulationResultResponse(BaseModel):
    """Results from Monte Carlo simulation"""
    expected_value: float
    best_case: float
    worst_case: float
    confidence_interval_95: float
    probability_success: float
    percentiles: Dict[int, float]
    std_deviation: float
    distribution: Optional[List[float]] = None


# ============ RISK IDENTIFICATION ============

class CriticalRiskResponse(BaseModel):
    """Identified critical risk in scenario"""
    variable: str
    threshold: float
    expected_value: float
    lower_bound: float
    risk_probability: float
    severity: str  # critical, medium, low


# ============ SENSITIVITY ANALYSIS ============

class TornadoAnalysisItem(BaseModel):
    """Item in tornado diagram analysis"""
    variable: str
    baseline_value: float
    scenario_value: float
    low_case: float
    high_case: float
    tornado_range: float
    elasticity: float
    importance_rank: int
    variance_contributed: float


class OneWayAnalysisResponse(BaseModel):
    """One-way sensitivity analysis result"""
    variable: str
    baseline_value: float
    range: tuple
    values: List[float]
    metrics: List[float]
    elasticity: float
    correlation_coefficient: float


class ParetoAnalysisResponse(BaseModel):
    """Pareto analysis (80/20 rule)"""
    critical_variables: List[Dict[str, Any]]
    non_critical_variables: List[Dict[str, Any]]
    critical_count: int
    non_critical_count: int
    variance_explained: float


# ============ SCENARIO CREATION ============

class ScenarioVariablesRequest(BaseModel):
    """Variables for scenario modification"""
    scope_multiplier: float = Field(default=1.0, description="Scope change factor (1.0 = no change)")
    resource_multiplier: float = Field(default=1.0, description="Resource change factor")
    quality_focus: float = Field(default=1.0, description="Quality priority (0.5-1.5)")
    hourly_rate_multiplier: float = Field(default=1.0, description="Hourly rate change factor")
    additional_params: Optional[Dict[str, float]] = None


class ScenarioCreateRequest(BaseModel):
    """Request to create a new scenario"""
    project_id: int
    scenario_name: str
    description: Optional[str] = None
    variables: ScenarioVariablesRequest


class ScenarioAnalysisResponse(BaseModel):
    """Complete scenario analysis response"""
    scenario_name: str
    variables: Dict[str, float]
    timeline: SimulationResultResponse
    budget: SimulationResultResponse
    resources: SimulationResultResponse
    quality: SimulationResultResponse
    sensitivity_analysis: List[TornadoAnalysisItem]
    critical_risks: List[CriticalRiskResponse]
    overall_risk_score: float
    created_at: str
    
    class Config:
        from_attributes = True


class ScenarioResponse(BaseModel):
    """Saved scenario"""
    id: int
    project_id: int
    user_id: int
    scenario_name: str
    description: Optional[str] = None
    variables: Dict[str, Any]
    analysis_data: Dict[str, Any]
    status: str  # draft, saved, compared
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============ SCENARIO COMPARISON ============

class ScenarioMetricsComparison(BaseModel):
    """Metrics for scenario in comparison"""
    scenario_name: str
    timeline_expected: float
    budget_expected: float
    risk_score: float
    quality_expected: float
    success_probability: float


class ScenarioComparison(BaseModel):
    """Comparison result for multiple scenarios"""
    scenario_count: int
    scenarios: List[Dict[str, Any]]
    winner: Optional[str]
    winner_reason: Optional[str]
    recommendations: List[str]
    comparison_metrics: Dict[str, Any]


class ComparisonTableRow(BaseModel):
    """Row in comparison table"""
    scenario: str
    timeline: str
    budget: str
    risk: str
    quality: str
    success: str


# ============ PROBABILITY DISTRIBUTION ============

class DistributionStatistics(BaseModel):
    """Statistical properties of a distribution"""
    mean: float
    median: float
    std: float
    min: float
    max: float
    skewness: float
    kurtosis: float


class DistributionParams(BaseModel):
    """Parameters for a specific distribution type"""
    mu: Optional[float] = None
    sigma: Optional[float] = None
    shape: Optional[float] = None
    loc: Optional[float] = None
    scale: Optional[float] = None


class FittedDistributionResponse(BaseModel):
    """Fitted distribution information"""
    best_fit: str
    all_fits: Dict[str, Dict[str, Any]]
    data_stats: DistributionStatistics


class ConfidenceIntervalResponse(BaseModel):
    """Confidence interval calculation"""
    confidence_level: float
    lower_bound: float
    upper_bound: float
    range: float
    mean: float
    median: float


# ============ BATCH OPERATIONS ============

class BatchScenarioRequest(BaseModel):
    """Request to create multiple scenarios"""
    project_id: int
    scenarios: List[Dict[str, Any]]


class BatchScenarioResponse(BaseModel):
    """Response with multiple scenario analyses"""
    total_scenarios: int
    successful: int
    failed: int
    analyses: List[ScenarioAnalysisResponse]


# ============ WHAT-IF QUESTIONS ============

class WhatIfQuestion(BaseModel):
    """What-if question for natural language processing"""
    project_id: int
    question: str  # e.g., "What if we reduce the scope by 20%?"


class WhatIfQuestionResponse(BaseModel):
    """Response to what-if question"""
    question: str
    interpreted_variables: Dict[str, float]
    scenario_analysis: ScenarioAnalysisResponse
    key_insights: List[str]
    recommendations: List[str]


# ============ DASHBOARD WIDGETS ============

class ScenarioComparationDashboard(BaseModel):
    """Dashboard data for scenario comparison"""
    current_scenarios: List[ScenarioResponse]
    best_scenario: Optional[ScenarioResponse]
    risk_heatmap: Dict[str, List[float]]
    key_metrics: Dict[str, float]
    alerts: List[Dict[str, str]]


class SensitivityDashboard(BaseModel):
    """Dashboard for sensitivity analysis"""
    tornado_diagram: List[TornadoAnalysisItem]
    pareto_analysis: ParetoAnalysisResponse
    critical_variables: List[str]
    recommendations: List[str]


class RiskDashboard(BaseModel):
    """Dashboard for risk analysis"""
    overall_risk_score: float
    critical_risks: List[CriticalRiskResponse]
    risk_distribution: Dict[str, int]
    mitigation_status: Dict[str, int]


# ============ DECISION SUPPORT ============

class ConfidenceScoreItem(BaseModel):
    """Per-metric confidence score for a scenario"""
    scenario: str
    scenario_id: int
    overall: float
    timeline: float
    budget: float
    quality: float
    risk: float


class TradeoffPoint(BaseModel):
    """Tradeoff analysis data point (cost vs time vs quality bubble)"""
    scenario: str
    scenario_id: int
    is_optimal: bool
    cost_index: float
    time_index: float
    quality_index: float
    risk_index: float
    expected_timeline_days: float
    expected_budget_usd: float
    expected_quality: float
    composite_score: float


class DecisionSupportResponse(BaseModel):
    """AI-powered decision support response"""
    has_scenarios: bool
    project_id: Optional[int] = None
    project_baseline: Optional[Dict[str, Any]] = None
    scenarios: List[Dict[str, Any]] = []
    optimal_scenario: Optional[Dict[str, Any]] = None
    worst_scenario: Optional[Dict[str, Any]] = None
    confidence_scores: List[Dict[str, Any]] = []
    tradeoff_analysis: List[Dict[str, Any]] = []
    ai_insights: List[str] = []
    recommendations: List[str] = []
    message: Optional[str] = None
