"""
Firebase Authentication Middleware and Utilities for Composite Service
"""
from fastapi import HTTPException, Depends, Header
from typing import Optional
import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv

# Load .env file
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path, override=True)

# Initialize Firebase Admin SDK
_firebase_initialized = False

try:
    # Check if already initialized
    if len(firebase_admin._apps) > 0:
        _firebase_initialized = True
        print("Firebase Admin already initialized in Composite Service")
    else:
        # Try default serviceAccountKey.json in current directory first (most common case)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        default_path = os.path.join(current_dir, 'serviceAccountKey.json')
        
        if os.path.exists(default_path):
            try:
                cred = credentials.Certificate(default_path)
                firebase_admin.initialize_app(cred)
                _firebase_initialized = True
                print("✅ Firebase Admin initialized with serviceAccountKey.json in Composite Service")
            except Exception as e:
                print(f"❌ Error initializing Firebase with serviceAccountKey.json: {e}")
        else:
            print(f"⚠️  serviceAccountKey.json not found at: {default_path}")
        
        # If default didn't work, try environment variable
        if not _firebase_initialized:
            service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
            if service_account_path:
                # Convert relative path to absolute path
                if not os.path.isabs(service_account_path):
                    service_account_path = os.path.join(current_dir, service_account_path)
                
                if os.path.exists(service_account_path):
                    try:
                        cred = credentials.Certificate(service_account_path)
                        firebase_admin.initialize_app(cred)
                        _firebase_initialized = True
                        print(f"✅ Firebase Admin initialized with service account from env: {service_account_path}")
                    except Exception as e:
                        print(f"❌ Error initializing Firebase with env path: {e}")
                else:
                    print(f"⚠️  Firebase service account file not found: {service_account_path}")
        
        # If still not initialized, try Application Default Credentials
        if not _firebase_initialized:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            if project_id:
                try:
                    firebase_admin.initialize_app()
                    _firebase_initialized = True
                    print("✅ Firebase Admin initialized with Application Default Credentials in Composite Service")
                except Exception as e:
                    print(f"❌ Error initializing Firebase with ADC: {e}")
        
        if not _firebase_initialized:
            print("❌ Firebase initialization FAILED in Composite Service")
            print("   Please ensure serviceAccountKey.json exists in Main-Backend-Service/ directory")
            print("   Or set FIREBASE_SERVICE_ACCOUNT_PATH environment variable")
            
except Exception as e:
    print(f"❌ Firebase initialization error in Composite Service: {e}")
    import traceback
    traceback.print_exc()
    _firebase_initialized = False


async def verify_firebase_token(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> dict:
    """
    Verify Firebase ID token from Authorization header.
    Returns the decoded token with user information.
    This is the authentication gatekeeper for the composite service.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing"
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )
    
    try:
        # Check if Firebase is initialized
        if len(firebase_admin._apps) == 0:
            raise HTTPException(
                status_code=500,
                detail="Firebase Admin SDK not initialized. Please check server logs and ensure serviceAccountKey.json exists."
            )
        
        # Verify the token
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Firebase token expired"
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid Firebase token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token verification failed: {str(e)}"
        )


def get_firebase_uid(decoded_token: dict = Depends(verify_firebase_token)) -> str:
    """
    Extract Firebase UID from decoded token.
    Use this as a dependency in your routes.
    """
    uid = decoded_token.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Firebase token missing UID")
    return uid


def get_verified_token(decoded_token: dict = Depends(verify_firebase_token)) -> dict:
    """
    Get the full decoded token for forwarding to atomic services.
    Use this when you need to pass the token to downstream services.
    """
    return decoded_token

