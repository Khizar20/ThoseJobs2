from fastapi import FastAPI, HTTPException, Path, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx
import os
import secrets
import bcrypt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import List, Optional
import math
import stripe
from affiliate_email_service import send_affiliate_approval_email
from admin_metrics_service import get_platform_metrics, get_revenue_metrics
from admin_dispute_service import get_disputes, resolve_dispute, get_dispute_details
from admin_payout_service import get_pending_payouts, get_all_payouts, approve_payout, reject_payout
from admin_user_service import get_all_users, ban_user, flag_user, update_user, get_user_details, unban_user, unflag_user
from admin_transaction_service import get_all_transactions, process_refund, get_transaction_stats
from admin_image_review_service import get_flagged_media, approve_media, reject_media, get_media_details

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyBFw0Qbyq9zTFTd-tUY6dZWTgaQzuU17R8")

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_51SbJ0tIgAKWf1JItBxqUHwForio3iRPliwPCJLtBWBU0K9b6hc6sBkj9paZayUhYPicg8QkZpUzYZQtiNOARVrV800kAVTlmUv")
stripe.api_key = STRIPE_SECRET_KEY

# Security
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)

app = FastAPI()

# CORS middleware for frontend-backend communication
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080,http://127.0.0.1:5173,http://localhost:8081")
ALLOWED_ORIGINS = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class LocationRequest(BaseModel):
    latitude: float
    longitude: float
    radius_km: Optional[float] = 10.0
    service_category: Optional[str] = None

class ProviderIn(BaseModel):
    user_id: str
    name: str
    service_category: str
    bio: Optional[str] = ""
    experience: Optional[str] = ""
    location: Optional[str] = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    profile_image: Optional[str] = ""
    cnic_front: Optional[str] = None
    cnic_back: Optional[str] = None
    is_verified: Optional[bool] = False
    jobs_pricing: Optional[dict] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class ProviderOut(ProviderIn):
    id: str
    rating: Optional[float] = 0
    reviews_count: Optional[int] = 0
    created_at: Optional[str] = None
    distance: Optional[float] = None

class PendingRequestIn(BaseModel):
    user_id: Optional[str] = None  # Made optional since backend will create user
    first_name: str
    last_name: str
    email: str
    phone: str
    service_category: List[str]
    experience: Optional[str] = ""
    location: Optional[str] = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    bio: Optional[str] = ""
    profile_image_url: Optional[str] = ""
    cnic_front_url: Optional[str] = None
    cnic_back_url: Optional[str] = None
    jobs_pricing: Optional[dict] = None

class PendingRequestOut(PendingRequestIn):
    id: str
    status: str = "pending"
    admin_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class PendingRequestOutWithEmail(PendingRequestOut):
    email_data: Optional[dict] = None

class AdminLogin(BaseModel):
    username: str
    password: str

class AdminSession(BaseModel):
    token: str
    expires_at: str
    admin_id: str

class AdminUser(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool
    last_login: Optional[str] = None

class AdminUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

# Authentication functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def generate_token() -> str:
    return secrets.token_urlsafe(32)

# Simple admin token validation - just check if token starts with admin_ prefix
ADMIN_TOKEN_PREFIX = "admin_"

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    
    # Simple token validation - check if it starts with admin_ prefix
    if not token or not token.startswith(ADMIN_TOKEN_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Return a simple admin dict
    return {
        "admin_id": "admin",
        "username": "admin",
        "token": token
    }

# Authentication endpoints
@app.post("/admin/login")
async def admin_login(login_data: AdminLogin):
    # Simple admin login - just check credentials and return a token
    # Default admin credentials: admin / admin123
    if login_data.username == "admin" and login_data.password == "admin123":
        # Generate a simple token
        import secrets
        token = f"admin_{secrets.token_urlsafe(32)}"
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        
        return {
            "token": token,
            "expires_at": expires_at,
            "admin_id": "admin",
            "username": "admin"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

@app.post("/admin/logout")
async def admin_logout(current_admin: dict = Depends(get_current_admin)):
    # Simple logout - just return success
    # Frontend will remove the token from localStorage
    return {"message": "Logged out successfully"}

@app.get("/admin/me", response_model=AdminUser)
async def get_current_admin_info(current_admin: dict = Depends(get_current_admin)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/admin_users",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"id": f"eq.{current_admin['admin_id']}", "select": "*"}
        )
        
        if response.status_code != 200 or not response.json():
            raise HTTPException(status_code=404, detail="Admin user not found")
        
        admin_user = response.json()[0]
        return AdminUser(**admin_user)

@app.put("/admin/me", response_model=AdminUser)
async def update_admin_info(admin_update: AdminUpdate, current_admin: dict = Depends(get_current_admin)):
    print(f"🔍 [ADMIN UPDATE] Starting update for admin_id: {current_admin['admin_id']}")
    print(f"🔍 [ADMIN UPDATE] Received data: {admin_update.dict()}")
    
    async with httpx.AsyncClient() as client:
        # Get current admin info
        print(f"🔍 [ADMIN UPDATE] Fetching current admin data...")
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/admin_users",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"id": f"eq.{current_admin['admin_id']}", "select": "*"}
        )
        
        print(f"🔍 [ADMIN UPDATE] Get response status: {response.status_code}")
        print(f"🔍 [ADMIN UPDATE] Get response text: {response.text}")
        
        if response.status_code != 200 or not response.json():
            print(f"❌ [ADMIN UPDATE] Failed to get current admin data")
            raise HTTPException(status_code=404, detail="Admin user not found")
        
        current_admin_data = response.json()[0]
        print(f"🔍 [ADMIN UPDATE] Current admin data: {current_admin_data}")
        
        update_data = {}
        
        # Update basic fields
        if admin_update.username is not None:
            update_data["username"] = admin_update.username
            print(f"🔍 [ADMIN UPDATE] Adding username update: {admin_update.username}")
        if admin_update.full_name is not None:
            update_data["full_name"] = admin_update.full_name
            print(f"🔍 [ADMIN UPDATE] Adding full_name update: {admin_update.full_name}")
        if admin_update.email is not None:
            update_data["email"] = admin_update.email
            print(f"🔍 [ADMIN UPDATE] Adding email update: {admin_update.email}")
        
        # Handle password change
        if admin_update.current_password and admin_update.new_password:
            print(f"🔍 [ADMIN UPDATE] Password change requested")
            print(f"🔍 [ADMIN UPDATE] Current password provided: {bool(admin_update.current_password)}")
            print(f"🔍 [ADMIN UPDATE] New password provided: {bool(admin_update.new_password)}")
            
            # Verify current password
            print(f"🔍 [ADMIN UPDATE] Verifying current password...")
            password_valid = verify_password(admin_update.current_password, current_admin_data["password_hash"])
            print(f"🔍 [ADMIN UPDATE] Password verification result: {password_valid}")
            
            if not password_valid:
                print(f"❌ [ADMIN UPDATE] Current password verification failed")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect"
                )
            
            # Hash new password
            print(f"🔍 [ADMIN UPDATE] Hashing new password...")
            hashed_password = hash_password(admin_update.new_password)
            update_data["password_hash"] = hashed_password
            print(f"🔍 [ADMIN UPDATE] New password hashed successfully")
        
        print(f"🔍 [ADMIN UPDATE] Final update_data: {update_data}")
        
        if not update_data:
            print(f"🔍 [ADMIN UPDATE] No fields to update")
            # Return current admin data if no updates
            return AdminUser(**current_admin_data)
        
        # Update admin user
        print(f"🔍 [ADMIN UPDATE] Sending PATCH request to update admin...")
        update_response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/admin_users?id=eq.{current_admin['admin_id']}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json"
            },
            json=update_data
        )
        
        print(f"🔍 [ADMIN UPDATE] PATCH response status: {update_response.status_code}")
        print(f"🔍 [ADMIN UPDATE] PATCH response text: {update_response.text}")
        
        if update_response.status_code not in [200, 204]:
            print(f"❌ [ADMIN UPDATE] Failed to update admin information")
            raise HTTPException(status_code=500, detail=f"Failed to update admin information: {update_response.text}")
        
        print(f"✅ [ADMIN UPDATE] Admin update successful (status: {update_response.status_code})")
        
        # Return updated admin info
        print(f"🔍 [ADMIN UPDATE] Fetching updated admin data...")
        updated_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/admin_users",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"id": f"eq.{current_admin['admin_id']}", "select": "*"}
        )
        
        print(f"🔍 [ADMIN UPDATE] Updated response status: {updated_response.status_code}")
        print(f"🔍 [ADMIN UPDATE] Updated response text: {updated_response.text}")
        
        if updated_response.status_code != 200 or not updated_response.json():
            print(f"❌ [ADMIN UPDATE] Failed to get updated admin data")
            raise HTTPException(status_code=500, detail="Failed to retrieve updated admin information")
        
        updated_admin = updated_response.json()[0]
        print(f"✅ [ADMIN UPDATE] Successfully updated admin information")
        return AdminUser(**updated_admin)

