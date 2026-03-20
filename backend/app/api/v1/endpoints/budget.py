from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.models import (
    BudgetCategory, BudgetItem, BudgetTransaction, 
    CashFlowProjection, Project, Task
)
from app.schemas.schemas import (
    BudgetCategoryCreate, BudgetCategoryResponse,
    BudgetItemCreate, BudgetItemUpdate, BudgetItemResponse,
    BudgetTransactionCreate, BudgetTransactionResponse,
    CashFlowProjectionResponse, BudgetSummary
)
from app.services.fmis_service import get_fmis_service
from app.services.ivalua_service import get_ivalua_service

router = APIRouter()


# Budget Categories
@router.post("/categories", response_model=BudgetCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_category(
    category: BudgetCategoryCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new budget category"""
    db_category = BudgetCategory(**category.dict())
    db.add(db_category)
    await db.commit()
    await db.refresh(db_category)
    return db_category


@router.get("/categories", response_model=List[BudgetCategoryResponse])
async def get_budget_categories(
    is_active: bool = Query(True),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all budget categories"""
    query = select(BudgetCategory)
    if is_active is not None:
        query = query.where(BudgetCategory.is_active == is_active)
    
    result = await db.execute(query)
    categories = result.scalars().all()
    return categories


# Budget Items
@router.post("/items", response_model=BudgetItemResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_item(
    item: BudgetItemCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a new budget item"""
    # Verify project exists
    project_query = select(Project).where(Project.id == item.project_id)
    result = await db.execute(project_query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    db_item = BudgetItem(**item.dict())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.get("/items", response_model=List[BudgetItemResponse])
async def get_budget_items(
    project_id: int = Query(None),
    category_id: int = Query(None),
    status: str = Query(None),
    fiscal_year: str = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get budget items with filters"""
    query = select(BudgetItem)
    
    if project_id:
        query = query.where(BudgetItem.project_id == project_id)
    if category_id:
        query = query.where(BudgetItem.category_id == category_id)
    if status:
        query = query.where(BudgetItem.status == status)
    if fiscal_year:
        query = query.where(BudgetItem.fiscal_year == fiscal_year)
    
    result = await db.execute(query)
    items = result.scalars().all()
    return items


@router.get("/items/{item_id}", response_model=BudgetItemResponse)
async def get_budget_item(
    item_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific budget item"""
    query = select(BudgetItem).where(BudgetItem.id == item_id)
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget item not found"
        )
    
    return item


@router.put("/items/{item_id}", response_model=BudgetItemResponse)
async def update_budget_item(
    item_id: int,
    item_update: BudgetItemUpdate,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Update a budget item"""
    query = select(BudgetItem).where(BudgetItem.id == item_id)
    result = await db.execute(query)
    db_item = result.scalar_one_or_none()
    
    if not db_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget item not found"
        )
    
    # Update fields
    update_data = item_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)
    
    # Recalculate variance
    if 'planned_amount' in update_data or 'actual_amount' in update_data:
        db_item.variance = db_item.actual_amount - db_item.planned_amount
        if db_item.planned_amount > 0:
            db_item.variance_percentage = (db_item.variance / db_item.planned_amount) * 100
    
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_item(
    item_id: int,
    current_user: dict = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db)
):
    """Delete a budget item"""
    query = select(BudgetItem).where(BudgetItem.id == item_id)
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget item not found"
        )
    
    await db.delete(item)
    await db.commit()


# Budget Transactions
@router.post("/transactions", response_model=BudgetTransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_budget_transaction(
    transaction: BudgetTransactionCreate,
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db)
):
    """Create a budget transaction"""
    db_transaction = BudgetTransaction(
        **transaction.dict(),
        created_by=current_user.id
    )
    
    db.add(db_transaction)
    
    # Update budget item actual amount
    item_query = select(BudgetItem).where(BudgetItem.id == transaction.budget_item_id)
    result = await db.execute(item_query)
    budget_item = result.scalar_one_or_none()
    
    if budget_item:
        if transaction.transaction_type == "expense":
            budget_item.actual_amount += transaction.amount
        elif transaction.transaction_type == "commitment":
            budget_item.committed_amount += transaction.amount
        elif transaction.transaction_type == "refund":
            budget_item.actual_amount -= transaction.amount
        
        # Recalculate variance
        budget_item.variance = budget_item.actual_amount - budget_item.planned_amount
        if budget_item.planned_amount > 0:
            budget_item.variance_percentage = (budget_item.variance / budget_item.planned_amount) * 100
    
    await db.commit()
    await db.refresh(db_transaction)
    return db_transaction


@router.get("/transactions", response_model=List[BudgetTransactionResponse])
async def get_budget_transactions(
    budget_item_id: int = Query(None),
    transaction_type: str = Query(None),
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get budget transactions with filters"""
    query = select(BudgetTransaction)
    
    if budget_item_id:
        query = query.where(BudgetTransaction.budget_item_id == budget_item_id)
    if transaction_type:
        query = query.where(BudgetTransaction.transaction_type == transaction_type)
    if start_date:
        query = query.where(BudgetTransaction.transaction_date >= start_date)
    if end_date:
        query = query.where(BudgetTransaction.transaction_date <= end_date)
    
    result = await db.execute(query)
    transactions = result.scalars().all()
    return transactions


# Budget Summary & Analytics
@router.get("/summary/{project_id}", response_model=BudgetSummary)
async def get_budget_summary(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get budget summary for a project"""
    query = select(BudgetItem).where(BudgetItem.project_id == project_id)
    result = await db.execute(query)
    items = result.scalars().all()
    
    total_budget = sum(item.planned_amount for item in items)
    total_actual = sum(item.actual_amount for item in items)
    total_committed = sum(item.committed_amount for item in items)
    total_variance = total_actual - total_budget
    variance_percentage = (total_variance / total_budget * 100) if total_budget > 0 else 0
    
    # Category breakdown
    categories_breakdown = []
    category_ids = set(item.category_id for item in items)
    
    for cat_id in category_ids:
        cat_items = [item for item in items if item.category_id == cat_id]
        cat_query = select(BudgetCategory).where(BudgetCategory.id == cat_id)
        cat_result = await db.execute(cat_query)
        category = cat_result.scalar_one_or_none()
        
        if category:
            categories_breakdown.append({
                "category_name": category.name,
                "planned": sum(item.planned_amount for item in cat_items),
                "actual": sum(item.actual_amount for item in cat_items),
                "variance": sum(item.variance for item in cat_items)
            })
    
    return BudgetSummary(
        total_budget=total_budget,
        total_actual=total_actual,
        total_committed=total_committed,
        total_variance=total_variance,
        variance_percentage=variance_percentage,
        budget_items_count=len(items),
        categories_breakdown=categories_breakdown
    )


# Cash Flow Projections
@router.get("/cash-flow/{project_id}", response_model=List[CashFlowProjectionResponse])
async def get_cash_flow_projections(
    project_id: int,
    start_date: datetime = Query(None),
    end_date: datetime = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get cash flow projections for a project"""
    query = select(CashFlowProjection).where(CashFlowProjection.project_id == project_id)
    
    if start_date:
        query = query.where(CashFlowProjection.period >= start_date)
    if end_date:
        query = query.where(CashFlowProjection.period <= end_date)
    
    query = query.order_by(CashFlowProjection.period)
    result = await db.execute(query)
    projections = result.scalars().all()
    return projections


@router.post("/cash-flow/{project_id}/generate")
async def generate_cash_flow_projections(
    project_id: int,
    months_ahead: int = Query(6, ge=1, le=24, description="Number of months to project forward"),
    current_user: dict = Depends(require_role("Admin", "Project Manager")),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Auto-generate monthly cash flow projections for a project based on current
    budget items, actual spend, and remaining budget distribution.
    Replaces any existing future projections for the project.
    """
    # Get project
    proj_q = select(Project).where(Project.id == project_id)
    proj_r = await db.execute(proj_q)
    project = proj_r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get all budget items
    items_q = select(BudgetItem).where(BudgetItem.project_id == project_id)
    items_r = await db.execute(items_q)
    items = items_r.scalars().all()

    bac = sum(i.planned_amount for i in items)
    total_actual = sum(i.actual_amount for i in items)
    remaining_budget = max(0.0, bac - total_actual)

    # Delete existing future projections
    now = datetime.utcnow()
    del_q = select(CashFlowProjection).where(
        CashFlowProjection.project_id == project_id,
        CashFlowProjection.period >= now,
    )
    del_r = await db.execute(del_q)
    for old in del_r.scalars().all():
        await db.delete(old)

    # Distribute remaining budget evenly across months_ahead
    monthly_outflow = remaining_budget / months_ahead if months_ahead > 0 else 0
    cumulative = 0.0
    created_projections = []

    for i in range(1, months_ahead + 1):
        # Step to next month
        month_date = datetime(now.year + (now.month + i - 1) // 12,
                              (now.month + i - 1) % 12 + 1, 1)
        net = -monthly_outflow  # outflow is negative
        cumulative += net
        proj = CashFlowProjection(
            project_id=project_id,
            period=month_date,
            projected_inflow=0.0,
            projected_outflow=monthly_outflow,
            net_cash_flow=net,
            cumulative_cash_flow=cumulative,
            confidence_level=max(10.0, 90.0 - (i * 5)),  # confidence decays over time
            notes=f"Auto-generated projection for {month_date.strftime('%B %Y')}",
        )
        db.add(proj)
        created_projections.append({
            "period": month_date.isoformat(),
            "projected_outflow": monthly_outflow,
            "net_cash_flow": net,
            "cumulative_cash_flow": cumulative,
        })

    await db.commit()
    return {
        "success": True,
        "project_id": project_id,
        "months_generated": months_ahead,
        "total_remaining_budget": remaining_budget,
        "monthly_outflow": monthly_outflow,
        "projections": created_projections,
    }


# ============================================================
# EVM Metrics
# ============================================================

@router.get("/evm/{project_id}")
async def get_evm_metrics(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Compute Earned Value Management (EVM) metrics in real-time:
      BAC, EV, PV, AC, SV, CV, SPI, CPI, EAC, ETC, TCPI, VAC

    Percent complete  = project.progress  (0-100)
    Percent scheduled = elapsed_days / total_duration_days  (from start/end dates)
    BAC               = sum of planned_amount from BudgetItems
    AC                = sum of actual_amount from BudgetItems
    """
    # Fetch project
    proj_q = select(Project).where(Project.id == project_id)
    proj_r = await db.execute(proj_q)
    project = proj_r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch budget items
    items_q = select(BudgetItem).where(BudgetItem.project_id == project_id)
    items_r = await db.execute(items_q)
    items = items_r.scalars().all()

    bac = sum(i.planned_amount for i in items)
    ac = sum(i.actual_amount for i in items)
    committed = sum(i.committed_amount for i in items)

    # Percent complete from project progress field
    percent_complete = float(project.progress or 0) / 100.0

    # Percent scheduled based on timeline
    now = datetime.utcnow()
    if project.start_date and project.end_date:
        sd = project.start_date.replace(tzinfo=None) if project.start_date.tzinfo else project.start_date
        ed = project.end_date.replace(tzinfo=None) if project.end_date.tzinfo else project.end_date
        total_days = max(1, (ed - sd).days)
        elapsed_days = max(0, (now - sd).days)
        percent_scheduled = min(1.0, elapsed_days / total_days)
    else:
        percent_scheduled = percent_complete  # fallback

    # Core EVM calculations
    ev = percent_complete * bac
    pv = percent_scheduled * bac

    sv = ev - pv                                        # Schedule Variance
    cv = ev - ac                                        # Cost Variance
    spi = (ev / pv) if pv > 0 else 1.0                # Schedule Performance Index
    cpi = (ev / ac) if ac > 0 else 1.0                # Cost Performance Index
    eac = (bac / cpi) if cpi > 0 else bac             # Estimate at Completion
    etc = max(0.0, eac - ac)                           # Estimate to Complete
    vac = bac - eac                                    # Variance at Completion
    tcpi = ((bac - ev) / (bac - ac)) if (bac - ac) > 0 else 1.0  # To-Complete PI

    # Burn rate = daily spend rate
    if project.start_date:
        sd_naive = project.start_date.replace(tzinfo=None)
        elapsed = max(1, (now - sd_naive).days)
    else:
        elapsed = 30
    daily_burn_rate = ac / elapsed
    weekly_burn_rate = daily_burn_rate * 7
    monthly_burn_rate = daily_burn_rate * 30

    # Task-based completion cross-check
    tasks_q = select(Task).where(Task.project_id == project_id)
    tasks_r = await db.execute(tasks_q)
    tasks = tasks_r.scalars().all()
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status == "done")
    task_completion_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return {
        "project_id": project_id,
        "project_name": project.name,
        "calculated_at": now.isoformat(),
        # Core EVM
        "bac": round(bac, 2),
        "ev": round(ev, 2),
        "pv": round(pv, 2),
        "ac": round(ac, 2),
        "sv": round(sv, 2),
        "cv": round(cv, 2),
        "spi": round(spi, 4),
        "cpi": round(cpi, 4),
        "eac": round(eac, 2),
        "etc": round(etc, 2),
        "vac": round(vac, 2),
        "tcpi": round(tcpi, 4),
        # Derived
        "percent_complete": round(percent_complete * 100, 1),
        "percent_scheduled": round(percent_scheduled * 100, 1),
        "committed_amount": round(committed, 2),
        # Burn rate
        "daily_burn_rate": round(daily_burn_rate, 2),
        "weekly_burn_rate": round(weekly_burn_rate, 2),
        "monthly_burn_rate": round(monthly_burn_rate, 2),
        # Status flags
        "is_over_budget": cpi < 1.0,
        "is_behind_schedule": spi < 1.0,
        "budget_health": "critical" if cpi < 0.8 else "warning" if cpi < 1.0 else "good",
        "schedule_health": "critical" if spi < 0.8 else "warning" if spi < 1.0 else "good",
        # Task stats
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "task_completion_pct": round(task_completion_pct, 1),
    }


# ============================================================
# Tableau Export
# ============================================================

@router.get("/export/tableau/{project_id}")
async def export_tableau(
    project_id: int,
    format: str = Query("json", regex="^(json|csv)$", description="json or csv"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Export all budget and financial data for a project in Tableau-compatible format.
    Returns a flat list of records suitable for Tableau Web Data Connector or direct import.
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io

    # Fetch project
    proj_q = select(Project).where(Project.id == project_id)
    proj_r = await db.execute(proj_q)
    project = proj_r.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch budget items with categories
    items_q = select(BudgetItem).where(BudgetItem.project_id == project_id)
    items_r = await db.execute(items_q)
    items = items_r.scalars().all()

    cat_map: Dict[int, str] = {}
    for item in items:
        if item.category_id and item.category_id not in cat_map:
            cat_q = select(BudgetCategory).where(BudgetCategory.id == item.category_id)
            cat_r = await db.execute(cat_q)
            cat = cat_r.scalar_one_or_none()
            if cat:
                cat_map[item.category_id] = cat.name

    # Fetch transactions
    tx_rows = []
    for item in items:
        tx_q = select(BudgetTransaction).where(BudgetTransaction.budget_item_id == item.id)
        tx_r = await db.execute(tx_q)
        for tx in tx_r.scalars().all():
            tx_rows.append({
                "project_id": project_id,
                "project_name": project.name,
                "budget_item_id": item.id,
                "budget_item_description": item.description,
                "category_name": cat_map.get(item.category_id, ""),
                "gl_code": item.gl_code or "",
                "cost_center": item.cost_center or "",
                "planned_amount": item.planned_amount,
                "actual_amount": item.actual_amount,
                "committed_amount": item.committed_amount,
                "variance": item.variance,
                "variance_percentage": item.variance_percentage,
                "is_billable": item.is_billable,
                "fiscal_year": item.fiscal_year or "",
                "quarter": item.quarter or "",
                "status": item.status,
                "transaction_id": tx.id,
                "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else "",
                "transaction_type": tx.transaction_type,
                "transaction_amount": tx.amount,
                "transaction_description": tx.description,
                "vendor_name": tx.vendor_name or "",
                "reference_number": tx.reference_number or "",
                "payment_status": tx.payment_status,
            })

    # Also include items that have no transactions
    item_ids_with_tx = {r["budget_item_id"] for r in tx_rows}
    for item in items:
        if item.id not in item_ids_with_tx:
            tx_rows.append({
                "project_id": project_id,
                "project_name": project.name,
                "budget_item_id": item.id,
                "budget_item_description": item.description,
                "category_name": cat_map.get(item.category_id, ""),
                "gl_code": item.gl_code or "",
                "cost_center": item.cost_center or "",
                "planned_amount": item.planned_amount,
                "actual_amount": item.actual_amount,
                "committed_amount": item.committed_amount,
                "variance": item.variance,
                "variance_percentage": item.variance_percentage,
                "is_billable": item.is_billable,
                "fiscal_year": item.fiscal_year or "",
                "quarter": item.quarter or "",
                "status": item.status,
                "transaction_id": None,
                "transaction_date": "",
                "transaction_type": "",
                "transaction_amount": None,
                "transaction_description": "",
                "vendor_name": "",
                "reference_number": "",
                "payment_status": "",
            })

    if format == "csv":
        output = io.StringIO()
        if tx_rows:
            writer = csv.DictWriter(output, fieldnames=list(tx_rows[0].keys()))
            writer.writeheader()
            writer.writerows(tx_rows)
        csv_content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(csv_content.encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=project_{project_id}_budget.csv"},
        )

    return {
        "project_id": project_id,
        "project_name": project.name,
        "exported_at": datetime.utcnow().isoformat(),
        "record_count": len(tx_rows),
        "records": tx_rows,
        "schema": {
            "description": "Tableau-compatible flat record export",
            "dimensions": ["project_name", "category_name", "gl_code", "fiscal_year", "quarter", "status", "transaction_type", "vendor_name"],
            "measures": ["planned_amount", "actual_amount", "committed_amount", "variance", "transaction_amount"],
        },
    }


# ============================================================
# Combined Financial Report (single call for dashboard)
# ============================================================

@router.get("/financial-report/{project_id}")
async def get_financial_report(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Combined financial report: budget summary + EVM + cash flow projections.
    Designed for the financial reporting dashboard to minimise round-trips.
    """
    # Re-use existing helpers by calling them directly
    from fastapi import Request  # dummy import for clarity

    # Budget summary
    items_q = select(BudgetItem).where(BudgetItem.project_id == project_id)
    items_r = await db.execute(items_q)
    items = items_r.scalars().all()

    total_budget = sum(i.planned_amount for i in items)
    total_actual = sum(i.actual_amount for i in items)
    total_committed = sum(i.committed_amount for i in items)

    # Category breakdown
    cat_breakdown: Dict[int, Dict] = {}
    for item in items:
        if item.category_id not in cat_breakdown:
            cat_breakdown[item.category_id] = {"planned": 0.0, "actual": 0.0, "variance": 0.0}
        cat_breakdown[item.category_id]["planned"] += item.planned_amount
        cat_breakdown[item.category_id]["actual"] += item.actual_amount
        cat_breakdown[item.category_id]["variance"] += item.variance

    cat_breakdown_list = []
    for cat_id, vals in cat_breakdown.items():
        cat_q = select(BudgetCategory).where(BudgetCategory.id == cat_id)
        cat_r2 = await db.execute(cat_q)
        cat = cat_r2.scalar_one_or_none()
        cat_breakdown_list.append({
            "category_name": cat.name if cat else f"Category {cat_id}",
            **vals,
        })

    # Cash flow projections
    cf_q = select(CashFlowProjection).where(
        CashFlowProjection.project_id == project_id
    ).order_by(CashFlowProjection.period)
    cf_r = await db.execute(cf_q)
    cash_flow = [
        {
            "period": cf.period.strftime("%b %Y"),
            "projected_outflow": cf.projected_outflow,
            "projected_inflow": cf.projected_inflow,
            "net_cash_flow": cf.net_cash_flow,
            "cumulative_cash_flow": cf.cumulative_cash_flow,
            "confidence_level": cf.confidence_level,
        }
        for cf in cf_r.scalars().all()
    ]

    # Transactions over time (monthly aggregation for burn chart)
    all_tx_q = select(BudgetTransaction).join(
        BudgetItem, BudgetTransaction.budget_item_id == BudgetItem.id
    ).where(BudgetItem.project_id == project_id).order_by(BudgetTransaction.transaction_date)
    all_tx_r = await db.execute(all_tx_q)
    monthly_spend: Dict[str, float] = {}
    for tx in all_tx_r.scalars().all():
        key = tx.transaction_date.strftime("%b %Y") if tx.transaction_date else "Unknown"
        monthly_spend[key] = monthly_spend.get(key, 0.0) + tx.amount

    burn_trend = [{"month": k, "spend": v} for k, v in monthly_spend.items()]

    return {
        "project_id": project_id,
        "budget_summary": {
            "total_budget": total_budget,
            "total_actual": total_actual,
            "total_committed": total_committed,
            "total_variance": total_actual - total_budget,
            "variance_percentage": ((total_actual - total_budget) / total_budget * 100) if total_budget > 0 else 0,
            "burn_rate_pct": (total_actual / total_budget * 100) if total_budget > 0 else 0,
            "categories_breakdown": cat_breakdown_list,
        },
        "cash_flow": cash_flow,
        "burn_trend": burn_trend,
    }


# ============================================================
# FMIS Integration Endpoints
# ============================================================

@router.get("/integrations/fmis/{project_id}/import")
async def fmis_import_budget(
    project_id: int,
    fiscal_year: str = Query(..., description="Fiscal year, e.g. 2026"),
    use_mock: bool = Query(False, description="Use mock data when FMIS is unreachable"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Import budget allocations from FMIS for a project.
    Returns allocation records that can be used to seed BudgetItems.
    """
    fmis = get_fmis_service()
    if use_mock:
        return fmis.get_mock_budget_allocations(project_id, fiscal_year)
    result = await fmis.import_budget_allocations(project_id, fiscal_year)
    if not result["success"]:
        # Fallback to mock when FMIS is not yet configured
        return fmis.get_mock_budget_allocations(project_id, fiscal_year)
    return result


@router.post("/integrations/fmis/{project_id}/sync")
async def fmis_sync_budget(
    project_id: int,
    fiscal_year: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Sync: Import FMIS allocations and create/update BudgetItems in PMS.
    Existing items for the same fiscal_year are updated; new ones are created.
    """
    fmis = get_fmis_service()
    import_result = await fmis.import_budget_allocations(project_id, fiscal_year)
    if not import_result["success"]:
        import_result = fmis.get_mock_budget_allocations(project_id, fiscal_year)

    created = 0
    updated = 0

    for alloc in import_result.get("allocations", []):
        gl_code = alloc.get("gl_code")
        # Find matching category
        cat_q = select(BudgetCategory).where(BudgetCategory.category_type == alloc.get("category_type", "other"))
        cat_r = await db.execute(cat_q)
        category = cat_r.scalars().first()

        # Look for an existing BudgetItem with same project+gl_code+fiscal_year
        item_q = select(BudgetItem).where(
            BudgetItem.project_id == project_id,
            BudgetItem.gl_code == gl_code,
            BudgetItem.fiscal_year == fiscal_year,
        )
        item_r = await db.execute(item_q)
        existing = item_r.scalar_one_or_none()

        if existing:
            existing.planned_amount = alloc["planned_amount"]
            existing.variance = existing.actual_amount - existing.planned_amount
            if existing.planned_amount > 0:
                existing.variance_percentage = (existing.variance / existing.planned_amount) * 100
            updated += 1
        else:
            new_item = BudgetItem(
                project_id=project_id,
                category_id=category.id if category else None,
                description=alloc.get("description", "FMIS Import"),
                planned_amount=alloc["planned_amount"],
                gl_code=gl_code,
                cost_center=alloc.get("cost_center"),
                fiscal_year=fiscal_year,
                quarter=alloc.get("quarter"),
                status="approved",
            )
            db.add(new_item)
            created += 1

    await db.commit()
    return {
        "success": True,
        "source": import_result.get("source", "fmis"),
        "fiscal_year": fiscal_year,
        "created": created,
        "updated": updated,
        "total_budget": import_result.get("total_budget", 0),
    }


@router.post("/integrations/fmis/{project_id}/export")
async def fmis_export_costs(
    project_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Export all project transactions to FMIS for reconciliation.
    """
    # Collect all transactions for this project
    items_q = select(BudgetItem).where(BudgetItem.project_id == project_id)
    items_r = await db.execute(items_q)
    items = items_r.scalars().all()

    transactions_payload = []
    for item in items:
        tx_q = select(BudgetTransaction).where(BudgetTransaction.budget_item_id == item.id)
        tx_r = await db.execute(tx_q)
        for tx in tx_r.scalars().all():
            transactions_payload.append({
                "gl_code": item.gl_code,
                "cost_center": item.cost_center,
                "amount": tx.amount,
                "transaction_date": tx.transaction_date,
                "description": tx.description,
                "reference_number": tx.reference_number,
                "vendor_name": tx.vendor_name,
            })

    if not transactions_payload:
        return {"success": True, "records_exported": 0, "message": "No transactions to export"}

    fmis = get_fmis_service()
    return await fmis.export_project_costs(project_id, transactions_payload)


@router.get("/integrations/fmis/{project_id}/validate-gl/{gl_code}")
async def fmis_validate_gl_code(
    project_id: int,
    gl_code: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Validate a GL code against the FMIS chart of accounts."""
    fmis = get_fmis_service()
    return await fmis.validate_gl_code(gl_code)


# ============================================================
# Ivalua Integration Endpoints
# ============================================================

@router.get("/integrations/ivalua/{project_id}/purchase-orders")
async def ivalua_get_purchase_orders(
    project_id: int,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Fetch all purchase orders linked to a project from Ivalua."""
    ivalua = get_ivalua_service()
    return await ivalua.get_project_purchase_orders(project_id)


@router.get("/integrations/ivalua/purchase-orders/{po_number}")
async def ivalua_get_po_status(
    po_number: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get the status and details of a specific purchase order from Ivalua."""
    ivalua = get_ivalua_service()
    result = await ivalua.get_purchase_order_status(po_number)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("message"))
    return result


@router.post("/integrations/ivalua/{project_id}/purchase-requisition")
async def ivalua_create_purchase_requisition(
    project_id: int,
    items: List[Dict[str, Any]],
    justification: str = Query(...),
    task_id: int = Query(None),
    current_user = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a purchase requisition in Ivalua from a PMS project."""
    ivalua = get_ivalua_service()
    requester_email = current_user.email or "pms@system.local"
    result = await ivalua.create_purchase_requisition(
        project_id=project_id,
        task_id=task_id,
        items=items,
        requester_email=requester_email,
        justification=justification,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("message", "Failed to create purchase requisition"),
        )
    return result


@router.patch("/integrations/ivalua/purchase-orders/{po_number}/link")
async def ivalua_link_po_to_task(
    po_number: str,
    project_id: int = Query(...),
    task_id: int = Query(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Link an existing Ivalua PO to a PMS project task."""
    ivalua = get_ivalua_service()
    return await ivalua.link_po_to_task(po_number, project_id, task_id)

