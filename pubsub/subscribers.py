"""
Pub/Sub Subscribers for Composite Service
Listens to topics and sends email notifications
"""
from google.cloud import pubsub_v1  # type: ignore
import json
import os
import httpx
import asyncio
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from email_service import send_email

# Load .env file to ensure environment variables are available
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path, override=True)

project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://localhost:8001")

# Subscription names
EVENT_NOTIFICATION_SUB = os.getenv("PUBSUB_EVENT_NOTIFICATION_SUB", "event-notification-sub")
USER_WELCOME_SUB = os.getenv("PUBSUB_USER_WELCOME_SUB", "user-welcome-sub")


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Lookup user by user_id from User Service"""
    try:
        async with httpx.AsyncClient() as client:
            # Use /users/{user_id:int} endpoint - FastAPI will match integer user_ids
            # Internal call - use 'system' header for authentication bypass
            response = await client.get(
                f"{USERS_SERVICE_URL}/users/{user_id}",
                headers={"x-firebase-uid": "system"},  # Internal call - User Service will validate this
                timeout=5.0
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                print(f"[EVENT SUBSCRIBER] User {user_id} not found (404)")
                return None
            else:
                print(f"[EVENT SUBSCRIBER] Unexpected status code {response.status_code} when fetching user {user_id}")
                print(f"[EVENT SUBSCRIBER] Response: {response.text[:200]}")
                return None
    except httpx.HTTPStatusError as e:
        print(f"[EVENT SUBSCRIBER] HTTP error fetching user {user_id}: {e.response.status_code} - {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"[EVENT SUBSCRIBER] Error fetching user {user_id}: {e}")
        return None


def handle_event_created(message: pubsub_v1.subscriber.message.Message):  # type: ignore
    """Handle event creation notification - send email to creator"""
    print(f"=" * 60)
    print(f"📨 [EVENT SUBSCRIBER] RECEIVED MESSAGE!")
    print(f"   Message ID: {message.message_id}")
    print(f"   Attributes: {message.attributes}")
    print(f"   Data length: {len(message.data) if message.data else 0} bytes")
    print(f"=" * 60)
    try:
        data = json.loads(message.data.decode("utf-8"))
        event_id = data.get("event_id")
        user_id = data.get("user_id")  # Use user_id for efficient lookup
        event_data = data.get("event_data", {})
        
        print(f"📧 [EVENT SUBSCRIBER] Parsed message: event_id={event_id}, user_id={user_id}")
        print(f"   Event data: {event_data}")
        
        if not user_id:
            print(f"⚠️  [EVENT SUBSCRIBER] No user_id in message, skipping email")
            message.ack()
            return
        
        # Lookup user email using user_id (efficient PRIMARY KEY lookup)
        # Use asyncio.run in a new event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        print(f"🔍 [EVENT SUBSCRIBER] Looking up user {user_id} from User Service...")
        user = loop.run_until_complete(get_user_by_id(user_id))
        
        if not user:
            print(f"⚠️  [EVENT SUBSCRIBER] User {user_id} not found in User Service, skipping email")
            message.ack()
            return
        
        email_address = user.get("email")
        if not email_address:
            print(f"⚠️  [EVENT SUBSCRIBER] User {user_id} has no email address, skipping email")
            message.ack()
            return
        
        print(f"📬 [EVENT SUBSCRIBER] Preparing email for {email_address}...")
        
        # Send email
        email_body = f"""
        Hi {user.get('first_name', 'User')},
        
        Your event "{event_data.get('title', 'New Event')}" has been successfully created!
        
        Event Details:
        - Title: {event_data.get('title')}
        - Location: {event_data.get('location', 'TBD')}
        - Start: {event_data.get('start_time')}
        - End: {event_data.get('end_time')}
        
        Thank you for using our platform!
        """
        
        email_sent = send_email(
            to=email_address,
            subject=f"Event Created: {event_data.get('title', 'New Event')}",
            body=email_body.strip()
        )
        
        if email_sent:
            print(f"✅ [EVENT SUBSCRIBER] Email sent successfully to {email_address}")
        else:
            print(f"❌ [EVENT SUBSCRIBER] Failed to send email to {email_address}")
        
        message.ack()
        print(f"✅ [EVENT SUBSCRIBER] Message acknowledged")
        
    except json.JSONDecodeError as e:
        print(f"❌ [EVENT SUBSCRIBER] Error decoding message JSON: {e}")
        print(f"   Message data: {message.data.decode('utf-8') if message.data else 'None'}")
        print(f"   Message ID: {message.message_id}")
        message.nack()
        raise  # Re-raise so wrapped_callback can handle it
    except Exception as e:
        print(f"❌ [EVENT SUBSCRIBER] Error processing event notification: {e}")
        print(f"   Message ID: {message.message_id}")
        import traceback
        traceback.print_exc()
        message.nack()
        raise  # Re-raise so wrapped_callback can handle it


def handle_user_created(message: pubsub_v1.subscriber.message.Message):  # type: ignore
    """Handle new user notification - send welcome email"""
    print(f"📨 [USER SUBSCRIBER] Received message: {message.message_id}")
    try:
        data = json.loads(message.data.decode("utf-8"))
        email = data.get("email")
        first_name = data.get("first_name", "User")
        user_id = data.get("user_id")
        firebase_uid = data.get("firebase_uid", "")
        role = data.get("role", "user")
        
        print(f"📧 [USER SUBSCRIBER] Parsed message: user_id={user_id}, email={email}, first_name={first_name}")
        
        if not email:
            print(f"⚠️  [USER SUBSCRIBER] No email in message, skipping welcome email")
            message.ack()
            return
        
        print(f"📬 [USER SUBSCRIBER] Preparing welcome email for {email}...")
        
        # Send welcome email
        email_body = f"""
        Hi {first_name},
        
        Welcome to our platform! We're excited to have you join us.
        
        Get started by:
        - Creating your first event
        - Sharing posts with the community
        - Connecting with friends
        
        Happy exploring!
        
        Best regards,
        The Team
        """
        
        email_sent = send_email(
            to=email,
            subject="Welcome to Our Platform!",
            body=email_body.strip()
        )
        
        if email_sent:
            print(f"✅ [USER SUBSCRIBER] Welcome email sent successfully to {email}")
        else:
            print(f"❌ [USER SUBSCRIBER] Failed to send welcome email to {email}")
        
        message.ack()
        print(f"✅ [USER SUBSCRIBER] Message acknowledged")
        
    except json.JSONDecodeError as e:
        print(f"❌ [USER SUBSCRIBER] Error decoding message JSON: {e}")
        print(f"   Message data: {message.data.decode('utf-8') if message.data else 'None'}")
        message.nack()
    except Exception as e:
        print(f"❌ [USER SUBSCRIBER] Error processing user notification: {e}")
        import traceback
        traceback.print_exc()
        message.nack()


def start_event_subscriber():
    """Start subscriber for event-created topic"""
    if not project_id:
        print("⚠️  GCP_PROJECT_ID not set, event subscriber not started")
        return
    
    try:
        # Load credentials for subscriber
        from dotenv import load_dotenv
        import os
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(dotenv_path=env_path, override=True)
        
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and not os.path.isabs(creds_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            creds_path = os.path.join(base_dir, creds_path)
            if os.path.exists(creds_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
                print(f"📋 [EVENT SUBSCRIBER] Using credentials: {creds_path}")
        
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project_id, EVENT_NOTIFICATION_SUB)
        
        print(f"🚀 [EVENT SUBSCRIBER] Starting subscriber...")
        print(f"   Project: {project_id}")
        print(f"   Subscription: {EVENT_NOTIFICATION_SUB}")
        print(f"   Full path: {subscription_path}")
        
        # Verify subscription exists by trying to get it
        try:
            subscription = subscriber.get_subscription(request={"subscription": subscription_path})
            print(f"✅ [EVENT SUBSCRIBER] Subscription exists and is accessible")
            print(f"   Topic: {subscription.topic}")
        except Exception as e:
            error_msg = str(e)
            if "403" in error_msg or "permission" in error_msg.lower() or "not authorized" in error_msg.lower():
                print(f"⚠️  [EVENT SUBSCRIBER] Warning: Permission denied when verifying subscription")
                print(f"   This is OK - verification requires 'pubsub.subscriptions.get' permission")
                print(f"   Subscribing only needs 'pubsub.subscriptions.consume' (from roles/pubsub.subscriber)")
                print(f"   Subscriber will continue - this should still work...")
            else:
                print(f"⚠️  [EVENT SUBSCRIBER] Warning: Could not verify subscription exists: {e}")
                print(f"   Subscription may not exist. Check GCP Console.")
                print(f"   Continuing anyway - subscription might work...")
        
        # Wrap callback to add error handling
        def wrapped_callback(message: pubsub_v1.subscriber.message.Message):  # type: ignore
            try:
                handle_event_created(message)
            except Exception as e:
                print(f"❌ [EVENT SUBSCRIBER] ERROR in callback handler: {e}")
                import traceback
                traceback.print_exc()
                # Nack the message so it gets redelivered
                message.nack()
        
        streaming_pull_future = subscriber.subscribe(
            subscription_path,
            callback=wrapped_callback
        )
        
        print(f"✅ [EVENT SUBSCRIBER] Subscriber started successfully!")
        print(f"   Waiting for messages from subscription: {EVENT_NOTIFICATION_SUB}")
        print(f"   Callback function registered and ready")
        print(f"   If messages are not being received, check:")
        print(f"   1. Subscription exists in GCP Console")
        print(f"   2. Messages are in the subscription (not just the topic)")
        print(f"   3. Service account has 'pubsub.subscriber' role")
        
        # Keep trying to listen for messages
        print(f"🔄 [EVENT SUBSCRIBER] Entering message listening loop...")
        try:
            # This blocks forever until an exception or KeyboardInterrupt
            streaming_pull_future.result()  # Block forever
        except KeyboardInterrupt:
            print("🛑 [EVENT SUBSCRIBER] Stopping subscriber...")
            streaming_pull_future.cancel()
            try:
                streaming_pull_future.result()
            except:
                pass
        except Exception as e:
            print(f"❌ [EVENT SUBSCRIBER] CRITICAL ERROR in subscriber loop: {e}")
            print(f"   ⚠️  Subscriber thread will exit and stop processing messages!")
            print(f"   This is why event emails are not working!")
            import traceback
            traceback.print_exc()
            try:
                streaming_pull_future.cancel()
            except:
                pass
            # Don't re-raise - just log it clearly
            
    except Exception as e:
        print(f"❌ [EVENT SUBSCRIBER] Failed to start subscriber: {e}")
        print(f"   Project ID: {project_id}")
        print(f"   Subscription: {EVENT_NOTIFICATION_SUB}")
        import traceback
        traceback.print_exc()


def start_user_subscriber():
    """Start subscriber for user-created topic"""
    if not project_id:
        print("⚠️  GCP_PROJECT_ID not set, user subscriber not started")
        return
    
    try:
        # Load credentials for subscriber (same as event subscriber)
        from dotenv import load_dotenv
        import os
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(dotenv_path=env_path, override=True)
        
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path and not os.path.isabs(creds_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            creds_path = os.path.join(base_dir, creds_path)
            if os.path.exists(creds_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        
        subscriber = pubsub_v1.SubscriberClient()
        subscription_path = subscriber.subscription_path(project_id, USER_WELCOME_SUB)
        
        print(f"🚀 [USER SUBSCRIBER] Starting subscriber on {subscription_path}")
        print(f"   Project: {project_id}")
        print(f"   Subscription: {USER_WELCOME_SUB}")
        
        streaming_pull_future = subscriber.subscribe(
            subscription_path,
            callback=handle_user_created
        )
        
        print(f"✅ [USER SUBSCRIBER] Subscriber started successfully, waiting for messages...")
        
        try:
            streaming_pull_future.result()  # Block forever
        except KeyboardInterrupt:
            print("🛑 [USER SUBSCRIBER] Stopping user subscriber...")
            streaming_pull_future.cancel()
            streaming_pull_future.result()
        except Exception as e:
            print(f"❌ [USER SUBSCRIBER] Error in subscriber loop: {e}")
            import traceback
            traceback.print_exc()
            try:
                streaming_pull_future.cancel()
            except:
                pass
    except Exception as e:
        print(f"❌ [USER SUBSCRIBER] Failed to start subscriber: {e}")
        import traceback
        traceback.print_exc()

