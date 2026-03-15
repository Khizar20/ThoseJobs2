"""
Admin User Service
Handles user management operations (ban, flag, edit)
"""
import os
import httpx
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")


async def get_all_users(limit: int = 100, offset: int = 0, search: Optional[str] = None) -> Dict:
    """Get all users with pagination and optional search"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "select": "id,name,email,role,rating_average,rating_count,created_at,is_verified",
                "order": "created_at.desc",
                "limit": str(limit),
                "offset": str(offset)
            }
            
            # Add search filter if provided
            if search:
                # Note: Supabase doesn't support full-text search directly, 
                # so we'll filter client-side or use ilike
                # For now, we'll get all and filter
                pass
            
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params=params
            )
            
            users = response.json() if response.status_code == 200 else []
            
            # Get total count
            count_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"select": "id"}
            )
            total_count = len(count_response.json()) if count_response.status_code == 200 else 0
            
            # Filter by search term if provided
            if search:
                search_lower = search.lower()
                users = [
                    u for u in users
                    if search_lower in u.get("name", "").lower() or
                       search_lower in u.get("email", "").lower()
                ]
            
            # Get job counts for each user
            for user in users:
                # Get jobs completed as worker
                worker_jobs_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    headers=headers,
                    params={
                        "assigned_worker_id": f"eq.{user['id']}",
                        "status": "eq.completed",
                        "select": "id"
                    }
                )
                user["jobs_completed"] = len(worker_jobs_response.json()) if worker_jobs_response.status_code == 200 else 0
                
                # Get jobs posted as requester
                requester_jobs_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    headers=headers,
                    params={
                        "requester_id": f"eq.{user['id']}",
                        "select": "id"
                    }
                )
                user["jobs_posted"] = len(requester_jobs_response.json()) if requester_jobs_response.status_code == 200 else 0
            
            return {
                "users": users,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
            
    except Exception as e:
        print(f"Error fetching users: {e}")
        return {
            "users": [],
            "total": 0,
            "limit": limit,
            "offset": offset
        }


async def ban_user(user_id: str, reason: str) -> Dict:
    """Ban a user by updating their record"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Update user with ban status
            # We'll store ban info in a JSONB field or use existing fields
            # First, get current user data
            get_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}", "select": "*"}
            )
            
            if get_response.status_code != 200:
                return {
                    "success": False,
                    "message": f"User not found: {get_response.text}"
                }
            
            users = get_response.json()
            if not users:
                return {
                    "success": False,
                    "message": "User not found"
                }
            
            # Check if user is already banned
            current_bio = users[0].get("bio", "") or ""
            if "[BANNED:" in current_bio:
                return {
                    "success": False,
                    "message": "User is already banned"
                }
            
            # Append ban note to bio
            ban_note = f"\n\n[BANNED: {reason} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
            new_bio = current_bio + ban_note
            
            # Update user bio with ban info
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers=headers,
                json={
                    "bio": new_bio
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "User banned successfully",
                    "user_id": user_id
                }
            else:
                error_text = update_response.text
                print(f"Error updating user: {error_text}")
                return {
                    "success": False,
                    "message": f"Failed to ban user: {error_text}"
                }
                
    except Exception as e:
        print(f"Error banning user: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": str(e)
        }