# Create a pending request (new provider application)
@app.post("/pending-requests/", response_model=PendingRequestOut)
async def create_pending_request(request: PendingRequestIn):
    try:
        print(f"=== PENDING REQUEST CREATION START ===")
        print(f"Request data: {request.dict()}")
        print(f"SUPABASE_URL: {SUPABASE_URL}")
        print(f"SUPABASE_SERVICE_KEY: {SUPABASE_SERVICE_KEY[:20]}..." if SUPABASE_SERVICE_KEY else "NOT SET")
        
        async with httpx.AsyncClient() as client:
            # Check if user already exists in Supabase Auth
            print(f"Checking if user exists with email: {request.email}")
            
            # Try to get existing user
            print(f"Making request to: {SUPABASE_URL}/auth/v1/admin/users")
            print(f"With params: filter=email.eq.{request.email}")
            
            existing_user_response = await client.get(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                },
                params={"filter": f"email.eq.{request.email}"}
            )
            
            print(f"Existing user response status: {existing_user_response.status_code}")
            print(f"Existing user response headers: {existing_user_response.headers}")
            print(f"Existing user response text: {existing_user_response.text}")
            
            user_id = None
            
            if existing_user_response.status_code == 200:
                response_data = existing_user_response.json()
                print(f"Response data: {response_data}")
                
                # Handle the correct response structure: {"users":[],"aud":"authenticated"}
                existing_users = response_data.get("users", [])
                print(f"Existing users: {existing_users}")
                print(f"Existing users type: {type(existing_users)}")
                print(f"Existing users length: {len(existing_users)}")
                
                if existing_users and len(existing_users) > 0:
                    # User already exists
                    user_id = existing_users[0]["id"]
                    print(f"✅ User already exists in Supabase Auth with ID: {user_id}")
                else:
                    # User doesn't exist, try to create new user
                    print(f"User not found in query, attempting to create new user...")
                    
                    import secrets
                    import string
                    temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                    
                    user_data = {
                        "email": request.email,
                        "password": temp_password,
                        "email_confirm": True
                    }
                    
                    print(f"Creating new Supabase user with email: {request.email}")
                    
                    # Create user in Supabase Auth
                    auth_response = await client.post(
                        f"{SUPABASE_URL}/auth/v1/admin/users",
                        headers={
                            "apikey": SUPABASE_SERVICE_KEY,
                            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                            "Content-Type": "application/json"
                        },
                        json=user_data
                    )
                    
                    print(f"Auth response status: {auth_response.status_code}")
                    print(f"Auth response: {auth_response.text}")
                    
                    if auth_response.status_code == 422 and "email_exists" in auth_response.text:
                        # User already exists but wasn't found by query
                        print(f"User exists but wasn't found by query, using email to get user ID...")
                        
                        # Since the user exists, we can use the email to get their ID
                        # We'll use a different query approach
                        try:
                            # Try to get user by email with a different query
                            user_query_response = await client.get(
                                f"{SUPABASE_URL}/auth/v1/admin/users",
                                headers={
                                    "apikey": SUPABASE_SERVICE_KEY,
                                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                                },
                                params={"email": request.email}
                            )
                            
                            print(f"User query response: {user_query_response.text}")
                            
                            if user_query_response.status_code == 200:
                                user_data = user_query_response.json()
                                if user_data.get("users") and len(user_data["users"]) > 0:
                                    user_id = user_data["users"][0]["id"]
                                    print(f"✅ Found existing user with ID: {user_id}")
                                else:
                                    # If we still can't find the user, we'll need to handle this case
                                    print(f"⚠️ User exists but can't be found by query, proceeding with new user creation...")
                                    # For now, we'll skip this user and create a new one
                                    user_id = None
                            else:
                                print(f"⚠️ Failed to query user, proceeding with new user creation...")
                                user_id = None
                                
                        except Exception as e:
                            print(f"Error in user query: {str(e)}")
                            user_id = None
                    
                    elif auth_response.status_code not in (200, 201):
                        print(f"ERROR: Failed to create Supabase user")
                        print(f"Error response: {auth_response.text}")
                        raise HTTPException(status_code=500, detail=f"Failed to create user account: {auth_response.text}")
                    else:
                        auth_user = auth_response.json()
                        user_id = auth_user["id"]
                        print(f"✅ Created new Supabase user with ID: {user_id}")
            else:
                print(f"ERROR: Failed to check existing user")
                print(f"Error response: {existing_user_response.text}")
                # Fallback: try to create user anyway
                print(f"Falling back to create new user...")
                
                import secrets
                import string
                temp_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                
                user_data = {
                    "email": request.email,
                    "password": temp_password,
                    "email_confirm": True
                }
                
                print(f"Creating new Supabase user with email: {request.email}")
                
                # Create user in Supabase Auth
                auth_response = await client.post(
                    f"{SUPABASE_URL}/auth/v1/admin/users",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=user_data
                )
                
                print(f"Auth response status: {auth_response.status_code}")
                print(f"Auth response: {auth_response.text}")
                
                if auth_response.status_code not in (200, 201):
                    print(f"ERROR: Failed to create Supabase user")
                    print(f"Error response: {auth_response.text}")
                    raise HTTPException(status_code=500, detail=f"Failed to create user account: {auth_response.text}")
                
                auth_user = auth_response.json()
                user_id = auth_user["id"]
                print(f"✅ Created new Supabase user with ID: {user_id}")
            
            if not user_id:
                print(f"⚠️ Could not get or create user ID, proceeding without user_id for now...")
                # We'll proceed without user_id and let the admin handle it later
                user_id = None
            
            # Now create the pending request with the real user_id
            request_data = request.dict()
            request_data["user_id"] = user_id
            print(f"Request data to send: {request_data}")
            
            # Make the request to Supabase
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/pending_requests",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                },
                json=request_data
            )
            
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {response.headers}")
            print(f"Response text: {response.text}")
            
            if response.status_code not in (200, 201):
                print(f"ERROR: Supabase returned status {response.status_code}")
                print(f"Error response: {response.text}")
                raise HTTPException(status_code=500, detail=f"Supabase error: {response.text}")
            
            result = response.json()[0]
            print(f"Successfully created pending request: {result}")
            print(f"=== PENDING REQUEST CREATION END ===")
            return result
            
    except Exception as e:
        print(f"EXCEPTION in create_pending_request: {str(e)}")
        print(f"Exception type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Get all pending requests (for admin panel)
@app.get("/pending-requests/", response_model=List[PendingRequestOut])
async def get_pending_requests(current_admin: dict = Depends(get_current_admin)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/pending_requests",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"select": "*", "order": "created_at.desc"}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=response.text)
        return response.json()

# Get a specific pending request
@app.get("/pending-requests/{request_id}", response_model=PendingRequestOut)
async def get_pending_request(request_id: str = Path(..., description="Request UUID"), current_admin: dict = Depends(get_current_admin)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/pending_requests",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"id": f"eq.{request_id}", "select": "*"}
        )
        if response.status_code != 200 or not response.json():
            raise HTTPException(status_code=404, detail="Pending request not found")
        return response.json()[0]

# Update pending request status (approve/reject)
@app.patch("/pending-requests/{request_id}", response_model=PendingRequestOutWithEmail)
async def update_pending_request(request_id: str, status_update: dict, current_admin: dict = Depends(get_current_admin)):
    try:
        print(f"=== APPROVAL PROCESS START ===")
        print(f"Request ID: {request_id}")
        print(f"Status Update: {status_update}")
        print(f"Admin: {current_admin}")
        
        async with httpx.AsyncClient() as client:
            # First, get the pending request details
            print(f"Fetching pending request details...")
            get_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/pending_requests",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                },
                params={"id": f"eq.{request_id}", "select": "*"}
            )
            
            print(f"Get response status: {get_response.status_code}")
            print(f"Get response: {get_response.text}")
            
            if get_response.status_code != 200 or not get_response.json():
                print(f"ERROR: Pending request not found")
                raise HTTPException(status_code=404, detail="Pending request not found")
            
            pending_request = get_response.json()[0]
            print(f"Found pending request: {pending_request}")
            
            new_status = status_update.get("status")
            print(f"New status: {new_status}")
        
            if new_status == "approved":
                print(f"Processing approval for request...")
                
                # Generate one-time password
                import secrets
                import string
                one_time_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                print(f"Generated password: {one_time_password}")
                
                # Use existing user_id from pending request instead of creating new user
                user_id = pending_request["user_id"]
                print(f"Using existing user ID: {user_id}")
                
                # Update the existing user's password
                user_data = {
                    "password": one_time_password
                }
                
                print(f"Updating user password for user ID: {user_id}")
                
                # Update user password in Supabase Auth
                auth_response = await client.put(
                    f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=user_data
                )
                
                print(f"Auth response status: {auth_response.status_code}")
                print(f"Auth response: {auth_response.text}")
                
                if auth_response.status_code not in (200, 201):
                    print(f"ERROR: Failed to update user password")
                    raise HTTPException(status_code=500, detail="Failed to update user password")
                
                print(f"Successfully updated password for user ID: {user_id}")
                
                # Check if user profile exists in users table, create if not
                print(f"Checking if user profile exists in users table...")
                user_profile_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/users",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                    },
                    params={"id": f"eq.{user_id}", "select": "*"}
                )
                
                if user_profile_response.status_code == 200:
                    existing_user = user_profile_response.json()
                    if not existing_user:
                        # Create user profile in users table
                        print(f"Creating user profile in users table...")
                        user_profile_data = {
                            "id": user_id,
                            "email": pending_request["email"],
                            "name": f"{pending_request['first_name']} {pending_request['last_name']}",
                            "phone": pending_request["phone"],
                            "address": pending_request.get("location", ""),
                            "addresses": [{"label": "Home", "address": pending_request.get("location", ""), "is_default": True}],
                            "preferences": {"notifications": True, "sms_notifications": False},
                            "created_at": datetime.now().isoformat()
                        }
                        
                        user_insert_response = await client.post(
                            f"{SUPABASE_URL}/rest/v1/users",
                            headers={
                                "apikey": SUPABASE_SERVICE_KEY,
                                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                "Content-Type": "application/json",
                                "Prefer": "return=representation"
                            },
                            json=user_profile_data
                        )
                        
                        if user_insert_response.status_code in (200, 201):
                            print(f"✅ Created user profile in users table")
                        else:
                            print(f"⚠️ Failed to create user profile: {user_insert_response.text}")
                    else:
                        print(f"✅ User profile already exists in users table")
                
                # Create provider record
                provider_data = {
                    "user_id": user_id,
                    "name": f"{pending_request['first_name']} {pending_request['last_name']}",
                    "service_category": ",".join(pending_request["service_category"]),
                    "bio": pending_request.get("bio", ""),
                    "experience": pending_request.get("experience", ""),
                    "location": pending_request.get("location", ""),
                    "latitude": pending_request.get("latitude"),
                    "longitude": pending_request.get("longitude"),
                    "profile_image": pending_request.get("profile_image_url", ""),
                    "cnic_front": pending_request.get("cnic_front_url"),
                    "cnic_back": pending_request.get("cnic_back_url"),
                    "is_verified": True,
                    "jobs_pricing": pending_request.get("jobs_pricing", {}),
                    "rating": 0,
                    "reviews_count": 0,
                    "email": pending_request.get("email"),
                    "phone": pending_request.get("phone")
                }
                
                print(f"Creating provider with data: {provider_data}")
                
                # Insert into providers table
                provider_response = await client.post(
                    f"{SUPABASE_URL}/rest/v1/providers",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation"
                    },
                    json=provider_data
                )
                
                print(f"Provider response status: {provider_response.status_code}")
                print(f"Provider response: {provider_response.text}")
                
                if provider_response.status_code not in (200, 201):
                    print(f"ERROR: Failed to create provider record")
                    raise HTTPException(status_code=500, detail="Failed to create provider record")
                
                # Send approval email with credentials
                email_data = {
                    "provider_name": f"{pending_request['first_name']} {pending_request['last_name']}",
                    "provider_email": pending_request["email"],
                    "one_time_password": one_time_password,
                    "login_url": "http://localhost:8080/provider-login",
                    "service_category": ",".join(pending_request["service_category"])
                }
                
                print(f"Email data prepared: {email_data}")
                
                # Call email service (this will be handled by frontend)
                # For now, we'll return the email data to be sent from frontend
                pending_request["email_data"] = email_data
                
                # Delete the pending request after successful provider creation
                print(f"Deleting pending request...")
                delete_response = await client.delete(
                    f"{SUPABASE_URL}/rest/v1/pending_requests?id=eq.{request_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Prefer": "return=representation"
                    }
                )
                
                print(f"Delete response status: {delete_response.status_code}")
                print(f"Delete response: {delete_response.text}")
                
                if delete_response.status_code != 200:
                    print(f"ERROR: Failed to delete approved request")
                    raise HTTPException(status_code=500, detail="Failed to delete approved request")
                
                print(f"=== APPROVAL PROCESS SUCCESSFUL ===")
                # Create response with email data
                response_data = {
                    **pending_request,
                    "email_data": email_data
                }
                print(f"Returning response with email_data: {response_data}")
                return response_data
                
            elif new_status == "rejected":
                # Delete uploaded documents from storage bucket
                documents_to_delete = []
                
                print(f"Original URLs:")
                print(f"Profile: {pending_request.get('profile_image_url')}")
                print(f"CNIC Front: {pending_request.get('cnic_front_url')}")
                print(f"CNIC Back: {pending_request.get('cnic_back_url')}")
                
                if pending_request.get("profile_image_url"):
                    # Extract file path from URL - handle profile folder
                    profile_url = pending_request["profile_image_url"]
                    if "/provider-uploads/" in profile_url:
                        profile_path = profile_url.split("/provider-uploads/")[-1]
                        # Ensure it includes the profile/ folder
                        if not profile_path.startswith("profile/"):
                            profile_path = f"profile/{profile_path}"
                        documents_to_delete.append(profile_path)
                        print(f"Extracted profile path: {profile_path}")
                
                if pending_request.get("cnic_front_url"):
                    # Extract file path from URL - handle cnic/front folder
                    cnic_front_url = pending_request["cnic_front_url"]
                    if "/provider-uploads/" in cnic_front_url:
                        cnic_front_path = cnic_front_url.split("/provider-uploads/")[-1]
                        # Ensure it includes the cnic/front/ folder
                        if not cnic_front_path.startswith("cnic/front/"):
                            cnic_front_path = f"cnic/front/{cnic_front_path}"
                        documents_to_delete.append(cnic_front_path)
                        print(f"Extracted CNIC front path: {cnic_front_path}")
                
                if pending_request.get("cnic_back_url"):
                    # Extract file path from URL - handle cnic/back folder
                    cnic_back_url = pending_request["cnic_back_url"]
                    if "/provider-uploads/" in cnic_back_url:
                        cnic_back_path = cnic_back_url.split("/provider-uploads/")[-1]
                        # Ensure it includes the cnic/back/ folder
                        if not cnic_back_path.startswith("cnic/back/"):
                            cnic_back_path = f"cnic/back/{cnic_back_path}"
                        documents_to_delete.append(cnic_back_path)
                        print(f"Extracted CNIC back path: {cnic_back_path}")
                
                # Delete documents from storage
                print(f"Attempting to delete {len(documents_to_delete)} documents: {documents_to_delete}")
                
                if not documents_to_delete:
                    print("No documents to delete - URLs might be empty or malformed")
                
                for document_path in documents_to_delete:
                    try:
                        delete_url = f"{SUPABASE_URL}/storage/v1/object/provider-uploads/{document_path}"
                        print(f"Deleting document: {delete_url}")
                        print(f"Document path: {document_path}")
                        
                        storage_response = await client.delete(
                            delete_url,
                            headers={
                                "apikey": SUPABASE_SERVICE_KEY,
                                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                            }
                        )
                        
                        print(f"Delete response status: {storage_response.status_code}")
                        print(f"Delete response text: {storage_response.text}")
                        
                        # Don't fail if document doesn't exist or can't be deleted
                        if storage_response.status_code == 200:
                            print(f"✅ Successfully deleted document: {document_path}")
                        elif storage_response.status_code == 204:
                            print(f"✅ Successfully deleted document: {document_path}")
                        elif storage_response.status_code == 404:
                            print(f"⚠️ Document not found (already deleted?): {document_path}")
                        else:
                            print(f"❌ Failed to delete document {document_path}")
                            print(f"Status: {storage_response.status_code}")
                            print(f"Response: {storage_response.text}")
                    except Exception as e:
                        print(f"❌ Exception while deleting document {document_path}: {str(e)}")
                        print(f"Exception type: {type(e).__name__}")
                
                # Delete the pending request
                delete_response = await client.delete(
                    f"{SUPABASE_URL}/rest/v1/pending_requests?id=eq.{request_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Prefer": "return=representation"
                    }
                )
                
                if delete_response.status_code != 200:
                    raise HTTPException(status_code=404, detail="Failed to delete rejected request")
                
                # Return the deleted request data
                return pending_request
            
            else:
                # For other status updates (like under_review), just update the status
                response = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/pending_requests?id=eq.{request_id}",
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=representation"
                    },
                    json=status_update
                )
                
                if response.status_code != 200 or not response.json():
                    raise HTTPException(status_code=404, detail="Failed to update pending request status")
                
                return response.json()[0]
            
    except Exception as e:
        print(f"EXCEPTION in update_pending_request: {str(e)}")
        print(f"Exception type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Create a provider (existing endpoint for when admin approves)
@app.post("/providers/", response_model=ProviderOut)
async def create_provider(provider: ProviderIn):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/providers",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            },
            json=provider.dict()
        )
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=response.text)
        return response.json()[0]

