"""
Email Service for Composite Service
Handles sending email notifications via SMTP
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from typing import Optional

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")  # Email address for sending
SMTP_PASS = os.getenv("SMTP_PASS")  # App password or email password
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)  # From address (defaults to SMTP_USER)


def send_email(to: str, subject: str, body: str, is_html: bool = False) -> bool:
    """
    Send email using SMTP.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text or HTML)
        is_html: If True, body is treated as HTML
    
    Returns:
        True if email sent successfully, False otherwise
    """
    if not SMTP_USER or not SMTP_PASS:
        print(f"⚠️  SMTP credentials not configured, skipping email to {to}")
        print(f"   Set SMTP_USER and SMTP_PASS environment variables")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = SMTP_FROM
        msg['To'] = to
        msg['Subject'] = subject
        
        # Add body
        if is_html:
            msg.attach(MIMEText(body, 'html'))
        else:
            msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent to {to}: {subject}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {e}")
        print(f"   Check SMTP_USER and SMTP_PASS credentials")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP error sending email to {to}: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to send email to {to}: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_html_email(to: str, subject: str, html_body: str) -> bool:
    """Convenience function to send HTML email"""
    return send_email(to, subject, html_body, is_html=True)

