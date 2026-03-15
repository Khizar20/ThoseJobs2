"""
Affiliate Email Service
Handles sending emails to affiliates when their application is approved
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

# Try to load dotenv, but don't fail if it's not available
# (main.py already loads it)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv already loaded by main.py or not needed

# SMTP Configuration from environment variables
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8080")


def create_affiliate_approval_email_html(
    affiliate_name: str,
    affiliate_email: str,
    temporary_password: str,
    login_url: str
) -> str:
    """
    Create a beautifully designed HTML email for affiliate approval
    """
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Affiliate Account Approved - ThoseJobs</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
        <table role="presentation" style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 40px 20px; text-align: center;">
                    <!-- Main Container -->
                    <table role="presentation" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); overflow: hidden;">
                        <!-- Header -->
                        <tr>
                            <td style="background: linear-gradient(135deg, #0846BC 0%, #063A9B 100%); padding: 40px 30px; text-align: center;">
                                <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">
                                    🎉 Congratulations!
                                </h1>
                                <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 16px; opacity: 0.9;">
                                    Your Affiliate Account Has Been Approved
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Content -->
                        <tr>
                            <td style="padding: 40px 30px;">
                                <p style="margin: 0 0 20px 0; color: #05070A; font-size: 16px; line-height: 1.6;">
                                    Hi <strong>{affiliate_name}</strong>,
                                </p>
                                
                                <p style="margin: 0 0 20px 0; color: #666666; font-size: 16px; line-height: 1.6;">
                                    Great news! Your affiliate partner application has been reviewed and approved. 
                                    You can now start earning commissions by referring workers and requesters to ThoseJobs.
                                </p>
                                
                                <!-- Credentials Box -->
                                <div style="background-color: #FCFAF8; border-left: 4px solid #0846BC; padding: 20px; margin: 30px 0; border-radius: 8px;">
                                    <p style="margin: 0 0 15px 0; color: #05070A; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
                                        Your Login Credentials
                                    </p>
                                    <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                        <tr>
                                            <td style="padding: 8px 0; color: #666666; font-size: 14px;">
                                                <strong>Email:</strong>
                                            </td>
                                            <td style="padding: 8px 0; color: #05070A; font-size: 14px; font-family: monospace;">
                                                {affiliate_email}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style="padding: 8px 0; color: #666666; font-size: 14px;">
                                                <strong>Temporary Password:</strong>
                                            </td>
                                            <td style="padding: 8px 0; color: #0846BC; font-size: 16px; font-weight: 700; font-family: monospace; letter-spacing: 2px;">
                                                {temporary_password}
                                            </td>
                                        </tr>
                                    </table>
                                    <p style="margin: 15px 0 0 0; color: #666666; font-size: 12px; font-style: italic;">
                                        ⚠️ Please change your password after your first login for security.
                                    </p>
                                </div>
                                
                                <!-- Login Button -->
                                <table role="presentation" style="width: 100%; margin: 30px 0;">
                                    <tr>
                                        <td style="text-align: center;">
                                            <a href="{login_url}" 
                                               style="display: inline-block; padding: 16px 40px; background-color: #0846BC; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; letter-spacing: 0.5px; box-shadow: 0 2px 4px rgba(8, 70, 188, 0.3); transition: background-color 0.3s;">
                                                🔐 Login to Affiliate Dashboard
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                                
                                <!-- What's Next Section -->
                                <div style="margin: 30px 0; padding: 20px; background-color: #FCFAF8; border-radius: 8px;">
                                    <h2 style="margin: 0 0 15px 0; color: #05070A; font-size: 20px; font-weight: 600;">
                                        What's Next?
                                    </h2>
                                    <ul style="margin: 0; padding-left: 20px; color: #666666; font-size: 14px; line-height: 1.8;">
                                        <li style="margin-bottom: 10px;">
                                            <strong>Log in</strong> to your affiliate dashboard using the credentials above
                                        </li>
                                        <li style="margin-bottom: 10px;">
                                            <strong>Get your unique affiliate links</strong> for workers and requesters
                                        </li>
                                        <li style="margin-bottom: 10px;">
                                            <strong>Start sharing</strong> your links on your website, social media, or email campaigns
                                        </li>
                                        <li style="margin-bottom: 10px;">
                                            <strong>Earn commissions</strong> when your referrals complete their first job (10% of platform fees)
                                        </li>
                                        <li>
                                            <strong>Track your performance</strong> with real-time analytics and monthly payouts
                                        </li>
                                    </ul>
                                </div>
                                
                                <!-- Commission Info -->
                                <div style="margin: 30px 0; padding: 20px; background: linear-gradient(135deg, #0846BC 0%, #063A9B 100%); border-radius: 8px; color: #ffffff;">
                                    <h3 style="margin: 0 0 10px 0; font-size: 18px; font-weight: 600;">
                                        💰 Commission Structure
                                    </h3>
                                    <p style="margin: 0; font-size: 14px; opacity: 0.9; line-height: 1.6;">
                                        You earn <strong>10% of platform fees</strong> when your referrals complete jobs. 
                                        For example, if a referred worker completes a $100 job, you earn $3 (10% of the $30 platform fee).
                                    </p>
                                </div>
                                
                                <p style="margin: 30px 0 0 0; color: #666666; font-size: 14px; line-height: 1.6;">
                                    If you have any questions or need assistance, feel free to reach out to our support team.
                                </p>
                                
                                <p style="margin: 20px 0 0 0; color: #05070A; font-size: 16px; font-weight: 600;">
                                    Welcome to the ThoseJobs Affiliate Program! 🚀
                                </p>
                            </td>
                        </tr>
                        
                        <!-- Footer -->
                        <tr>
                            <td style="background-color: #05070A; padding: 30px; text-align: center;">
                                <p style="margin: 0 0 10px 0; color: #ffffff; font-size: 14px; font-weight: 600;">
                                    ThoseJobs
                                </p>
                                <p style="margin: 0 0 20px 0; color: #999999; font-size: 12px;">
                                    Connecting workers with opportunities
                                </p>
                                <p style="margin: 0; color: #666666; font-size: 11px;">
                                    This is an automated email. Please do not reply to this message.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html_content


def _send_smtp_email(msg):
    """Helper function to send email synchronously"""
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        server.send_message(msg)

def create_affiliate_approval_email_text(
    affiliate_name: str,
    affiliate_email: str,
    temporary_password: str,
    login_url: str
) -> str:
    """
    Create a plain text version of the affiliate approval email
    """
    text_content = f"""
