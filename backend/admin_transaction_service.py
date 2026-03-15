"""
Admin Transaction Service
Handles transaction management and refunds
"""
import os
import httpx
import stripe
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


async def get_all_transactions(limit: int = 100, offset: int = 0, status: Optional[str] = None) -> Dict:
    """Get all transactions with pagination"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "select": "*,job:jobs(*),worker:users!transactions_worker_id_fkey(id,name,email),requester:users!transactions_requester_id_fkey(id,name,email)",
                "order": "created_at.desc",
                "limit": str(limit),
                "offset": str(offset)
            }
            
            if status:
                params["status"] = f"eq.{status}"
            
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params=params
            )
            
            transactions = response.json() if response.status_code == 200 else []
            
            # Get total count
            count_params = {}
            if status:
                count_params["status"] = f"eq.{status}"
            
            count_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={**count_params, "select": "id"}
            )
            total_count = len(count_response.json()) if count_response.status_code == 200 else 0
            
            return {
                "transactions": transactions,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
            
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return {
            "transactions": [],
            "total": 0,
            "limit": limit,
            "offset": offset
        }


async def process_refund(transaction_id: str, amount: Optional[float] = None, reason: str = "Admin refund") -> Dict:
    """Process a refund for a transaction"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get transaction details
            transaction_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"id": f"eq.{transaction_id}"}
            )
            
            if transaction_response.status_code != 200:
                return {
                    "success": False,
                    "message": "Transaction not found"
                }
            
            transactions = transaction_response.json()
            if not transactions:
                return {
                    "success": False,
                    "message": "Transaction not found"
                }
            
            transaction = transactions[0]
            payment_intent_id = transaction.get("stripe_payment_intent_id")
            
            if not payment_intent_id:
                return {
                    "success": False,
                    "message": "No Stripe payment intent found for this transaction"
                }
            
            # Process refund via Stripe
            if not STRIPE_SECRET_KEY:
                return {
                    "success": False,
                    "message": "Stripe not configured"
                }
            
            refund_amount = amount if amount else int(float(transaction.get("total_amount", 0)) * 100)  # Convert to cents
            
            refund = stripe.Refund.create(
                payment_intent=payment_intent_id,
                amount=refund_amount,
                reason="requested_by_customer" if "customer" in reason.lower() else "fraudulent"
            )
            
            # Update transaction status
            update_response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"id": f"eq.{transaction_id}"},
                json={
                    "status": "refunded",
                    "admin_notes": f"Refund processed: {reason}. Stripe refund ID: {refund.id}"
                }
            )
            
            # Update job status if needed
            job_id = transaction.get("job_id")
            if job_id:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    headers=headers,
                    params={"id": f"eq.{job_id}"},
                    json={"status": "cancelled"}
                )
            
            return {
                "success": True,
                "message": "Refund processed successfully",
                "transaction_id": transaction_id,
                "refund_id": refund.id,
                "refund_amount": refund_amount / 100
            }
            
    except stripe.error.StripeError as e:
        print(f"Stripe error processing refund: {e}")
        return {
            "success": False,
            "message": f"Stripe error: {str(e)}"
        }
    except Exception as e:
        print(f"Error processing refund: {e}")
        return {
            "success": False,
            "message": str(e)
        }


async def get_transaction_stats() -> Dict:
    """Get transaction statistics"""
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Get all transactions
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/transactions",
                headers=headers,
                params={"select": "status,total_amount,platform_fee,worker_payout"}
            )
            
            transactions = response.json() if response.status_code == 200 else []
            
            stats = {
                "total": len(transactions),
                "completed": 0,
                "pending": 0,
                "failed": 0,
                "refunded": 0,
                "total_volume": 0.0,
                "total_revenue": 0.0,
                "total_payouts": 0.0
            }
            
            for txn in transactions:
                status = txn.get("status", "pending")
                stats[status] = stats.get(status, 0) + 1
                
                if status == "completed":
                    stats["total_volume"] += float(txn.get("total_amount", 0))
                    stats["total_revenue"] += float(txn.get("platform_fee", 0))
                    stats["total_payouts"] += float(txn.get("worker_payout", 0))
            
            # Round values
            stats["total_volume"] = round(stats["total_volume"], 2)
            stats["total_revenue"] = round(stats["total_revenue"], 2)
            stats["total_payouts"] = round(stats["total_payouts"], 2)
            
            return stats
            
    except Exception as e:
        print(f"Error fetching transaction stats: {e}")
        return {
            "total": 0,
            "completed": 0,
            "pending": 0,
            "failed": 0,
            "refunded": 0,
            "total_volume": 0.0,
            "total_revenue": 0.0,
            "total_payouts": 0.0
        }
