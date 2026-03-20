"""
Federal Financial Management System (FMIS) Integration Service.
Handles budget import/export, GL code validation, and financial reconciliation.
"""
import httpx
import csv
import io
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FMISIntegrationService:
    """Service for integrating with the Federal Financial Management System (FMIS)."""

    def __init__(self, base_url: str, api_key: str, org_code: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.org_code = org_code
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Org-Code": org_code,
        }

    # -------------------------------------------------------------------------
    # Budget Import
    # -------------------------------------------------------------------------

    async def import_budget_allocations(self, project_id: int, fiscal_year: str) -> Dict:
        """
        Import budget allocations from FMIS for a given project and fiscal year.

        Returns a dict with a list of allocation records keyed by GL code.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/budget-allocations",
                    params={"projectId": str(project_id), "fiscalYear": fiscal_year},
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                allocations = data.get("allocations", [])
                logger.info(
                    f"Imported {len(allocations)} budget allocations from FMIS "
                    f"for project {project_id}, FY {fiscal_year}"
                )

                return {
                    "success": True,
                    "fiscal_year": fiscal_year,
                    "project_id": project_id,
                    "allocations": [
                        {
                            "gl_code": a.get("glCode"),
                            "cost_center": a.get("costCenter"),
                            "description": a.get("description"),
                            "planned_amount": float(a.get("approvedBudget", 0)),
                            "category_type": a.get("categoryType", "other"),
                            "quarter": a.get("quarter"),
                        }
                        for a in allocations
                    ],
                    "total_budget": sum(
                        float(a.get("approvedBudget", 0)) for a in allocations
                    ),
                }
        except httpx.HTTPError as e:
            logger.error(f"FMIS API error (import_budget_allocations): {e}")
            return {"success": False, "error": str(e), "allocations": []}

    # -------------------------------------------------------------------------
    # Cost Export / Reconciliation
    # -------------------------------------------------------------------------

    async def export_project_costs(
        self, project_id: int, transactions: List[Dict]
    ) -> Dict:
        """
        Export project cost transactions to FMIS for reconciliation.

        Each transaction dict should contain: gl_code, cost_center, amount,
        transaction_date, description, reference_number, vendor_name.
        """
        try:
            payload = {
                "sourceSystem": "PMS",
                "projectId": str(project_id),
                "exportDate": datetime.utcnow().isoformat(),
                "transactions": [
                    {
                        "glCode": t.get("gl_code"),
                        "costCenter": t.get("cost_center"),
                        "transactionDate": (
                            t.get("transaction_date").isoformat()
                            if hasattr(t.get("transaction_date"), "isoformat")
                            else str(t.get("transaction_date"))
                        ),
                        "amount": t.get("amount", 0),
                        "description": t.get("description"),
                        "referenceNumber": t.get("reference_number"),
                        "vendorName": t.get("vendor_name"),
                    }
                    for t in transactions
                ],
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/cost-exports",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                logger.info(
                    f"Exported {len(transactions)} transactions to FMIS "
                    f"for project {project_id}"
                )

                return {
                    "success": True,
                    "export_id": data.get("exportId"),
                    "status": data.get("status"),
                    "records_exported": len(transactions),
                    "message": "Project costs exported successfully",
                }
        except httpx.HTTPError as e:
            logger.error(f"FMIS API error (export_project_costs): {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Budget vs. Actual (real-time)
    # -------------------------------------------------------------------------

    async def get_budget_vs_actual(self, project_id: int, fiscal_year: str) -> Dict:
        """
        Retrieve real-time budget vs. actual comparison from FMIS.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/budget-actuals",
                    params={"projectId": str(project_id), "fiscalYear": fiscal_year},
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "project_id": project_id,
                    "fiscal_year": fiscal_year,
                    "total_budget": float(data.get("totalBudget", 0)),
                    "total_actual": float(data.get("totalActual", 0)),
                    "total_committed": float(data.get("totalCommitted", 0)),
                    "variance": float(data.get("variance", 0)),
                    "variance_pct": float(data.get("variancePercent", 0)),
                    "line_items": data.get("lineItems", []),
                    "last_sync": data.get("lastSyncDate"),
                }
        except httpx.HTTPError as e:
            logger.error(f"FMIS API error (get_budget_vs_actual): {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # GL Code Validation
    # -------------------------------------------------------------------------

    async def validate_gl_code(self, gl_code: str) -> Dict:
        """Validate a GL code against the FMIS chart of accounts."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/gl-codes/{gl_code}/validate",
                    headers=self.headers,
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "gl_code": gl_code,
                    "is_valid": data.get("isValid", False),
                    "description": data.get("description"),
                    "cost_center": data.get("defaultCostCenter"),
                    "category_type": data.get("categoryType"),
                }
        except httpx.HTTPError as e:
            logger.error(f"FMIS API error (validate_gl_code): {e}")
            return {"success": False, "error": str(e), "is_valid": False}

    # -------------------------------------------------------------------------
    # Journal Entry Creation
    # -------------------------------------------------------------------------

    async def create_journal_entry(
        self,
        project_id: int,
        entries: List[Dict],
        period: str,
        description: str,
    ) -> Dict:
        """
        Create automated journal entries in FMIS for month-end close.

        Each entry dict: gl_code, cost_center, debit, credit, description.
        """
        try:
            payload = {
                "journalType": "PROJECT_COST",
                "period": period,
                "description": description,
                "sourceSystem": "PMS",
                "projectId": str(project_id),
                "lines": [
                    {
                        "glCode": e.get("gl_code"),
                        "costCenter": e.get("cost_center"),
                        "debit": e.get("debit", 0),
                        "credit": e.get("credit", 0),
                        "lineDescription": e.get("description"),
                    }
                    for e in entries
                ],
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/journal-entries",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "success": True,
                    "journal_id": data.get("journalId"),
                    "status": data.get("status"),
                    "message": "Journal entry created successfully",
                }
        except httpx.HTTPError as e:
            logger.error(f"FMIS API error (create_journal_entry): {e}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------------------------------
    # Mock / Fallback (when FMIS is unavailable)
    # -------------------------------------------------------------------------

    def get_mock_budget_allocations(self, project_id: int, fiscal_year: str) -> Dict:
        """Return mock FMIS data for development/demo when FMIS is unreachable."""
        mock_allocs = [
            {
                "gl_code": "5001",
                "cost_center": "CC-001",
                "description": "Personnel Costs",
                "planned_amount": 250000.0,
                "category_type": "labor",
                "quarter": "Q1",
            },
            {
                "gl_code": "5002",
                "cost_center": "CC-001",
                "description": "Materials & Supplies",
                "planned_amount": 75000.0,
                "category_type": "materials",
                "quarter": "Q1",
            },
            {
                "gl_code": "5003",
                "cost_center": "CC-002",
                "description": "Professional Services",
                "planned_amount": 120000.0,
                "category_type": "services",
                "quarter": "Q2",
            },
            {
                "gl_code": "5004",
                "cost_center": "CC-002",
                "description": "Software Licenses",
                "planned_amount": 30000.0,
                "category_type": "services",
                "quarter": "Q2",
            },
        ]
        return {
            "success": True,
            "fiscal_year": fiscal_year,
            "project_id": project_id,
            "allocations": mock_allocs,
            "total_budget": sum(a["planned_amount"] for a in mock_allocs),
            "source": "mock",
        }


def get_fmis_service() -> FMISIntegrationService:
    """Get configured FMIS service instance from environment variables."""
    import os

    base_url = os.getenv("FMIS_BASE_URL", "https://fmis.gov.ae/api")
    api_key = os.getenv("FMIS_API_KEY", "")
    org_code = os.getenv("FMIS_ORG_CODE", "MOF-UAE")

    return FMISIntegrationService(base_url, api_key, org_code)
