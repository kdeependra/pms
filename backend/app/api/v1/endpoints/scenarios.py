from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Project, Task, User
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import Optional, List
import random

router = APIRouter()

# ── In-memory scenario store (demo) ─────────────────────────────────────────
_scenarios: dict[int, dict] = {}
_next_id = 1


class ScenarioCreateRequest(BaseModel):
    project_id: int
    scenario_name: str
    variables: dict = {}


class WhatIfQuestionRequest(BaseModel):
    project_id: int
    question: str


def _simulate_scenario(name: str, project: Project, tasks: list, variables: dict, sid: int) -> dict:
    scope_m = variables.get("scope_multiplier", 1.0)
    resource_m = variables.get("resource_multiplier", 1.0)
    quality_f = variables.get("quality_focus", 1.0)
    rate_m = variables.get("hourly_rate_multiplier", 1.0)

    base_days = max(len(tasks) * 3, 30)
    base_budget = max(len(tasks) * 2000, 20000)

    expected_days = round(base_days * scope_m / resource_m, 1)
    expected_budget = round(base_budget * scope_m * rate_m, 2)
    quality_score = round(min(100, 65 * quality_f + random.uniform(-5, 10)), 1)
    risk_score = round(max(5, 50 * scope_m / resource_m + random.uniform(-10, 10)), 1)
    success_prob = round(max(0.3, min(0.95, 0.8 / scope_m * resource_m + random.uniform(-0.1, 0.1))), 2)

    return {
        "id": sid,
        "name": name,
        "scenario_name": name,
        "project_id": project.id if project else 0,
        "variables": variables,
        "composite_score": round(quality_score * 0.3 + (100 - risk_score) * 0.3 + success_prob * 100 * 0.2 + max(0, 100 - expected_days) * 0.2, 1),
        "time_efficiency": round(max(10, 100 - expected_days * 0.5 + random.uniform(-5, 5)), 1),
        "cost_efficiency": round(max(10, 100 - expected_budget / 1000 + random.uniform(-5, 5)), 1),
        "quality_score": quality_score,
        "risk_mitigation": round(100 - risk_score, 1),
        "predictability": round(random.uniform(55, 85), 1),
        "overall_confidence": round(success_prob * 100, 1),
        "timeline": {
            "best_case": round(expected_days * 0.8),
            "expected_value": round(expected_days),
            "worst_case": round(expected_days * 1.4),
        },
        "budget": {
            "expected_value": round(expected_budget),
        },
        "analysis_data": {
            "overall_risk_score": risk_score,
            "timeline": {"expected_value": expected_days},
            "budget": {"expected_value": expected_budget},
            "quality": {"expected_value": quality_score},
        },
    }


# ── POST /scenarios/create ───────────────────────────────────────────────────

