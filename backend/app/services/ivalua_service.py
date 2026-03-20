"""
Ivalua Procurement System Integration Service.
Handles purchase requisitions, purchase orders, and vendor management.
"""
import httpx
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class IvaluaIntegrationService:
    """Service for integrating with Ivalua procurement system."""
    
    def __init__(self, base_url: str, api_key: str, tenant_id: str):
        """
        Initialize Ivalua integration service.
        
        Args:
            base_url: Ivalua API base URL
            api_key: API key for authentication
            tenant_id: Tenant/Organization ID
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Tenant-ID": tenant_id
        }
    
    async def create_purchase_requisition(
        self,
        project_id: int,
        task_id: Optional[int],
        items: List[Dict],
        requester_email: str,
        justification: str
    ) -> Dict:
        """
        Create a purchase requisition in Ivalua.
        
        Args:
            project_id: Project ID from PMS
            task_id: Optional task ID from PMS
            items: List of items to purchase
            requester_email: Email of the requester
            justification: Business justification for the purchase
            
        Returns:
            Dict containing PR number and status
        """
        try:
            payload = {
                "requisitionHeader": {
                    "requisitionType": "STANDARD",
                    "requesterEmail": requester_email,
                    "deliveryDate": datetime.now().isoformat(),
                    "currency": "AED",
                    "justification": justification,
                    "customFields": {
                        "projectId": str(project_id),
                        "taskId": str(task_id) if task_id else None,
                        "sourceSystem": "PMS"
                    }
                },
                "requisitionLines": [
                    {
                        "lineNumber": idx + 1,
                        "description": item.get("description"),
                        "quantity": item.get("quantity", 1),
                        "unitPrice": item.get("unit_price", 0),
                        "totalPrice": item.get("quantity", 1) * item.get("unit_price", 0),
                        "categoryCode": item.get("category_code"),
                        "requestedDeliveryDate": item.get("delivery_date"),
                        "glAccount": item.get("gl_account")
                    }
                    for idx, item in enumerate(items)
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/requisitions",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                logger.info(f"Created PR in Ivalua: {data.get('requisitionNumber')}")
                
                return {
                    "success": True,
                    "pr_number": data.get("requisitionNumber"),
                    "pr_id": data.get("requisitionId"),
                    "status": data.get("status"),
                    "total_amount": data.get("totalAmount"),
                    "message": "Purchase requisition created successfully"
                }
                
        except httpx.HTTPError as e:
            logger.error(f"Ivalua API error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to create purchase requisition"
            }
    
    async def get_purchase_order_status(self, po_number: str) -> Dict:
        """
        Get status of a purchase order from Ivalua.
        
        Args:
            po_number: Purchase order number
            
        Returns:
            Dict containing PO status and details
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/purchase-orders/{po_number}",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                
                return {
                    "success": True,
                    "po_number": data.get("poNumber"),
                    "status": data.get("status"),
                    "vendor_name": data.get("vendor", {}).get("name"),
                    "total_amount": data.get("totalAmount"),
                    "currency": data.get("currency"),
                    "created_date": data.get("createdDate"),
                    "expected_delivery": data.get("expectedDeliveryDate"),
                    "lines": data.get("poLines", [])
                }
                
        except httpx.HTTPError as e:
            logger.error(f"Ivalua API error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to retrieve PO {po_number}"
            }
    
    async def get_project_purchase_orders(self, project_id: int) -> List[Dict]:
        """
        Get all purchase orders linked to a project.
        
        Args:
            project_id: Project ID from PMS
            
        Returns:
            List of purchase orders
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/purchase-orders",
                    params={"customField.projectId": str(project_id)},
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                pos = data.get("purchaseOrders", [])
                
                return [
                    {
                        "po_number": po.get("poNumber"),
                        "status": po.get("status"),
                        "vendor_name": po.get("vendor", {}).get("name"),
                        "total_amount": po.get("totalAmount"),
                        "currency": po.get("currency"),
                        "created_date": po.get("createdDate")
                    }
                    for po in pos
                ]
                
        except httpx.HTTPError as e:
            logger.error(f"Ivalua API error: {str(e)}")
            return []
    
    async def get_vendor_performance(self, vendor_code: str) -> Dict:
        """
        Get vendor performance metrics from Ivalua.
        
        Args:
            vendor_code: Vendor code/ID
            
        Returns:
            Dict containing vendor performance data
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/vendors/{vendor_code}/performance",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                
                return {
                    "success": True,
                    "vendor_code": vendor_code,
                    "vendor_name": data.get("vendorName"),
                    "on_time_delivery_rate": data.get("onTimeDeliveryRate"),
                    "quality_rating": data.get("qualityRating"),
                    "total_orders": data.get("totalOrders"),
                    "total_spend": data.get("totalSpend"),
                    "average_lead_time_days": data.get("averageLeadTime")
                }
                
        except httpx.HTTPError as e:
            logger.error(f"Ivalua API error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def link_po_to_task(self, po_number: str, project_id: int, task_id: int) -> Dict:
        """
        Link an existing PO to a project task.
        
        Args:
            po_number: Purchase order number
            project_id: Project ID
            task_id: Task ID
            
        Returns:
            Dict with operation result
        """
        try:
            payload = {
                "customFields": {
                    "projectId": str(project_id),
                    "taskId": str(task_id),
                    "sourceSystem": "PMS"
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{self.base_url}/api/v1/purchase-orders/{po_number}",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                return {
                    "success": True,
                    "message": f"PO {po_number} linked to task {task_id}"
                }
                
        except httpx.HTTPError as e:
            logger.error(f"Ivalua API error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance (configure via environment variables)
def get_ivalua_service() -> IvaluaIntegrationService:
    """Get configured Ivalua service instance."""
    import os
    
    base_url = os.getenv("IVALUA_BASE_URL", "https://api.ivalua.com")
    api_key = os.getenv("IVALUA_API_KEY", "")
    tenant_id = os.getenv("IVALUA_TENANT_ID", "MOF-UAE")
    
    return IvaluaIntegrationService(base_url, api_key, tenant_id)
