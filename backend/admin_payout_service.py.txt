"""
Admin Payout Service
Handles manual payout approval and management
"""
import os
import httpx
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")


async def get_pending_payouts() -> List[Dict]:
    """Get all pending payouts (transactions with status='pending')"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={
                    "status": "eq.pending",
                    "select": "*,job:jobs(*),worker:users!transactions_worker_id_fkey(id,name,email),requester:users!transactions_requester_id_fkey(id,name,email)"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return []
                
    except Exception as e:
        print(f"Error fetching pending payouts: {e}")
        return []


async def get_all_payouts(limit: int = 100, offset: int = 0) -> Dict:
    """Get all payouts with pagination"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get total count
            count_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"select": "id"}
            )
            total_count = len(count_response.json()) if count_response.status_code == 200 else 0
            
            # Get paginated results
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={
                    "select": "*,job:jobs(*),worker:users!transactions_worker_id_fkey(id,name,email),requester:users!transactions_requester_id_fkey(id,name,email)",
                    "order": "created_at.desc",
                    "limit": str(limit),
                    "offset": str(offset)
                }
            )
            
            payouts = response.json() if response.status_code == 200 else []
            
            return {
                "payouts": payouts,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
            
    except Exception as e:
        print(f"Error fetching payouts: {e}")
        return {
            "payouts": [],
            "total": 0,
            "limit": limit,
            "offset": offset
        }


async def approve_payout(transaction_id: str, admin_notes: Optional[str] = None) -> Dict:
    """Approve a pending payout"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update transaction status
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"id": f"eq.{transaction_id}"},
                json={
                    "status": "completed",
                    "completed_at": "now()",
                    "admin_notes": admin_notes
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "Payout approved successfully",
                    "transaction_id": transaction_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to approve payout: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error approving payout: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def reject_payout(transaction_id: str, reason: str) -> Dict:
    """Reject a pending payout"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update transaction status
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"id": f"eq.{transaction_id}"},
                json={
                    "status": "failed",
                    "admin_notes": reason
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "Payout rejected",
                    "transaction_id": transaction_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to reject payout: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error rejecting payout: {e}")
        return {
            "success": False,
            "message": str(e)
        }