@router.post("/create")
async def create_scenario(
    body: ScenarioCreateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    global _next_id
    project = (await db.execute(select(Project).where(Project.id == body.project_id))).scalar_one_or_none()
    tasks = (await db.execute(select(Task))).scalars().all()

    sid = _next_id
    _next_id += 1
    scenario = _simulate_scenario(body.scenario_name, project, tasks, body.variables, sid)
    _scenarios[sid] = scenario
    return scenario


# ── POST /scenarios/batch ────────────────────────────────────────────────────

@router.post("/batch")
async def batch_create(
    body: list[ScenarioCreateRequest] = Body(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    global _next_id
    tasks = (await db.execute(select(Task))).scalars().all()
    results = []
    for item in body:
        project = (await db.execute(select(Project).where(Project.id == item.project_id))).scalar_one_or_none()
        sid = _next_id
        _next_id += 1
        scenario = _simulate_scenario(item.scenario_name, project, tasks, item.variables, sid)
        _scenarios[sid] = scenario
        results.append(scenario)
    return results


# ── GET /scenarios/list/{project_id} ─────────────────────────────────────────

@router.get("/list/{project_id}")
async def list_scenarios(
    project_id: int,
    current_user=Depends(get_current_user),
):
    return [s for s in _scenarios.values() if s.get("project_id") == project_id]


# ── GET /scenarios/{scenario_id} ─────────────────────────────────────────────

@router.get("/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    current_user=Depends(get_current_user),
):
    if scenario_id in _scenarios:
        return _scenarios[scenario_id]
    return {"detail": "Not found"}


# ── DELETE /scenarios/{scenario_id} ──────────────────────────────────────────

@router.delete("/{scenario_id}")
async def delete_scenario(
    scenario_id: int,
    current_user=Depends(get_current_user),
):
    if scenario_id in _scenarios:
        del _scenarios[scenario_id]
        return {"status": "deleted"}
    return {"detail": "Not found"}


# ── POST /scenarios/compare ──────────────────────────────────────────────────

@router.post("/compare")
async def compare_scenarios(
    scenario_ids: list[int] = Query(...),
    current_user=Depends(get_current_user),
):
    selected = [_scenarios[sid] for sid in scenario_ids if sid in _scenarios]
    if len(selected) < 2:
        return {"scenarios": [], "winner": None, "winner_reason": "Need at least 2 scenarios"}

    comparison_scenarios = []
    best_composite = -1
    winner_name = None
    for s in selected:
        entry = {
            "scenario_name": s["name"],
            "timeline_expected": s["timeline"]["expected_value"],
            "budget_expected": s["budget"]["expected_value"],
            "quality_expected": s["quality_score"],
            "risk_score": s["analysis_data"]["overall_risk_score"],
            "success_probability": round(s["overall_confidence"] / 100, 2),
        }
        comparison_scenarios.append(entry)
        if s["composite_score"] > best_composite:
            best_composite = s["composite_score"]
            winner_name = s["name"]

    return {
        "scenario_count": len(selected),
        "scenarios": comparison_scenarios,
        "winner": winner_name,
        "winner_reason": f"Highest composite score ({best_composite:.0f}/100) with the best balance of cost, time, quality, and risk.",
        "recommendations": [
            f"Consider '{winner_name}' as the primary plan.",
            "Run sensitivity analysis on the top 2 scenarios.",
            "Monitor risk factors closely during execution.",
        ],
    }


# ── POST /scenarios/comparison-table ─────────────────────────────────────────

@router.post("/comparison-table")
async def comparison_table(
    scenario_ids: list[int] = Query(...),
    current_user=Depends(get_current_user),
):
    selected = [_scenarios[sid] for sid in scenario_ids if sid in _scenarios]
    return [
        {
            "name": s["name"],
            "composite_score": s["composite_score"],
            "timeline_days": s["timeline"]["expected_value"],
            "budget_usd": s["budget"]["expected_value"],
            "quality": s["quality_score"],
            "risk": s["analysis_data"]["overall_risk_score"],
        }
        for s in selected
    ]


# ── POST /scenarios/what-if-question ─────────────────────────────────────────

@router.post("/what-if-question")
async def what_if_question(
    body: WhatIfQuestionRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = (await db.execute(select(Task))).scalars().all()
    q = body.question.lower()

    # Parse intent from question
    scope_m = 1.0
    resource_m = 1.0
    if "reduce" in q and "scope" in q:
        scope_m = 0.8
    elif "increase" in q and "scope" in q:
        scope_m = 1.2
    if "increase" in q and "resource" in q:
        resource_m = 1.3
    elif "reduce" in q and "resource" in q:
        resource_m = 0.7

    base_days = max(len(tasks) * 3, 30)
    base_budget = max(len(tasks) * 2000, 20000)
    expected_days = round(base_days * scope_m / resource_m, 1)
    expected_budget = round(base_budget * scope_m, 2)
    quality = round(random.uniform(60, 85), 1)
    risk = round(random.uniform(20, 50), 1)

    insights = [
        f"Scope adjustment ({scope_m:.0%}) impacts timeline proportionally.",
        f"Resource change ({resource_m:.0%}) inversely affects delivery speed.",
        f"Quality score estimated at {quality} based on current team capacity.",
    ]

    return {
        "question": body.question,
        "scenario_analysis": {
            "timeline": {"expected_value": expected_days, "best_case": expected_days * 0.8, "worst_case": expected_days * 1.4},
            "budget": {"expected_value": expected_budget},
            "quality": {"expected_value": quality},
            "overall_risk_score": risk,
        },
        "key_insights": insights,
    }


# ── GET /scenarios/decision-support/{project_id} ────────────────────────────

@router.get("/decision-support/{project_id}")
async def decision_support(
    project_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_scenarios = [s for s in _scenarios.values() if s.get("project_id") == project_id]

    if not project_scenarios:
        return {
            "has_scenarios": False,
            "message": "No scenarios found for this project. Create scenarios first to enable Decision Support.",
        }

    # Find optimal
    optimal = max(project_scenarios, key=lambda s: s["composite_score"])

    optimal_scenario = {
        **optimal,
        "reasoning": f"'{optimal['name']}' scores highest at {optimal['composite_score']:.0f}/100 composite, "
                     f"balancing cost efficiency ({optimal['cost_efficiency']:.0f}), time ({optimal['time_efficiency']:.0f}), "
                     f"quality ({optimal['quality_score']:.0f}), and risk mitigation ({optimal['risk_mitigation']:.0f}).",
    }

    confidence_scores = []
    for s in project_scenarios:
        confidence_scores.append({
            "scenario_id": s["id"],
            "scenario": s["name"],
            "timeline": round(random.uniform(55, 90), 1),
            "budget": round(random.uniform(50, 85), 1),
            "quality": s["quality_score"],
            "risk": s["risk_mitigation"],
            "overall": s["overall_confidence"],
        })

    tradeoff_analysis = []
    for s in project_scenarios:
        tradeoff_analysis.append({
            "scenario_id": s["id"],
            "scenario": s["name"],
            "cost_index": s["cost_efficiency"],
            "time_index": s["time_efficiency"],
            "quality_index": s["quality_score"],
            "risk_index": s["risk_mitigation"],
            "composite_score": s["composite_score"],
            "is_optimal": s["id"] == optimal["id"],
            "expected_timeline_days": s["timeline"]["expected_value"],
            "expected_budget_usd": s["budget"]["expected_value"],
        })

    ai_insights = [
        f"✅ '{optimal['name']}' provides the best overall balance across all dimensions.",
        f"⚠ Scenarios with scope > 1.2x show significantly increased risk scores.",
        "Resource increases yield diminishing returns above 1.5x current capacity.",
        f"Quality focus directly correlates with project success probability.",
    ]

    recommendations = [
        f"Adopt '{optimal['name']}' as the baseline plan.",
        "Create contingency plans for the worst-case timeline scenario.",
        "Allocate budget reserves of 15-20% for risk mitigation.",
        "Schedule monthly scenario reviews to adapt to changing conditions.",
        "Consider hybrid approaches combining elements of top-scoring scenarios.",
    ]

    return {
        "has_scenarios": True,
        "optimal_scenario": optimal_scenario,
        "confidence_scores": confidence_scores,
        "scenarios": project_scenarios,
        "tradeoff_analysis": tradeoff_analysis,
        "ai_insights": ai_insights,
        "recommendations": recommendations,
    }


# ── GET /scenarios/dashboard/sensitivity/{scenario_id} ───────────────────────

@router.get("/dashboard/sensitivity/{scenario_id}")
async def dashboard_sensitivity(
    scenario_id: int,
    current_user=Depends(get_current_user),
):
    s = _scenarios.get(scenario_id)
    if not s:
        return {"detail": "Not found"}

    variables = ["scope", "resources", "quality_focus", "hourly_rate"]
    sensitivity = []
    for v in variables:
        sensitivity.append({
            "variable": v,
            "low": round(s["composite_score"] * random.uniform(0.7, 0.9), 1),
            "base": s["composite_score"],
            "high": round(s["composite_score"] * random.uniform(1.05, 1.2), 1),
        })

    return {"scenario_id": scenario_id, "sensitivity": sensitivity}


# ── GET /scenarios/dashboard/risks/{scenario_id} ─────────────────────────────

@router.get("/dashboard/risks/{scenario_id}")
async def dashboard_risks(
    scenario_id: int,
    current_user=Depends(get_current_user),
):
    s = _scenarios.get(scenario_id)
    if not s:
        return {"detail": "Not found"}

    risks = [
        {"risk": "Scope Creep", "probability": round(random.uniform(0.2, 0.6), 2), "impact": "high", "mitigation": "Strict change control process"},
        {"risk": "Resource Shortage", "probability": round(random.uniform(0.1, 0.4), 2), "impact": "medium", "mitigation": "Cross-training and backup resources"},
        {"risk": "Technical Complexity", "probability": round(random.uniform(0.15, 0.45), 2), "impact": "high", "mitigation": "Proof of concept and early prototyping"},
        {"risk": "Budget Overrun", "probability": round(random.uniform(0.1, 0.35), 2), "impact": "medium", "mitigation": "Regular budget reviews and contingency reserves"},
    ]

    return {"scenario_id": scenario_id, "overall_risk_score": s["analysis_data"]["overall_risk_score"], "risks": risks}
