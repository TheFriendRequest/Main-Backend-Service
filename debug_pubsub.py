"""
Debug script to test Pub/Sub publishing and verify configuration
"""
import os
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path, override=True)

def check_config():
    """Check Pub/Sub and email configuration"""
    print("=" * 60)
    print("Pub/Sub & Email Configuration Check")
    print("=" * 60)
    
    # Check GCP config
    print("\n[GCP Configuration]")
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if project_id:
        print(f"   [OK] GCP_PROJECT_ID: {project_id}")
    else:
        print("   [ERROR] GCP_PROJECT_ID: NOT SET")
    
    # Check service account
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./pubsub-service-account.json")
    if os.path.exists(creds_path):
        print(f"   [OK] Service account key: {creds_path} (exists)")
    else:
        print(f"   [ERROR] Service account key: {creds_path} (NOT FOUND)")
    
    # Check Pub/Sub topics
    print("\n[Pub/Sub Topics]")
    event_topic = os.getenv("PUBSUB_EVENT_CREATED_TOPIC", "event-created")
    user_topic = os.getenv("PUBSUB_USER_CREATED_TOPIC", "user-created")
    print(f"   Event topic: {event_topic}")
    print(f"   User topic: {user_topic}")
    
    # Check subscriptions
    print("\n[Pub/Sub Subscriptions]")
    event_sub = os.getenv("PUBSUB_EVENT_NOTIFICATION_SUB", "event-notification-sub")
    user_sub = os.getenv("PUBSUB_USER_WELCOME_SUB", "user-welcome-sub")
    print(f"   Event subscription: {event_sub}")
    print(f"   User subscription: {user_sub}")
    
    # Check SMTP config
    print("\n[SMTP Configuration]")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.getenv("SMTP_PORT", "587")
    
    if smtp_user:
        print(f"   [OK] SMTP_USER: {smtp_user}")
    else:
        print("   [ERROR] SMTP_USER: NOT SET")
    
    if smtp_pass:
        print(f"   [OK] SMTP_PASS: {'*' * len(smtp_pass)} (set)")
    else:
        print("   [ERROR] SMTP_PASS: NOT SET")
    
    print(f"   SMTP_HOST: {smtp_host}")
    print(f"   SMTP_PORT: {smtp_port}")
    
    # Test imports
    print("\n[Package Imports]")
    try:
        from google.cloud import pubsub_v1
        print("   [OK] google-cloud-pubsub: Imported")
    except ImportError as e:
        print(f"   [ERROR] google-cloud-pubsub: {e}")
    
    try:
        from email_service import send_email
        print("   [OK] email_service: Imported")
    except ImportError as e:
        print(f"   [ERROR] email_service: {e}")
    
    # Test publisher
    print("\n[Publisher Test]")
    try:
        from pubsub.publishers import publish_event_created
        print("   [OK] publish_event_created function: Available")
        
        # Try to get project ID
        if project_id:
            print(f"   [OK] Project ID available for publishing")
        else:
            print("   [WARNING] Project ID missing - publishing will fail")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    # Test subscriber imports
    print("\n[Subscriber Test]")
    try:
        from pubsub.subscribers import start_event_subscriber, start_user_subscriber
        print("   [OK] Subscriber functions: Available")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test email service
    print("\n[Email Service Test]")
    try:
        from email_service import send_email
        if smtp_user and smtp_pass:
            print("   [OK] Email service ready (credentials set)")
        else:
            print("   [WARNING] Email service ready but credentials not set")
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("1. Test email: python test_email.py your-email@gmail.com")
    print("2. Start Composite Service and check for subscriber startup messages")
    print("3. Create an event and watch logs for:")
    print("   - [OK] Published event-created message: ...")
    print("   - [RECEIVED] Received event-created notification: ...")
    print("   - [OK] Email sent to ...")
    print("=" * 60)

if __name__ == "__main__":
    check_config()

