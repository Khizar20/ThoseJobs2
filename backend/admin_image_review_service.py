"""
Admin Image Review Service
Handles image review queue for job media
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


async def get_flagged_media(requires_review: bool = True) -> List[Dict]:
    """Get all flagged media that requires admin review"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get job media that needs review
            # Note: You may need to add a 'requires_review' column to job_media table
            # For now, we'll get media where ai_verified is false or null
            params = {
                "select": "*,job:jobs(*),worker:users!job_media_worker_id_fkey(id,name,email)",
                "or": "ai_verified.is.null,ai_verified.eq.false"
            }
            
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/job_media",
                headers=headers,
                params=params
            )
            
            if response.status_code == 200:
                media_list = response.json()
                
                # Filter for media that actually needs review
                # You can add additional filtering logic here
                flagged_media = []
                for media in media_list:
                    # Check if job is in submitted or disputed status
                    job = media.get("job", {})
                    job_status = job.get("status", "")
                    
                    if job_status in ["submitted", "disputed"]:
                        flagged_media.append(media)
                
                return flagged_media
            else:
                return []
                
    except Exception as e:
        print(f"Error fetching flagged media: {e}")
        return []


async def approve_media(media_id: str, admin_notes: Optional[str] = None) -> Dict:
    """Approve a media item"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update media as verified
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/job_media",
                headers=headers,
                params={"id": f"eq.{media_id}"},
                json={
                    "ai_verified": True,
                    "ai_verification_result": {
                        "admin_approved": True,
                        "admin_notes": admin_notes,
                        "approved_at": "now()"
                    }
                }
            )
            
            if update_response.status_code in [200, 204]:
                # Check if all media for the job is approved
                media_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/job_media",
                    headers=headers,
                    params={"id": f"eq.{media_id}"}
                )
                
                if media_response.status_code == 200:
                    media_list = media_response.json()
                    if media_list:
                        job_id = media_list[0].get("job_id")
                        
                        # Check all media for this job
                        all_media_response = await client.get(
                            f"{SUPABASE_URL}/rest/v1/job_media",
                            headers=headers,
                            params={"job_id": f"eq.{job_id}"}
                        )
                        
                        if all_media_response.status_code == 200:
                            all_media = all_media_response.json()
                            all_approved = all(
                                m.get("ai_verified", False) for m in all_media
                            )
                            
                            if all_approved:
                                # Update job status to approved
                                await client.patch(
                                    f"{SUPABASE_URL}/rest/v1/jobs",
                                    headers=headers,
                                    params={"id": f"eq.{job_id}"},
                                    json={"status": "approved"}
                                )
                
                return {
                    "success": True,
                    "message": "Media approved successfully",
                    "media_id": media_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to approve media: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error approving media: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def reject_media(media_id: str, reason: str) -> Dict:
    """Reject a media item"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update media as rejected
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/job_media",
                headers=headers,
                params={"id": f"eq.{media_id}"},
                json={
                    "ai_verified": False,
                    "ai_verification_result": {
                        "admin_approved": False,
                        "rejection_reason": reason,
                        "rejected_at": "now()"
                    }
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "Media rejected",
                    "media_id": media_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to reject media: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error rejecting media: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def get_media_details(media_id: str) -> Optional[Dict]:
    """Get detailed information about a specific media item"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/job_media",
                headers=headers,
                params={
                    "id": f"eq.{media_id}",
                    "select": "*,job:jobs(*),worker:users!job_media_worker_id_fkey(*)"
                }
            )
            
            if response.status_code == 200:
                media_list = response.json()
                if media_list:
                    return media_list[0]
            
            return None
            
    except Exception as e:
        print(f"Error fetching media details: {e}")
        return None
