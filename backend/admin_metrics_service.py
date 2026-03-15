"""
Admin Metrics Service
Provides real-time platform metrics from database
"""
import os
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")


async def get_platform_metrics() -> Dict:
    """Get real-time platform metrics from database"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get total jobs completed
            jobs_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                headers=headers,
                params={"status": "eq.completed", "select": "id"}
            )
            total_jobs_completed = len(jobs_response.json()) if jobs_response.status_code == 200 else 0
            
            # Get total workers (users with worker role)
            workers_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"role": "eq.worker", "select": "id"}
            )
            total_workers = len(workers_response.json()) if workers_response.status_code == 200 else 0
            
            # Get total requesters (users with requester role)
            requesters_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users",
                headers=headers,
                params={"role": "eq.requester", "select": "id"}
            )
            total_clients = len(requesters_response.json()) if requesters_response.status_code == 200 else 0
            
            # Get total fees collected (sum of platform_fee from completed jobs)
            fees_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                headers=headers,
                params={"status": "eq.completed", "select": "platform_fee"}
            )
            total_fees = 0.0
            if fees_response.status_code == 200:
                fees_data = fees_response.json()
                total_fees = sum(float(job.get("platform_fee", 0)) for job in fees_data)
            
            # Get jobs per day (last 7 days)
            today = datetime.now()
            jobs_per_day = []
            for i in range(6, -1, -1):
                date = today - timedelta(days=i)
                date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                date_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                day_jobs_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    headers=headers,
                    params={
                        "created_at": f"gte.{date_start.isoformat()}",
                        "created_at": f"lte.{date_end.isoformat()}",
                        "select": "id"
                    }
                )
                count = len(day_jobs_response.json()) if day_jobs_response.status_code == 200 else 0
                jobs_per_day.append(count)
            
            # Get jobs per month (last 4 months)
            jobs_per_month = []
            for i in range(3, -1, -1):
                # Calculate month start and end
                month_date = today - timedelta(days=30*i)
                month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if month_start.month == 12:
                    month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(microseconds=1)
                else:
                    month_end = month_start.replace(month=month_start.month + 1) - timedelta(microseconds=1)
                
                month_jobs_response = await client.get(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    headers=headers,
                    params={
                        "created_at": f"gte.{month_start.isoformat()}",
                        "created_at": f"lte.{month_end.isoformat()}",
                        "select": "id"
                    }
                )
                count = len(month_jobs_response.json()) if month_jobs_response.status_code == 200 else 0
                jobs_per_month.append(count)
            
            return {
                "total_jobs_completed": total_jobs_completed,
                "total_workers": total_workers,
                "total_clients": total_clients,
                "total_fees_collected": round(total_fees, 2),
                "jobs_per_day": jobs_per_day,
                "jobs_per_month": jobs_per_month
            }
            
    except Exception as e:
        print(f"Error fetching platform metrics: {e}")
        # Return zeros on error
        return {
            "total_jobs_completed": 0,
            "total_workers": 0,
            "total_clients": 0,
            "total_fees_collected": 0.0,
            "jobs_per_day": [0] * 7,
            "jobs_per_month": [0] * 4
        }


async def get_revenue_metrics(days: int = 30) -> Dict:
    """Get revenue metrics for the specified number of days"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get transactions from last N days
            date_start = datetime.now() - timedelta(days=days)
            
            transactions_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={
                    "created_at": f"gte.{date_start.isoformat()}",
                    "status": "eq.completed",
                    "select": "platform_fee,created_at,total_amount"
                }
            )
            
            transactions = transactions_response.json() if transactions_response.status_code == 200 else []
            
            # Calculate metrics
            total_revenue = sum(float(t.get("platform_fee", 0)) for t in transactions)
            total_volume = sum(float(t.get("total_amount", 0)) for t in transactions)
            
            # Daily breakdown
            daily_revenue = {}
            for transaction in transactions:
                date_str = transaction.get("created_at", "")[:10]  # YYYY-MM-DD
                if date_str:
                    daily_revenue[date_str] = daily_revenue.get(date_str, 0) + float(transaction.get("platform_fee", 0))
            
            return {
                "total_revenue": round(total_revenue, 2),
                "total_volume": round(total_volume, 2),
                "transaction_count": len(transactions),
                "daily_revenue": daily_revenue,
                "average_daily_revenue": round(total_revenue / days, 2) if days > 0 else 0
            }
            
    except Exception as e:
        print(f"Error fetching revenue metrics: {e}")
        return {
            "total_revenue": 0.0,
            "total_volume": 0.0,
            "transaction_count": 0,
            "daily_revenue": {},
            "average_daily_revenue": 0.0
        }