Congratulations! Your Affiliate Account Has Been Approved

Hi {affiliate_name},

Great news! Your affiliate partner application has been reviewed and approved. 
You can now start earning commissions by referring workers and requesters to ThoseJobs.

YOUR LOGIN CREDENTIALS:
Email: {affiliate_email}
Temporary Password: {temporary_password}

⚠️ Please change your password after your first login for security.

LOGIN TO YOUR DASHBOARD:
{login_url}

WHAT'S NEXT?
- Log in to your affiliate dashboard using the credentials above
- Get your unique affiliate links for workers and requesters
- Start sharing your links on your website, social media, or email campaigns
- Earn commissions when your referrals complete their first job (10% of platform fees)
- Track your performance with real-time analytics and monthly payouts

COMMISSION STRUCTURE:
You earn 10% of platform fees when your referrals complete jobs. 
For example, if a referred worker completes a $100 job, you earn $3 (10% of the $30 platform fee).

If you have any questions or need assistance, feel free to reach out to our support team.

Welcome to the ThoseJobs Affiliate Program!

---
ThoseJobs
Connecting workers with opportunities

This is an automated email. Please do not reply to this message.
    """
    return text_content.strip()


async def send_affiliate_approval_email(
    affiliate_name: str,
    affiliate_email: str,
    temporary_password: str,
    login_url: Optional[str] = None
) -> dict:
    """
    Send affiliate approval email with login credentials
    
    Args:
        affiliate_name: Name of the affiliate
        affiliate_email: Email address of the affiliate
        temporary_password: Temporary password for login
        login_url: Optional custom login URL (defaults to FRONTEND_URL/login?role=affiliate)
    
    Returns:
        dict with success status and message
    """
    try:
        # Validate SMTP configuration
        if not SMTP_EMAIL or not SMTP_APP_PASSWORD:
            return {
                "success": False,
                "message": "SMTP configuration is missing. Please set SMTP_EMAIL and SMTP_APP_PASSWORD environment variables."
            }
        
        # Set default login URL if not provided
        if not login_url:
            login_url = f"{FRONTEND_URL}/login?role=affiliate"
        
        # Create email message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🎉 Your Affiliate Account Has Been Approved - ThoseJobs"
        msg["From"] = f"ThoseJobs <{SMTP_EMAIL}>"
        msg["To"] = affiliate_email
        
        # Create HTML and text versions
        html_content = create_affiliate_approval_email_html(
            affiliate_name, affiliate_email, temporary_password, login_url
        )
        text_content = create_affiliate_approval_email_text(
            affiliate_name, affiliate_email, temporary_password, login_url
        )
        
        # Attach both versions
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email via SMTP (using asyncio executor for blocking I/O)
        import asyncio
        try:
            # Python 3.9+ has asyncio.to_thread, fallback to run_in_executor for older versions
            if hasattr(asyncio, 'to_thread'):
                await asyncio.to_thread(_send_smtp_email, msg)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _send_smtp_email, msg)
        except AttributeError:
            # Fallback for Python < 3.7
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _send_smtp_email, msg)
        
        return {
            "success": True,
            "message": f"Approval email sent successfully to {affiliate_email}"
        }
        
    except smtplib.SMTPAuthenticationError as e:
        return {
            "success": False,
            "message": f"SMTP authentication failed: {str(e)}"
        }
    except smtplib.SMTPException as e:
        return {
            "success": False,
            "message": f"SMTP error occurred: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to send email: {str(e)}"
        }