# Get all providers
@app.get("/providers/", response_model=List[ProviderOut])
async def get_providers(current_admin: dict = Depends(get_current_admin)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/providers",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"select": "*"}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=response.text)
        return response.json()

# Get a provider by id
@app.get("/providers/{provider_id}", response_model=ProviderOut)
async def get_provider(provider_id: str = Path(..., description="Provider UUID")):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/providers",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
            },
            params={"id": f"eq.{provider_id}", "select": "*"}
        )
        if response.status_code != 200 or not response.json():
            raise HTTPException(status_code=404, detail="Provider not found")
        return response.json()[0]

# Update a provider
@app.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, provider: ProviderIn):
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/providers?id=eq.{provider_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            },
            json=provider.dict(exclude_unset=True)
        )
        if response.status_code != 200 or not response.json():
            raise HTTPException(status_code=404, detail="Provider not found or not updated")
        return response.json()[0]

# Delete a provider
@app.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{SUPABASE_URL}/rest/v1/providers?id=eq.{provider_id}",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Prefer": "return=representation"
            }
        )
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Provider not found or not deleted")
        return {"message": "Provider deleted"} 

# Enhanced geocoding function using Google Maps API
async def geocode_address_google(address: str) -> Optional[tuple[float, float]]:
    """Geocode an address using Google Maps API for better accuracy."""
    try:
        print(f"Geocoding address with Google Maps API: {address}")
        
        # Add Pakistan to the address if not present
        search_address = address
        if not address.lower().includes('pakistan'):
            search_address = f"{address}, Pakistan"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": search_address,
                    "key": GOOGLE_MAPS_API_KEY
                }
            )
            
            data = response.json()
            print(f"Google Maps API response: {data}")
            
            if data.get("results") and len(data["results"]) > 0:
                location = data["results"][0]["geometry"]["location"]
                coords = (location["lat"], location["lng"])
                print(f"Geocoding successful: {coords}")
                return coords
            
            # If no results, try with just the city name
            if ',' in address:
                city_name = address.split(',')[0].strip()
                print(f"Trying with city name: {city_name}")
                
                city_response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={
                        "address": f"{city_name}, Pakistan",
                        "key": GOOGLE_MAPS_API_KEY
                    }
                )
                
                city_data = city_response.json()
                if city_data.get("results") and len(city_data["results"]) > 0:
                    location = city_data["results"][0]["geometry"]["location"]
                    coords = (location["lat"], location["lng"])
                    print(f"Geocoding successful with city fallback: {coords}")
                    return coords
            
            print(f"Geocoding failed for address: {address}")
            return None
            
    except Exception as e:
        print(f"Google Maps geocoding error for {address}: {e}")
        return None

