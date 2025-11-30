"""
Pub/Sub Publishers for Composite Service
Note: Event and User services publish directly, but Composite Service
can also publish if needed for composite-level events
"""
from google.cloud import pubsub_v1  # type: ignore
from google.auth import default as google_auth_default  # type: ignore
from google.auth.exceptions import DefaultCredentialsError  # type: ignore
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path, override=True)

project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))

# Initialize publisher client with explicit credential handling
publisher = None
_publisher_initialized = False

def _ensure_publisher_initialized():
    """Ensure publisher client is initialized with proper credentials"""
    global publisher, _publisher_initialized
    
    if _publisher_initialized and publisher is not None:
        return True
    
    try:
        # Try to use GOOGLE_APPLICATION_CREDENTIALS first
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path:
            # Convert relative path to absolute
            if not os.path.isabs(creds_path):
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                creds_path = os.path.join(base_dir, creds_path)
            
            if os.path.exists(creds_path):
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
                print(f"[PUBLISHER] Using credentials from: {creds_path}")
            else:
                print(f"[WARNING] [PUBLISHER] Credentials file not found: {creds_path}")
        
        # Initialize publisher (will use GOOGLE_APPLICATION_CREDENTIALS or ADC)
        publisher = pubsub_v1.PublisherClient()
        
        # Test credentials by checking project
        if project_id:
            # Try to get topic path to verify credentials work
            try:
                test_path = publisher.topic_path(project_id, "test")
                print(f"[OK] [PUBLISHER] Publisher client initialized successfully")
                print(f"   Project ID: {project_id}")
                _publisher_initialized = True
                return True
            except Exception as e:
                print(f"[ERROR] [PUBLISHER] Failed to initialize publisher (credentials issue): {e}")
                publisher = None
                return False
        else:
            print(f"[WARNING] [PUBLISHER] GCP_PROJECT_ID not set, publisher may not work")
            _publisher_initialized = True
            return True
            
    except DefaultCredentialsError as e:
        print(f"[ERROR] [PUBLISHER] No credentials found: {e}")
        print(f"   Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        publisher = None
        return False
    except Exception as e:
        print(f"[ERROR] [PUBLISHER] Error initializing publisher: {e}")
        import traceback
        traceback.print_exc()
        publisher = None
        return False

# Initialize on module load
_ensure_publisher_initialized()

# Topic names
EVENT_CREATED_TOPIC = os.getenv("PUBSUB_EVENT_CREATED_TOPIC", "event-created")
USER_CREATED_TOPIC = os.getenv("PUBSUB_USER_CREATED_TOPIC", "user-created")


def _get_topic_path(topic_name: str) -> str:
    """Get full topic path for a topic name"""
    if not project_id:
        raise ValueError(
            "GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable must be set"
        )
    if publisher is None:
        raise RuntimeError("Publisher client not initialized")
    return publisher.topic_path(project_id, topic_name)


def publish_event_created(
    event_id: int,
    user_id: int,
    event_data: Dict[str, Any]
) -> Optional[str]:
    """
    Publish event creation message to Pub/Sub.
    Uses user_id for efficient email lookups.
    """
    print(f"[PUBLISHER] publish_event_created called: event_id={event_id}, user_id={user_id}")
    
    # Ensure publisher is initialized
    if not _ensure_publisher_initialized():
        print("[ERROR] [PUBLISHER] Publisher not initialized, cannot publish")
        return None
    
    if not project_id:
        print("[WARNING] [PUBLISHER] GCP_PROJECT_ID not set, skipping Pub/Sub publish")
        return None
    
    try:
        topic_path = _get_topic_path(EVENT_CREATED_TOPIC)
    except Exception as e:
        print(f"[ERROR] [PUBLISHER] Failed to get topic path: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    message_payload = {
        "event_type": "event.created",
        "event_id": event_id,
        "user_id": user_id,  # Use user_id for efficient lookup
        "event_data": event_data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    message_data = json.dumps(message_payload, default=str).encode("utf-8")
    
    try:
        print(f"[PUBLISHER] Publishing to topic: {topic_path}")
        print(f"   Topic name: {EVENT_CREATED_TOPIC}")
        print(f"   Project: {project_id}")
        print(f"   Payload keys: {list(message_payload.keys())}")
        print(f"   Event ID: {event_id}, User ID: {user_id}")
        
        if publisher is None:
            print("[ERROR] [PUBLISHER] Publisher client is None, cannot publish")
            return None
        
        # Type guard: publisher is not None at this point
        assert publisher is not None
        future = publisher.publish(topic_path, message_data)
        print(f"[PUBLISHER] Waiting for publish result...")
        message_id = future.result(timeout=10)  # Increased timeout
        
        print(f"[SUCCESS] [PUBLISHER] Published event-created message successfully!")
        print(f"   Message ID: {message_id}")
        print(f"   Topic: {EVENT_CREATED_TOPIC}")
        print(f"   Event ID: {event_id}, User ID: {user_id}")
        return message_id
    except Exception as e:
        print(f"[ERROR] [PUBLISHER] Failed to publish event-created: {e}")
        print(f"   Topic path: {topic_path}")
        print(f"   Project ID: {project_id}")
        print(f"   Publisher initialized: {_publisher_initialized}")
        print(f"   Publisher client: {publisher}")
        import traceback
        traceback.print_exc()
        return None


def publish_user_created(
    user_id: int,
    firebase_uid: str,
    email: str,
    first_name: str,
    role: str = "user"
) -> Optional[str]:
    """
    Publish user creation message to Pub/Sub.
    """
    print(f"🚀 [PUBLISHER] publish_user_created called: user_id={user_id}, email={email}")
    
    # Ensure publisher is initialized
    if not _ensure_publisher_initialized():
        print("❌ [PUBLISHER] Publisher not initialized, cannot publish")
        return None
    
    if not project_id:
        print("⚠️  [PUBLISHER] GCP_PROJECT_ID not set, skipping Pub/Sub publish")
        return None
    
    try:
        topic_path = _get_topic_path(USER_CREATED_TOPIC)
    except Exception as e:
        print(f"❌ [PUBLISHER] Failed to get topic path: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    message_payload = {
        "event_type": "user.created",
        "user_id": user_id,
        "firebase_uid": firebase_uid,
        "email": email,
        "first_name": first_name,
        "role": role,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    message_data = json.dumps(message_payload).encode("utf-8")
    
    try:
        print(f"📤 [PUBLISHER] Publishing to topic: {topic_path}")
        print(f"   Topic name: {USER_CREATED_TOPIC}")
        print(f"   Project: {project_id}")
        print(f"   User ID: {user_id}, Email: {email}")
        
        if publisher is None:
            print("❌ [PUBLISHER] Publisher client is None, cannot publish")
            return None
        
        # Type guard: publisher is not None at this point
        assert publisher is not None
        future = publisher.publish(topic_path, message_data)
        message_id = future.result(timeout=10)  # Increased timeout
        
        print(f"✅ [PUBLISHER] Published user-created message successfully!")
        print(f"   Message ID: {message_id}")
        print(f"   Topic: {USER_CREATED_TOPIC}")
        print(f"   User ID: {user_id}, Email: {email}")
        return message_id
    except Exception as e:
        print(f"❌ [PUBLISHER] Failed to publish user-created: {e}")
        print(f"   Topic path: {topic_path}")
        print(f"   Project ID: {project_id}")
        print(f"   Publisher initialized: {_publisher_initialized}")
        import traceback
        traceback.print_exc()
        return None

