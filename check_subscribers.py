"""
Quick script to check if Pub/Sub subscribers are running
"""
import os
import sys
import time
from dotenv import load_dotenv

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path, override=True)

print("=" * 60)
print("Pub/Sub Subscriber Status Check")
print("=" * 60)

project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
print(f"\nProject ID: {project_id}")

event_sub = os.getenv("PUBSUB_EVENT_NOTIFICATION_SUB", "event-notification-sub")
user_sub = os.getenv("PUBSUB_USER_WELCOME_SUB", "user-welcome-sub")

print(f"\nSubscriptions:")
print(f"  Event: {event_sub}")
print(f"  User: {user_sub}")

print("\n" + "=" * 60)
print("To check if subscribers are running:")
print("1. Look for these messages in Composite Service startup logs:")
print("   - '🚀 Starting event-created subscriber on ...'")
print("   - '✅ Event subscriber started successfully, waiting for messages...'")
print("   - '🚀 Starting user-created subscriber on ...'")
print("   - '✅ User subscriber started successfully, waiting for messages...'")
print("\n2. If you see '✅ Started event-created subscriber thread' but NOT")
print("   '✅ Event subscriber started successfully', the subscriber may have crashed.")
print("\n3. Check GCP Console > Pub/Sub > Subscriptions to verify subscriptions exist.")
print("=" * 60)