# Fallback geocoding function using Pakistani cities database
def geocode_address_fallback(address: str) -> Optional[tuple[float, float]]:
    """Fallback geocoding using Pakistani cities database."""
    try:
        # Pakistani cities with coordinates
        pakistani_cities = {
            'islamabad': (33.6844, 73.0479),
            'rawalpindi': (33.5651, 73.0169),
            'lahore': (31.5204, 74.3587),
            'karachi': (24.8607, 67.0011),
            'peshawar': (34.0150, 71.5249),
            'faisalabad': (31.4167, 73.0892),
            'multan': (30.1575, 71.5249),
            'quetta': (30.1798, 66.9750),
            'sialkot': (32.4927, 74.5314),
            'gujranwala': (32.1619, 74.1883),
            'sargodha': (32.0836, 72.6711),
            'bahawalpur': (29.3956, 71.6722),
            'sukkur': (27.7031, 68.8589),
            'hyderabad': (25.3969, 68.3772),
            'mardan': (34.1979, 72.0497),
            'abbottabad': (34.1463, 73.2117),
            'mirpur': (33.1447, 73.7516),
            'gujrat': (32.5735, 74.0789),
            'sahiwal': (30.6646, 73.1016),
            'okara': (30.8090, 73.4538),
            'wazirabad': (32.4453, 74.1209),
            'dera ghazi khan': (30.0500, 70.6333),
            'sheikhupura': (31.7131, 73.9783),
            'jhelum': (32.9333, 73.7333),
            'khanewal': (30.3000, 71.9333),
            'daska': (32.3242, 74.3500),
            'mianwali': (32.5833, 71.5500),
            'toba tek singh': (30.9700, 72.4800),
            'kabirwala': (30.4061, 71.8667),
            'burewala': (30.1667, 72.6500),
            'bahawalnagar': (29.9983, 73.2527),
            'pakpattan': (30.3411, 73.3861),
            'attock': (33.7667, 72.3667),
            'vihari': (30.0419, 72.3528),
            'kot addu': (30.4700, 70.9644),
        }
        
        # Check if any city name matches
        address_lower = address.lower()
        for city, coords in pakistani_cities.items():
            if city in address_lower:
                print(f"Found city match: {city} -> {coords}")
                return coords
        
        return None
    except Exception as e:
        print(f"Fallback geocoding error for {address}: {e}")
        return None

# Main geocoding function that tries Google Maps API first, then fallback
async def geocode_address_enhanced(address: str) -> Optional[tuple[float, float]]:
    """Enhanced geocoding with Google Maps API and fallback."""
    try:
        # Try Google Maps API first
        coords = await geocode_address_google(address)
        if coords:
            return coords
        
        # If Google Maps fails, try fallback
        print(f"Google Maps failed, trying fallback for: {address}")
        coords = geocode_address_fallback(address)
        if coords:
            return coords
        
        print(f"All geocoding methods failed for: {address}")
        return None
        
    except Exception as e:
        print(f"Enhanced geocoding error for {address}: {e}")
        return None

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    try:
        # Haversine formula
        R = 6371  # Earth's radius in kilometers
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        distance = R * c
        return distance
    except Exception as e:
        print(f"Distance calculation error: {e}")
        return float('inf')

# New endpoint for enhanced geocoding
@app.post("/geocode/address")
async def geocode_address_endpoint(address_request: dict):
    """Enhanced geocoding endpoint with Google Maps API."""
    try:
        address = address_request.get("address", "")
        if not address:
            raise HTTPException(status_code=400, detail="Address is required")
        
        coords = await geocode_address_enhanced(address)
        
        if coords:
            return {
                "success": True,
                "latitude": coords[0],
                "longitude": coords[1],
                "address": address
            }
        else:
            return {
                "success": False,
                "message": "Could not geocode the address",
                "address": address
            }
            
    except Exception as e:
        print(f"Geocoding endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Geocoding failed: {str(e)}")

# Location-based provider search
@app.post("/providers/nearby", response_model=List[ProviderOut])
async def get_nearby_providers(location_request: LocationRequest):
    try:
        print(f"=== NEARBY PROVIDERS SEARCH ===")
        print(f"User location: {location_request.latitude}, {location_request.longitude}")
        print(f"Search radius: {location_request.radius_km}km")
        print(f"Service category: {location_request.service_category}")
        
        async with httpx.AsyncClient() as client:
            # Build query parameters
            params = {
                "select": "*",
                "is_verified": "eq.true"
            }
            
            if location_request.service_category and location_request.service_category != "All Services":
                params["service_category"] = f"ilike.%{location_request.service_category}%"
            
            print(f"Query params: {params}")
            
            # Get all providers
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/providers",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                },
                params=params
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Failed to fetch providers: {response.text}")
            
            providers = response.json()
            print(f"Found {len(providers)} providers")
            
            # Process providers with location data
            nearby_providers = []
            
            for provider in providers:
                provider_lat = provider.get("latitude")
                provider_lon = provider.get("longitude")
                
                # If provider has coordinates, calculate distance
                if provider_lat is not None and provider_lon is not None:
                    distance = calculate_distance(
                        location_request.latitude,
                        location_request.longitude,
                        provider_lat,
                        provider_lon
                    )
                    
                    # Filter by radius
                    if distance <= location_request.radius_km:
                        provider["distance"] = distance
                        nearby_providers.append(provider)
                        print(f"Provider {provider['name']}: {distance:.2f}km away")
                
                # If provider doesn't have coordinates but has location text, try to geocode
                elif provider.get("location"):
                    print(f"Geocoding provider {provider['name']} location: {provider['location']}")
                    coords = await geocode_address_enhanced(provider["location"])
                    
                    if coords:
                        lat, lon = coords
                        distance = calculate_distance(
                            location_request.latitude,
                            location_request.longitude,
                            lat,
                            lon
                        )
                        
                        if distance <= location_request.radius_km:
                            provider["latitude"] = lat
                            provider["longitude"] = lon
                            provider["distance"] = distance
                            nearby_providers.append(provider)
                            print(f"Provider {provider['name']} (geocoded): {distance:.2f}km away")
                            
                            # Update provider record with coordinates
                            try:
                                await client.patch(
                                    f"{SUPABASE_URL}/rest/v1/providers?id=eq.{provider['id']}",
                                    headers={
                                        "apikey": SUPABASE_SERVICE_KEY,
                                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                        "Content-Type": "application/json"
                                    },
                                    json={"latitude": lat, "longitude": lon}
                                )
                                print(f"Updated provider {provider['name']} with coordinates")
                            except Exception as e:
                                print(f"Failed to update provider coordinates: {e}")
            
            # Sort by distance
            nearby_providers.sort(key=lambda x: x.get("distance", float('inf')))
            
            print(f"Returning {len(nearby_providers)} nearby providers")
            print(f"=== NEARBY PROVIDERS SEARCH END ===")
            
            return nearby_providers
            
    except Exception as e:
        print(f"EXCEPTION in get_nearby_providers: {str(e)}")
        print(f"Exception type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Geocode provider location
@app.post("/providers/{provider_id}/geocode")
async def geocode_provider_location(provider_id: str):
    """
    Geocode a provider's location using their address
    """
    try:
        # Get provider data
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{SUPABASE_URL}/rest/v1/providers?id=eq.{provider_id}", 
                                     headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"})
            response.raise_for_status()
            providers = response.json()
            
            if not providers:
                raise HTTPException(status_code=404, detail="Provider not found")
            
            provider = providers[0]
            location = provider.get("location", "")
            
            if not location:
                raise HTTPException(status_code=400, detail="Provider has no location to geocode")
            
            # Geocode the location
            coords = await geocode_address_enhanced(location)
            
            if not coords:
                raise HTTPException(status_code=400, detail="Could not geocode provider location")
            
            lat, lng = coords
            
            # Update provider with coordinates
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/providers?id=eq.{provider_id}",
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"},
                json={"latitude": lat, "longitude": lng}
            )
            update_response.raise_for_status()
            
            return {
                "provider_id": provider_id,
                "location": location,
                "latitude": lat,
                "longitude": lng,
                "message": "Location geocoded successfully"
            }
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STRIPE CONNECT ENDPOINTS
# ============================================

class CreatePaymentIntentRequest(BaseModel):
    jobId: str
    amount: float
    requesterId: str
    workerId: Optional[str] = None

class CreateConnectAccountRequest(BaseModel):
    userId: str
    email: str

class ConnectOnboardingRequest(BaseModel):
    accountId: str

class TransferToWorkerRequest(BaseModel):
    jobId: str
    workerId: str
    amount: float

class ConfirmPaymentIntentRequest(BaseModel):
    paymentIntentId: str

class RefundRequest(BaseModel):
    paymentIntentId: str
    amount: Optional[float] = None

