"""
Admin Dispute Service
Handles dispute resolution for jobs
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


async def get_disputes(status: Optional[str] = None) -> List[Dict]:
    """Get all disputes (jobs with status='disputed')"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            params = {"status": "eq.disputed", "select": "*,requester:users!jobs_requester_id_fkey(id,name,email),worker:users!jobs_assigned_worker_id_fkey(id,name,email)"}
            
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                headers=headers,
                params=params
            )
            
            if response.status_code == 200:
                disputes = response.json()
                
                # Fetch job media for each dispute
                for dispute in disputes:
                    media_response = await client.get(
                        f"{SUPABASE_URL}/rest/v1/job_media",
                        headers=headers,
                        params={"job_id": f"eq.{dispute['id']}"}
                    )
                    dispute["media"] = media_response.json() if media_response.status_code == 200 else []
                
                return disputes
            else:
                return []
                
    except Exception as e:
        print(f"Error fetching disputes: {e}")
        return []


async def resolve_dispute(
    job_id: str,
    resolution: str,
    admin_notes: str,
    favor_requester: bool = False
) -> Dict:
    """
    Resolve a dispute
    
    Args:
        job_id: The job ID in dispute
        resolution: Resolution type ('approve', 'refund', 'partial_refund')
        admin_notes: Admin's notes on the resolution
        favor_requester: If True, favor requester (refund); if False, favor worker (approve)
    """
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update job status based on resolution
            if resolution == "approve":
                new_status = "approved"
            elif resolution == "refund":
                new_status = "cancelled"
            elif resolution == "partial_refund":
                new_status = "cancelled"  # Will handle partial refund separately
            else:
                new_status = "disputed"
            
            # Update job
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/jobs",
                headers=headers,
                params={"id": f"eq.{job_id}"},
                json={
                    "status": new_status,
                    "admin_notes": admin_notes,
                    "updated_at": "now()"
                }
            )
            
            if update_response.status_code in [200, 204]:
                # Create admin action record (if you have an admin_actions table)
                # For now, we'll just return success
                return {
                    "success": True,
                    "message": f"Dispute resolved: {resolution}",
                    "job_id": job_id,
                    "new_status": new_status
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to update job: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error resolving dispute: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def get_dispute_details(job_id: str) -> Optional[Dict]:
    """Get detailed information about a specific dispute"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get job details
            job_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                headers=headers,
                params={
                    "id": f"eq.{job_id}",
                    "select": "*,requester:users!jobs_requester_id_fkey(*),worker:users!jobs_assigned_worker_id_fkey(*)"
                }
            )
            
            if job_response.status_code == 200:
                jobs = job_response.json()
                if not jobs:
                    return None
                
                job = jobs[0]
                
                # Get job media
                media_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/job_media",
                    headers=headers,
                    params={"job_id": f"eq.{job_id}"}
                )
                job["media"] = media_response.json() if media_response.status_code == 200 else []
                
                # Get transaction details if exists
                transaction_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/transactions",
                    headers=headers,
                    params={"job_id": f"eq.{job_id}"}
                )
                job["transaction"] = None
                if transaction_response.status_code == 200:
                    transactions = transaction_response.json()
                    if transactions:
                        job["transaction"] = transactions[0]
                
                return job
            else:
                return None
                
    except Exception as e:
        print(f"Error fetching dispute details: {e}")
        return None