async def flag_user(user_id: str, reason: str, flag_type: str = "low_rating") -> Dict:
    """Flag a user for review"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get current user data
            get_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}", "select": "*"}
            )
            
            if get_response.status_code != 200:
                return {
                    "success": False,
                    "message": f"User not found: {get_response.text}"
                }
            
            users = get_response.json()
            if not users:
                return {
                    "success": False,
                    "message": "User not found"
                }
            
            # Check if user is already flagged
            current_bio = users[0].get("bio", "") or ""
            if "[FLAGGED (" in current_bio:
                return {
                    "success": False,
                    "message": "User is already flagged"
                }
            
            # Append flag note to bio
            flag_note = f"\n\n[FLAGGED ({flag_type}): {reason} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
            new_bio = current_bio + flag_note
            
            # Update user bio with flag info
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers=headers,
                json={
                    "bio": new_bio
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "User flagged successfully",
                    "user_id": user_id,
                    "flag_type": flag_type
                }
            else:
                error_text = update_response.text
                print(f"Error updating user: {error_text}")
                return {
                    "success": False,
                    "message": f"Failed to flag user: {error_text}"
                }
                
    except Exception as e:
        print(f"Error flagging user: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": str(e)
        }


async def unban_user(user_id: str) -> Dict:
    """Unban a user by removing ban status"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get current user data
            get_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}", "select": "*"}
            )
            
            if get_response.status_code != 200:
                return {
                    "success": False,
                    "message": f"User not found: {get_response.text}"
                }
            
            users = get_response.json()
            if not users:
                return {
                    "success": False,
                    "message": "User not found"
                }
            
            # Remove ban note from bio
            current_bio = users[0].get("bio", "") or ""
            if "[BANNED:" not in current_bio:
                return {
                    "success": False,
                    "message": "User is not banned"
                }
            
            # Remove [BANNED: ...] patterns
            import re
            cleaned_bio = re.sub(r'\n\n\[BANNED:.*?\]', '', current_bio)
            
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers=headers,
                json={
                    "bio": cleaned_bio
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "User unbanned successfully",
                    "user_id": user_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to unban user: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error unbanning user: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def unflag_user(user_id: str) -> Dict:
    """Unflag a user by removing flag status"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get current user data
            get_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}", "select": "*"}
            )
            
            if get_response.status_code != 200:
                return {
                    "success": False,
                    "message": f"User not found: {get_response.text}"
                }
            
            users = get_response.json()
            if not users:
                return {
                    "success": False,
                    "message": "User not found"
                }
            
            # Remove flag note from bio
            current_bio = users[0].get("bio", "") or ""
            if "[FLAGGED (" not in current_bio:
                return {
                    "success": False,
                    "message": "User is not flagged"
                }
            
            # Remove [FLAGGED (...)] patterns
            import re
            cleaned_bio = re.sub(r'\n\n\[FLAGGED \(.*?\):.*?\]', '', current_bio)
            
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers=headers,
                json={
                    "bio": cleaned_bio
                }
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "User unflagged successfully",
                    "user_id": user_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to unflag user: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error unflagging user: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def update_user(user_id: str, updates: Dict) -> Dict:
    """Update user information"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Add updated_at timestamp
            updates["updated_at"] = "now()"
            
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}"},
                json=updates
            )
            
            if update_response.status_code in [200, 204]:
                return {
                    "success": True,
                    "message": "User updated successfully",
                    "user_id": user_id
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to update user: {update_response.text}"
                }
                
    except Exception as e:
        print(f"Error updating user: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def get_user_details(user_id: str) -> Optional[Dict]:
    """Get detailed information about a specific user"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"id": f"eq.{user_id}"}
            )
            
            if response.status_code == 200:
                users = response.json()
                if users:
                    user = users[0]
                    
                    # Get user's jobs
                    jobs_response = await client.get(
                        f"{SUPABASE_URL}/rest/v1/jobs",
                        headers=headers,
                        params={
                            "or": f"(requester_id.eq.{user_id},assigned_worker_id.eq.{user_id})",
                            "select": "id,title,status,budget,created_at"
                        }
                    )
                    user["jobs"] = jobs_response.json() if jobs_response.status_code == 200 else []
                    
                    # Get user's ratings
                    ratings_response = await client.get(
                        f"{SUPABASE_URL}/rest/v1/ratings",
                        headers=headers,
                        params={
                            "to_user_id": f"eq.{user_id}",
                            "select": "*"
                        }
                    )
                    user["ratings_received"] = ratings_response.json() if ratings_response.status_code == 200 else []
                    
                    return user
            
            return None
            
    except Exception as e:
        print(f"Error fetching user details: {e}")
        return None