@app.post("/api/stripe/create-payment-intent")
async def create_payment_intent(request: CreatePaymentIntentRequest):
    """
    Create a Payment Intent for a job (escrow)
    Amount should be in dollars, will be converted to cents
    """
    try:
        amount_cents = int(request.amount * 100)  # Convert to cents
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card'],
            capture_method='manual',  # Hold funds until we capture
            metadata={
                'job_id': request.jobId,
                'requester_id': request.requesterId,
                'worker_id': request.workerId or '',
            }
        )
        
        return {
            'clientSecret': payment_intent.client_secret,
            'paymentIntentId': payment_intent.id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/confirm-payment-intent")
async def confirm_payment_intent(request: ConfirmPaymentIntentRequest):
    """
    Capture the payment intent (release funds from escrow)
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Capture the payment
        payment_intent = stripe.PaymentIntent.confirm(request.paymentIntentId)
        
        return {
            'success': True,
            'status': payment_intent.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/create-connect-account")
async def create_connect_account(request: CreateConnectAccountRequest):
    """
    Create a Stripe Connect Express account for a worker
    """
    try:
        # Validate input
        if not request.email or not request.userId:
            raise HTTPException(status_code=400, detail="Email and userId are required")
        
        print(f"Creating Stripe Connect account for user: {request.userId}, email: {request.email}")
        
        account = stripe.Account.create(
            type='express',
            country='US',
            email=request.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
            metadata={
                'user_id': request.userId,
            }
        )
        
        print(f"Stripe account created: {account.id}")
        
        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        print(f"Account link created: {account_link.url}")
        
        return {
            'accountId': account.id,
            'onboardingUrl': account_link.url,
            'detailsSubmitted': account.details_submitted,
            'chargesEnabled': account.charges_enabled,
            'payoutsEnabled': account.payouts_enabled,
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/connect-onboarding-url")
async def get_connect_onboarding_url(request: ConnectOnboardingRequest):
    """
    Get a new onboarding URL for an existing Connect account
    """
    try:
        account_link = stripe.AccountLink.create(
            account=request.accountId,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        return {
            'url': account_link.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stripe/connect-account-status/{user_id}")
async def get_connect_account_status(user_id: str):
    """
    Get the status of a worker's Stripe Connect account
    """
    try:
        # Get user's stripe_account_id from Supabase
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            response.raise_for_status()
            users = response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                return {
                    'accountId': None,
                    'detailsSubmitted': False,
                    'chargesEnabled': False,
                    'payoutsEnabled': False,
                }
            
            account_id = users[0]['stripe_account_id']
            account = stripe.Account.retrieve(account_id)
            
            return {
                'accountId': account.id,
                'detailsSubmitted': account.details_submitted,
                'chargesEnabled': account.charges_enabled,
                'payoutsEnabled': account.payouts_enabled,
            }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/transfer-to-worker")
async def transfer_to_worker(request: TransferToWorkerRequest):
    """
    Transfer funds to worker's Stripe Connect account (70% of job amount)
    """
    try:
        print(f"Transferring ${request.amount} to worker {request.workerId} for job {request.jobId}")
        
        # Get worker's stripe_account_id and job payment_intent_id from Supabase
        async with httpx.AsyncClient() as client:
            # Get worker's stripe_account_id
            worker_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{request.workerId}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            worker_response.raise_for_status()
            users = worker_response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                raise HTTPException(status_code=400, detail="Worker has not set up Stripe Connect account")
            
            account_id = users[0]['stripe_account_id']
            print(f"Worker account ID: {account_id}")
            
            # Get job's payment_intent_id
            job_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{request.jobId}&select=payment_intent_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            job_response.raise_for_status()
            jobs = job_response.json()
            
            payment_intent_id = None
            if jobs and jobs[0].get('payment_intent_id'):
                payment_intent_id = jobs[0]['payment_intent_id']
                print(f"Payment intent ID: {payment_intent_id}")
        
        # Convert amount to cents
        amount_cents = int(request.amount * 100)
        
        # If payment intent exists, capture it first (if using manual capture)
        if payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                print(f"Payment intent status: {payment_intent.status}")
                
                # Capture payment intent if it's in requires_capture status
                if payment_intent.status == 'requires_capture':
                    print("Capturing payment intent...")
                    payment_intent = stripe.PaymentIntent.capture(payment_intent_id)
                    print(f"Payment intent captured: {payment_intent.status}")
                elif payment_intent.status == 'succeeded':
                    print("Payment intent already succeeded")
                else:
                    print(f"Warning: Payment intent status is {payment_intent.status}, may not be ready for transfer")
            except stripe.error.StripeError as e:
                error_msg = f"Could not capture payment intent: {str(e)}"
                print(f"❌ {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)
        
        # Create transfer to worker's Connect account
        print(f"Creating transfer of ${request.amount} ({amount_cents} cents) to {account_id}")
        try:
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency='usd',
                destination=account_id,
                metadata={
                    'job_id': request.jobId,
                    'worker_id': request.workerId,
                }
            )
        except stripe.error.StripeError as e:
            error_msg = f"Stripe transfer error: {str(e)}"
            print(f"❌ {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        print(f"Transfer created: {transfer.id}, status: {transfer.status}")
        
        return {
            'transferId': transfer.id,
            'amount': request.amount,
            'status': transfer.status
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/refund")
async def refund_payment(request: RefundRequest):
    """
    Refund a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Create refund
        refund_params = {
            'payment_intent': request.paymentIntentId,
        }
        if request.amount:
            refund_params['amount'] = int(request.amount * 100)  # Convert to cents
        
        refund = stripe.Refund.create(**refund_params)
        
        return {
            'refundId': refund.id,
            'status': refund.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class GetPaymentMethodRequest(BaseModel):
    paymentIntentId: str

@app.post("/api/stripe/get-payment-method")
async def get_payment_method(request: GetPaymentMethodRequest):
    """
    Get payment method details from a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        if not payment_intent.payment_method:
            raise HTTPException(status_code=404, detail="Payment method not found")
        
        payment_method = stripe.PaymentMethod.retrieve(payment_intent.payment_method)
        
        # Extract card details
        card_info = {}
        if payment_method.card:
            card_info = {
                'brand': payment_method.card.brand,
                'last4': payment_method.card.last4,
                'exp_month': payment_method.card.exp_month,
                'exp_year': payment_method.card.exp_year,
            }
        
        return {
            'id': payment_method.id,
            'type': payment_method.type,
            'card': card_info,
            'created': payment_method.created
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/get-payment-method")
async def get_payment_method(request: GetPaymentMethodRequest):
    """
    Get payment method details from a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        if not payment_intent.payment_method:
            raise HTTPException(status_code=404, detail="Payment method not found")
        
        payment_method = stripe.PaymentMethod.retrieve(payment_intent.payment_method)
        
        # Extract card details
        card_info = {}
        if payment_method.card:
            card_info = {
                'brand': payment_method.card.brand,
                'last4': payment_method.card.last4,
                'exp_month': payment_method.card.exp_month,
                'exp_year': payment_method.card.exp_year,
            }
        
        return {
            'id': payment_method.id,
            'type': payment_method.type,
            'card': card_info,
            'created': payment_method.created
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Google Maps Autocomplete Endpoints
@app.get("/api/google-maps/autocomplete")
async def google_maps_autocomplete(
    input: str,
    types: str = "geocode",
    components: Optional[str] = "country:pk"
):
    """
    Proxy for Google Maps Places Autocomplete API
    """
    try:
        url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
        params = {
            "input": input,
            "types": types,
            "key": GOOGLE_MAPS_API_KEY
        }
        
        if components:
            params["components"] = components
            
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STRIPE CONNECT ENDPOINTS
# ============================================

class CreatePaymentIntentRequest(BaseModel):
    jobId: str
    amount: float
    requesterId: str
    workerId: Optional[str] = None

class CreateConnectAccountRequest(BaseModel):
    userId: str
    email: str

class ConnectOnboardingRequest(BaseModel):
    accountId: str

class TransferToWorkerRequest(BaseModel):
    jobId: str
    workerId: str
    amount: float

class ConfirmPaymentIntentRequest(BaseModel):
    paymentIntentId: str

class RefundRequest(BaseModel):
    paymentIntentId: str
    amount: Optional[float] = None

@app.post("/api/stripe/create-payment-intent")
async def create_payment_intent(request: CreatePaymentIntentRequest):
    """
    Create a Payment Intent for a job (escrow)
    Amount should be in dollars, will be converted to cents
    """
    try:
        amount_cents = int(request.amount * 100)  # Convert to cents
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card'],
            capture_method='manual',  # Hold funds until we capture
            metadata={
                'job_id': request.jobId,
                'requester_id': request.requesterId,
                'worker_id': request.workerId or '',
            }
        )
        
        return {
            'clientSecret': payment_intent.client_secret,
            'paymentIntentId': payment_intent.id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/confirm-payment-intent")
async def confirm_payment_intent(request: ConfirmPaymentIntentRequest):
    """
    Capture the payment intent (release funds from escrow)
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Capture the payment
        payment_intent = stripe.PaymentIntent.confirm(request.paymentIntentId)
        
        return {
            'success': True,
            'status': payment_intent.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/create-connect-account")
async def create_connect_account(request: CreateConnectAccountRequest):
    """
    Create a Stripe Connect Express account for a worker
    """
    try:
        # Validate input
        if not request.email or not request.userId:
            raise HTTPException(status_code=400, detail="Email and userId are required")
        
        print(f"Creating Stripe Connect account for user: {request.userId}, email: {request.email}")
        
        account = stripe.Account.create(
            type='express',
            country='US',
            email=request.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
            metadata={
                'user_id': request.userId,
            }
        )
        
        print(f"Stripe account created: {account.id}")
        
        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        print(f"Account link created: {account_link.url}")
        
        return {
            'accountId': account.id,
            'onboardingUrl': account_link.url,
            'detailsSubmitted': account.details_submitted,
            'chargesEnabled': account.charges_enabled,
            'payoutsEnabled': account.payouts_enabled,
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/connect-onboarding-url")
async def get_connect_onboarding_url(request: ConnectOnboardingRequest):
    """
    Get a new onboarding URL for an existing Connect account
    """
    try:
        account_link = stripe.AccountLink.create(
            account=request.accountId,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        return {
            'url': account_link.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stripe/connect-account-status/{user_id}")
async def get_connect_account_status(user_id: str):
    """
    Get the status of a worker's Stripe Connect account
    """
    try:
        # Get user's stripe_account_id from Supabase
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            response.raise_for_status()
            users = response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                return {
                    'accountId': None,
                    'detailsSubmitted': False,
                    'chargesEnabled': False,
                    'payoutsEnabled': False,
                }
            
            account_id = users[0]['stripe_account_id']
            account = stripe.Account.retrieve(account_id)
            
            return {
                'accountId': account.id,
                'detailsSubmitted': account.details_submitted,
                'chargesEnabled': account.charges_enabled,
                'payoutsEnabled': account.payouts_enabled,
            }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/transfer-to-worker")
async def transfer_to_worker(request: TransferToWorkerRequest):
    """
    Transfer funds to worker's Stripe Connect account (70% of job amount)
    """
    try:
        print(f"Transferring ${request.amount} to worker {request.workerId} for job {request.jobId}")
        
        # Get worker's stripe_account_id and job payment_intent_id from Supabase
        async with httpx.AsyncClient() as client:
            # Get worker's stripe_account_id
            worker_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{request.workerId}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            worker_response.raise_for_status()
            users = worker_response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                raise HTTPException(status_code=400, detail="Worker has not set up Stripe Connect account")
            
            account_id = users[0]['stripe_account_id']
            print(f"Worker account ID: {account_id}")
            
            # Get job's payment_intent_id
            job_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{request.jobId}&select=payment_intent_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            job_response.raise_for_status()
            jobs = job_response.json()
            
            payment_intent_id = None
            if jobs and jobs[0].get('payment_intent_id'):
                payment_intent_id = jobs[0]['payment_intent_id']
                print(f"Payment intent ID: {payment_intent_id}")
        
        # Convert amount to cents
        amount_cents = int(request.amount * 100)
        
        # If payment intent exists, capture it first (if using manual capture)
        if payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                print(f"Payment intent status: {payment_intent.status}")
                
                # Capture payment intent if it's in requires_capture status
                if payment_intent.status == 'requires_capture':
                    print("Capturing payment intent...")
                    payment_intent = stripe.PaymentIntent.capture(payment_intent_id)
                    print(f"Payment intent captured: {payment_intent.status}")
                elif payment_intent.status == 'succeeded':
                    print("Payment intent already succeeded")
                else:
                    print(f"Warning: Payment intent status is {payment_intent.status}, may not be ready for transfer")
            except stripe.error.StripeError as e:
                error_msg = f"Could not capture payment intent: {str(e)}"
                print(f"❌ {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)
        
        # Create transfer to worker's Connect account
        print(f"Creating transfer of ${request.amount} ({amount_cents} cents) to {account_id}")
        try:
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency='usd',
                destination=account_id,
                metadata={
                    'job_id': request.jobId,
                    'worker_id': request.workerId,
                }
            )
        except stripe.error.StripeError as e:
            error_msg = f"Stripe transfer error: {str(e)}"
            print(f"❌ {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        print(f"Transfer created: {transfer.id}, status: {transfer.status}")
        
        return {
            'transferId': transfer.id,
            'amount': request.amount,
            'status': transfer.status
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/refund")
async def refund_payment(request: RefundRequest):
    """
    Refund a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Create refund
        refund_params = {
            'payment_intent': request.paymentIntentId,
        }
        if request.amount:
            refund_params['amount'] = int(request.amount * 100)  # Convert to cents
        
        refund = stripe.Refund.create(**refund_params)
        
        return {
            'refundId': refund.id,
            'status': refund.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/google-maps/place-details")
async def google_maps_place_details(
    place_id: str,
    fields: str = "geometry"
):
    """
    Proxy for Google Maps Place Details API
    """
    try:
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": fields,
            "key": GOOGLE_MAPS_API_KEY
        }
            
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STRIPE CONNECT ENDPOINTS
# ============================================

class CreatePaymentIntentRequest(BaseModel):
    jobId: str
    amount: float
    requesterId: str
    workerId: Optional[str] = None

class CreateConnectAccountRequest(BaseModel):
    userId: str
    email: str

class ConnectOnboardingRequest(BaseModel):
    accountId: str

class TransferToWorkerRequest(BaseModel):
    jobId: str
    workerId: str
    amount: float

class ConfirmPaymentIntentRequest(BaseModel):
    paymentIntentId: str

class RefundRequest(BaseModel):
    paymentIntentId: str
    amount: Optional[float] = None

@app.post("/api/stripe/create-payment-intent")
async def create_payment_intent(request: CreatePaymentIntentRequest):
    """
    Create a Payment Intent for a job (escrow)
    Amount should be in dollars, will be converted to cents
    """
    try:
        amount_cents = int(request.amount * 100)  # Convert to cents
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card'],
            capture_method='manual',  # Hold funds until we capture
            metadata={
                'job_id': request.jobId,
                'requester_id': request.requesterId,
                'worker_id': request.workerId or '',
            }
        )
        
        return {
            'clientSecret': payment_intent.client_secret,
            'paymentIntentId': payment_intent.id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/confirm-payment-intent")
async def confirm_payment_intent(request: ConfirmPaymentIntentRequest):
    """
    Capture the payment intent (release funds from escrow)
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Capture the payment
        payment_intent = stripe.PaymentIntent.confirm(request.paymentIntentId)
        
        return {
            'success': True,
            'status': payment_intent.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/create-connect-account")
async def create_connect_account(request: CreateConnectAccountRequest):
    """
    Create a Stripe Connect Express account for a worker
    """
    try:
        # Validate input
        if not request.email or not request.userId:
            raise HTTPException(status_code=400, detail="Email and userId are required")
        
        print(f"Creating Stripe Connect account for user: {request.userId}, email: {request.email}")
        
        account = stripe.Account.create(
            type='express',
            country='US',
            email=request.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
            metadata={
                'user_id': request.userId,
            }
        )
        
        print(f"Stripe account created: {account.id}")
        
        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        print(f"Account link created: {account_link.url}")
        
        return {
            'accountId': account.id,
            'onboardingUrl': account_link.url,
            'detailsSubmitted': account.details_submitted,
            'chargesEnabled': account.charges_enabled,
            'payoutsEnabled': account.payouts_enabled,
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/connect-onboarding-url")
async def get_connect_onboarding_url(request: ConnectOnboardingRequest):
    """
    Get a new onboarding URL for an existing Connect account
    """
    try:
        account_link = stripe.AccountLink.create(
            account=request.accountId,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        return {
            'url': account_link.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stripe/connect-account-status/{user_id}")
async def get_connect_account_status(user_id: str):
    """
    Get the status of a worker's Stripe Connect account
    """
    try:
        # Get user's stripe_account_id from Supabase
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            response.raise_for_status()
            users = response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                return {
                    'accountId': None,
                    'detailsSubmitted': False,
                    'chargesEnabled': False,
                    'payoutsEnabled': False,
                }
            
            account_id = users[0]['stripe_account_id']
            account = stripe.Account.retrieve(account_id)
            
            return {
                'accountId': account.id,
                'detailsSubmitted': account.details_submitted,
                'chargesEnabled': account.charges_enabled,
                'payoutsEnabled': account.payouts_enabled,
            }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/transfer-to-worker")
async def transfer_to_worker(request: TransferToWorkerRequest):
    """
    Transfer funds to worker's Stripe Connect account (70% of job amount)
    """
    try:
        print(f"Transferring ${request.amount} to worker {request.workerId} for job {request.jobId}")
        
        # Get worker's stripe_account_id and job payment_intent_id from Supabase
        async with httpx.AsyncClient() as client:
            # Get worker's stripe_account_id
            worker_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{request.workerId}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            worker_response.raise_for_status()
            users = worker_response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                raise HTTPException(status_code=400, detail="Worker has not set up Stripe Connect account")
            
            account_id = users[0]['stripe_account_id']
            print(f"Worker account ID: {account_id}")
            
            # Get job's payment_intent_id
            job_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{request.jobId}&select=payment_intent_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            job_response.raise_for_status()
            jobs = job_response.json()
            
            payment_intent_id = None
            if jobs and jobs[0].get('payment_intent_id'):
                payment_intent_id = jobs[0]['payment_intent_id']
                print(f"Payment intent ID: {payment_intent_id}")
        
        # Convert amount to cents
        amount_cents = int(request.amount * 100)
        
        # If payment intent exists, capture it first (if using manual capture)
        if payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                print(f"Payment intent status: {payment_intent.status}")
                
                # Capture payment intent if it's in requires_capture status
                if payment_intent.status == 'requires_capture':
                    print("Capturing payment intent...")
                    payment_intent = stripe.PaymentIntent.capture(payment_intent_id)
                    print(f"Payment intent captured: {payment_intent.status}")
                elif payment_intent.status == 'succeeded':
                    print("Payment intent already succeeded")
                else:
                    print(f"Warning: Payment intent status is {payment_intent.status}, may not be ready for transfer")
            except stripe.error.StripeError as e:
                error_msg = f"Could not capture payment intent: {str(e)}"
                print(f"❌ {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)
        
        # Create transfer to worker's Connect account
        print(f"Creating transfer of ${request.amount} ({amount_cents} cents) to {account_id}")
        try:
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency='usd',
                destination=account_id,
                metadata={
                    'job_id': request.jobId,
                    'worker_id': request.workerId,
                }
            )
        except stripe.error.StripeError as e:
            error_msg = f"Stripe transfer error: {str(e)}"
            print(f"❌ {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        print(f"Transfer created: {transfer.id}, status: {transfer.status}")
        
        return {
            'transferId': transfer.id,
            'amount': request.amount,
            'status': transfer.status
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/refund")
async def refund_payment(request: RefundRequest):
    """
    Refund a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Create refund
        refund_params = {
            'payment_intent': request.paymentIntentId,
        }
        if request.amount:
            refund_params['amount'] = int(request.amount * 100)  # Convert to cents
        
        refund = stripe.Refund.create(**refund_params)
        
        return {
            'refundId': refund.id,
            'status': refund.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/google-maps/geocode")
async def google_maps_geocode(
    address: str
):
    """
    Proxy for Google Maps Geocoding API
    """
    try:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": GOOGLE_MAPS_API_KEY
        }
            
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STRIPE CONNECT ENDPOINTS
# ============================================

class CreatePaymentIntentRequest(BaseModel):
    jobId: str
    amount: float
    requesterId: str
    workerId: Optional[str] = None

class CreateConnectAccountRequest(BaseModel):
    userId: str
    email: str

class ConnectOnboardingRequest(BaseModel):
    accountId: str

class TransferToWorkerRequest(BaseModel):
    jobId: str
    workerId: str
    amount: float

class ConfirmPaymentIntentRequest(BaseModel):
    paymentIntentId: str

class RefundRequest(BaseModel):
    paymentIntentId: str
    amount: Optional[float] = None

@app.post("/api/stripe/create-payment-intent")
async def create_payment_intent(request: CreatePaymentIntentRequest):
    """
    Create a Payment Intent for a job (escrow)
    Amount should be in dollars, will be converted to cents
    """
    try:
        amount_cents = int(request.amount * 100)  # Convert to cents
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method_types=['card'],
            capture_method='manual',  # Hold funds until we capture
            metadata={
                'job_id': request.jobId,
                'requester_id': request.requesterId,
                'worker_id': request.workerId or '',
            }
        )
        
        return {
            'clientSecret': payment_intent.client_secret,
            'paymentIntentId': payment_intent.id
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/confirm-payment-intent")
async def confirm_payment_intent(request: ConfirmPaymentIntentRequest):
    """
    Capture the payment intent (release funds from escrow)
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Capture the payment
        payment_intent = stripe.PaymentIntent.confirm(request.paymentIntentId)
        
        return {
            'success': True,
            'status': payment_intent.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/create-connect-account")
async def create_connect_account(request: CreateConnectAccountRequest):
    """
    Create a Stripe Connect Express account for a worker
    """
    try:
        # Validate input
        if not request.email or not request.userId:
            raise HTTPException(status_code=400, detail="Email and userId are required")
        
        print(f"Creating Stripe Connect account for user: {request.userId}, email: {request.email}")
        
        account = stripe.Account.create(
            type='express',
            country='US',
            email=request.email,
            capabilities={
                'card_payments': {'requested': True},
                'transfers': {'requested': True},
            },
            metadata={
                'user_id': request.userId,
            }
        )
        
        print(f"Stripe account created: {account.id}")
        
        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        print(f"Account link created: {account_link.url}")
        
        return {
            'accountId': account.id,
            'onboardingUrl': account_link.url,
            'detailsSubmitted': account.details_submitted,
            'chargesEnabled': account.charges_enabled,
            'payoutsEnabled': account.payouts_enabled,
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/connect-onboarding-url")
async def get_connect_onboarding_url(request: ConnectOnboardingRequest):
    """
    Get a new onboarding URL for an existing Connect account
    """
    try:
        account_link = stripe.AccountLink.create(
            account=request.accountId,
            refresh_url=f"http://localhost:8080/worker-dashboard?stripe_refresh=true",
            return_url=f"http://localhost:8080/worker-dashboard?stripe_success=true",
            type='account_onboarding',
        )
        
        return {
            'url': account_link.url
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stripe/connect-account-status/{user_id}")
async def get_connect_account_status(user_id: str):
    """
    Get the status of a worker's Stripe Connect account
    """
    try:
        # Get user's stripe_account_id from Supabase
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{user_id}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            response.raise_for_status()
            users = response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                return {
                    'accountId': None,
                    'detailsSubmitted': False,
                    'chargesEnabled': False,
                    'payoutsEnabled': False,
                }
            
            account_id = users[0]['stripe_account_id']
            account = stripe.Account.retrieve(account_id)
            
            return {
                'accountId': account.id,
                'detailsSubmitted': account.details_submitted,
                'chargesEnabled': account.charges_enabled,
                'payoutsEnabled': account.payouts_enabled,
            }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/transfer-to-worker")
async def transfer_to_worker(request: TransferToWorkerRequest):
    """
    Transfer funds to worker's Stripe Connect account (70% of job amount)
    """
    try:
        print(f"Transferring ${request.amount} to worker {request.workerId} for job {request.jobId}")
        
        # Get worker's stripe_account_id and job payment_intent_id from Supabase
        async with httpx.AsyncClient() as client:
            # Get worker's stripe_account_id
            worker_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?id=eq.{request.workerId}&select=stripe_account_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            worker_response.raise_for_status()
            users = worker_response.json()
            
            if not users or not users[0].get('stripe_account_id'):
                raise HTTPException(status_code=400, detail="Worker has not set up Stripe Connect account")
            
            account_id = users[0]['stripe_account_id']
            print(f"Worker account ID: {account_id}")
            
            # Get job's payment_intent_id
            job_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{request.jobId}&select=payment_intent_id",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                }
            )
            job_response.raise_for_status()
            jobs = job_response.json()
            
            payment_intent_id = None
            if jobs and jobs[0].get('payment_intent_id'):
                payment_intent_id = jobs[0]['payment_intent_id']
                print(f"Payment intent ID: {payment_intent_id}")
        
        # Convert amount to cents
        amount_cents = int(request.amount * 100)
        
        # If payment intent exists, capture it first (if using manual capture)
        if payment_intent_id:
            try:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
                print(f"Payment intent status: {payment_intent.status}")
                
                # Capture payment intent if it's in requires_capture status
                if payment_intent.status == 'requires_capture':
                    print("Capturing payment intent...")
                    payment_intent = stripe.PaymentIntent.capture(payment_intent_id)
                    print(f"Payment intent captured: {payment_intent.status}")
                elif payment_intent.status == 'succeeded':
                    print("Payment intent already succeeded")
                else:
                    print(f"Warning: Payment intent status is {payment_intent.status}, may not be ready for transfer")
            except stripe.error.StripeError as e:
                error_msg = f"Could not capture payment intent: {str(e)}"
                print(f"❌ {error_msg}")
                raise HTTPException(status_code=400, detail=error_msg)
        
        # Create transfer to worker's Connect account
        print(f"Creating transfer of ${request.amount} ({amount_cents} cents) to {account_id}")
        try:
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency='usd',
                destination=account_id,
                metadata={
                    'job_id': request.jobId,
                    'worker_id': request.workerId,
                }
            )
        except stripe.error.StripeError as e:
            error_msg = f"Stripe transfer error: {str(e)}"
            print(f"❌ {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        print(f"Transfer created: {transfer.id}, status: {transfer.status}")
        
        return {
            'transferId': transfer.id,
            'amount': request.amount,
            'status': transfer.status
        }
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        error_msg = f"Stripe error: {str(e)}"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/stripe/refund")
async def refund_payment(request: RefundRequest):
    """
    Refund a payment intent
    """
    try:
        payment_intent = stripe.PaymentIntent.retrieve(request.paymentIntentId)
        
        # Create refund
        refund_params = {
            'payment_intent': request.paymentIntentId,
        }
        if request.amount:
            refund_params['amount'] = int(request.amount * 100)  # Convert to cents
        
        refund = stripe.Refund.create(**refund_params)
        
        return {
            'refundId': refund.id,
            'status': refund.status
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

# Affiliate approval email endpoint
class AffiliateApprovalEmailRequest(BaseModel):
    affiliate_id: str
    affiliate_name: str
    affiliate_email: str
    user_id: str

@app.post("/api/affiliate/send-approval-email")
async def send_affiliate_approval_email_endpoint(
    request: AffiliateApprovalEmailRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
):
    """
    Send approval email to affiliate with temporary password
    Generates a new temporary password and sends it via email
    
    Note: Admin authentication is optional since affiliate is already approved in frontend.
    This endpoint only sends an email notification.
    """
    try:
        print(f"=== AFFILIATE APPROVAL EMAIL START ===")
        print(f"Affiliate ID: {request.affiliate_id}")
        print(f"Affiliate Name: {request.affiliate_name}")
        print(f"Affiliate Email: {request.affiliate_email}")
        print(f"User ID: {request.user_id}")
        
        # Optional: Try to validate admin token if provided (for logging purposes)
        # Don't fail if token is invalid - affiliate is already approved
        if credentials:
            try:
                await get_current_admin(credentials)
                print(f"✅ Admin authentication successful")
            except HTTPException as auth_error:
                print(f"⚠️ Admin token validation failed: {auth_error.detail}, but continuing anyway (affiliate already approved)")
        
        # Validate required fields
        if not request.affiliate_email:
            raise HTTPException(status_code=400, detail="Affiliate email is required")
        if not request.user_id:
            raise HTTPException(status_code=400, detail="User ID is required")
        
        async with httpx.AsyncClient() as client:
            # Generate a new temporary password
            import string
            temporary_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
            print(f"Generated temporary password: {temporary_password}")
            
            # Update user password in Supabase Auth
            user_data = {
                "password": temporary_password
            }
            
            print(f"Updating user password in Supabase Auth for user ID: {request.user_id}")
            auth_response = await client.put(
                f"{SUPABASE_URL}/auth/v1/admin/users/{request.user_id}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json"
                },
                json=user_data
            )
            
            print(f"Auth response status: {auth_response.status_code}")
            print(f"Auth response: {auth_response.text}")
            
            if auth_response.status_code not in (200, 201):
                print(f"ERROR: Failed to update user password")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update user password in Supabase Auth"
                )
            
            print(f"✅ Successfully updated password for user ID: {request.user_id}")
            
            # Get frontend URL from environment or use default
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
            login_url = f"{frontend_url}/login?role=affiliate"
            
            # Send approval email
            print(f"Sending approval email to {request.affiliate_email}...")
            try:
                email_result = await send_affiliate_approval_email(
                    affiliate_name=request.affiliate_name,
                    affiliate_email=request.affiliate_email,
                    temporary_password=temporary_password,
                    login_url=login_url
                )
                
                if not email_result.get("success", False):
                    error_msg = email_result.get("message", "Unknown error")
                    print(f"ERROR: Failed to send email: {error_msg}")
                    # Don't raise exception - return success but with warning
                    return {
                        "success": True,
                        "message": f"Affiliate approved. Password updated. Email sending failed: {error_msg}",
                        "email_sent": False,
                        "warning": error_msg
                    }
            except Exception as email_error:
                print(f"ERROR: Exception while sending email: {str(email_error)}")
                import traceback
                traceback.print_exc()
                # Don't raise exception - return success but with warning
                return {
                    "success": True,
                    "message": f"Affiliate approved. Password updated. Email sending failed: {str(email_error)}",
                    "email_sent": False,
                    "warning": str(email_error)
                }
            
            print(f"✅ Approval email sent successfully to {request.affiliate_email}")
            
            return {
                "success": True,
                "message": f"Approval email sent successfully to {request.affiliate_email}",
                "email_sent": True
            }
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=error_msg)

# ============================================
# ADMIN ENDPOINTS
# ============================================

# Platform Metrics
@app.get("/api/admin/metrics")
async def get_admin_metrics(admin: dict = Depends(get_current_admin)):
    """Get real-time platform metrics"""
    try:
        metrics = await get_platform_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/revenue")
async def get_admin_revenue(days: int = 30, admin: dict = Depends(get_current_admin)):
    """Get revenue metrics"""
    try:
        revenue = await get_revenue_metrics(days)
        return revenue
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Dispute Management
@app.get("/api/admin/disputes")
async def get_admin_disputes(admin: dict = Depends(get_current_admin)):
    """Get all disputes"""
    try:
        disputes = await get_disputes()
        return {"disputes": disputes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/disputes/{dispute_id}")
async def get_admin_dispute_details(dispute_id: str, admin: dict = Depends(get_current_admin)):
    """Get dispute details"""
    try:
        dispute = await get_dispute_details(dispute_id)
        if not dispute:
            raise HTTPException(status_code=404, detail="Dispute not found")
        return dispute
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DisputeResolution(BaseModel):
    job_id: str
    resolution: str  # 'approve', 'refund', 'partial_refund'
    admin_notes: str
    favor_requester: bool = False

@app.post("/api/admin/disputes/resolve")
async def resolve_admin_dispute(resolution: DisputeResolution, admin: dict = Depends(get_current_admin)):
    """Resolve a dispute"""
    try:
        result = await resolve_dispute(
            job_id=resolution.job_id,
            resolution=resolution.resolution,
            admin_notes=resolution.admin_notes,
            favor_requester=resolution.favor_requester
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Payout Management
@app.get("/api/admin/payouts")
async def get_admin_payouts(status: Optional[str] = None, limit: int = 100, offset: int = 0, admin: dict = Depends(get_current_admin)):
    """Get payouts"""
    try:
        if status == "pending":
            payouts = await get_pending_payouts()
            return {"payouts": payouts, "total": len(payouts)}
        else:
            result = await get_all_payouts(limit, offset)
            return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PayoutAction(BaseModel):
    transaction_id: str
    admin_notes: Optional[str] = None

@app.post("/api/admin/payouts/approve")
async def approve_admin_payout(action: PayoutAction, admin: dict = Depends(get_current_admin)):
    """Approve a payout"""
    try:
        result = await approve_payout(action.transaction_id, action.admin_notes)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PayoutRejection(BaseModel):
    transaction_id: str
    reason: str

@app.post("/api/admin/payouts/reject")
async def reject_admin_payout(rejection: PayoutRejection, admin: dict = Depends(get_current_admin)):
    """Reject a payout"""
    try:
        result = await reject_payout(rejection.transaction_id, rejection.reason)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# User Management
@app.get("/api/admin/users")
async def get_admin_users(search: Optional[str] = None, limit: int = 100, offset: int = 0, admin: dict = Depends(get_current_admin)):
    """Get all users"""
    try:
        result = await get_all_users(limit, offset, search)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/users/{user_id}")
async def get_admin_user_details(user_id: str, admin: dict = Depends(get_current_admin)):
    """Get user details"""
    try:
        user = await get_user_details(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UserBan(BaseModel):
    user_id: str
    reason: str

@app.post("/api/admin/users/ban")
async def ban_admin_user(ban: UserBan, admin: dict = Depends(get_current_admin)):
    """Ban a user"""
    try:
        result = await ban_user(ban.user_id, ban.reason)
        if not result.get("success"):
            error_msg = result.get("message", "Failed to ban user")
            print(f"Ban failed: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Exception in ban_admin_user: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class UserFlag(BaseModel):
    user_id: str
    reason: str
    flag_type: str = "low_rating"

@app.post("/api/admin/users/flag")
async def flag_admin_user(flag: UserFlag, admin: dict = Depends(get_current_admin)):
    """Flag a user"""
    try:
        result = await flag_user(flag.user_id, flag.reason, flag.flag_type)
        if not result.get("success"):
            error_msg = result.get("message", "Failed to flag user")
            print(f"Flag failed: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Exception in flag_admin_user: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class UserUpdate(BaseModel):
    user_id: str
    updates: dict

@app.patch("/api/admin/users/update")
async def update_admin_user(update: UserUpdate, admin: dict = Depends(get_current_admin)):
    """Update user information"""
    try:
        result = await update_user(update.user_id, update.updates)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UserUnban(BaseModel):
    user_id: str

@app.post("/api/admin/users/unban")
async def unban_admin_user(unban: UserUnban, admin: dict = Depends(get_current_admin)):
    """Unban a user"""
    try:
        result = await unban_user(unban.user_id)
        if not result.get("success"):
            error_msg = result.get("message", "Failed to unban user")
            print(f"Unban failed: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Exception in unban_admin_user: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class UserUnflag(BaseModel):
    user_id: str

@app.post("/api/admin/users/unflag")
async def unflag_admin_user(unflag: UserUnflag, admin: dict = Depends(get_current_admin)):
    """Unflag a user"""
    try:
        result = await unflag_user(unflag.user_id)
        if not result.get("success"):
            error_msg = result.get("message", "Failed to unflag user")
            print(f"Unflag failed: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Exception in unflag_admin_user: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Transaction Management
@app.get("/api/admin/transactions")
async def get_admin_transactions(status: Optional[str] = None, limit: int = 100, offset: int = 0, admin: dict = Depends(get_current_admin)):
    """Get all transactions"""
    try:
        result = await get_all_transactions(limit, offset, status)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/transactions/stats")
async def get_admin_transaction_stats(admin: dict = Depends(get_current_admin)):
    """Get transaction statistics"""
    try:
        stats = await get_transaction_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RefundRequest(BaseModel):
    transaction_id: str
    amount: Optional[float] = None
    reason: str = "Admin refund"

@app.post("/api/admin/transactions/refund")
async def process_admin_refund(refund: RefundRequest, admin: dict = Depends(get_current_admin)):
    """Process a refund"""
    try:
        result = await process_refund(refund.transaction_id, refund.amount, refund.reason)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Image Review
@app.get("/api/admin/media/flagged")
async def get_admin_flagged_media(admin: dict = Depends(get_current_admin)):
    """Get flagged media for review"""
    try:
        media = await get_flagged_media()
        return {"media": media}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/media/{media_id}")
async def get_admin_media_details(media_id: str, admin: dict = Depends(get_current_admin)):
    """Get media details"""
    try:
        media = await get_media_details(media_id)
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        return media
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MediaApproval(BaseModel):
    media_id: str
    admin_notes: Optional[str] = None

@app.post("/api/admin/media/approve")
async def approve_admin_media(approval: MediaApproval, admin: dict = Depends(get_current_admin)):
    """Approve media"""
    try:
        result = await approve_media(approval.media_id, approval.admin_notes)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MediaRejection(BaseModel):
    media_id: str
    reason: str

@app.post("/api/admin/media/reject")
async def reject_admin_media(rejection: MediaRejection, admin: dict = Depends(get_current_admin)):
    """Reject media"""
    try:
        result = await reject_media(rejection.media_id, rejection.reason)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
