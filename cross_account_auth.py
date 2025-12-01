"""
Cross-Account Authentication Helper
For Composite Service to authenticate with services in other GCP accounts
"""
import os
import time
from typing import Optional, Any
import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import id_token

# Cache for identity tokens to avoid regenerating on every request
_token_cache: dict[str, tuple[str, float]] = {}
_token_cache_ttl = 300  # 5 minutes


def get_identity_token(target_url: str) -> str:
    """
    Get identity token for authenticating to Cloud Run services in other GCP accounts.
    
    Args:
        target_url: The URL of the target Cloud Run service
        
    Returns:
        Identity token as a string
    """
    # Check cache first
    if target_url in _token_cache:
        token, timestamp = _token_cache[target_url]
        if time.time() - timestamp < _token_cache_ttl:
            return token
    
    try:
        # Get default credentials
        credentials, _ = google.auth.default()
        request = Request()
        
        # Refresh credentials if needed
        # Use try-except to handle different credential types safely
        try:
            # Try to refresh credentials - this works for most credential types
            if hasattr(credentials, 'refresh'):
                # Check if credentials need refreshing
                if hasattr(credentials, 'valid'):
                    # Type checker doesn't know about 'valid', so use getattr
                    is_valid = getattr(credentials, 'valid', True)
                    if not is_valid:
                        credentials.refresh(request)  # type: ignore
                else:
                    # No 'valid' attribute, try refreshing anyway
                    credentials.refresh(request)  # type: ignore
        except (AttributeError, Exception):
            # If refresh fails or attribute doesn't exist, continue anyway
            # The credentials might still be valid
            pass
        
        # Get identity token for the target service
        target_audience = target_url
        id_token_obj: Any = id_token.fetch_id_token(request, target_audience)
        
        # Ensure we have a string token
        if not id_token_obj or not isinstance(id_token_obj, str):
            print(f"[Cross-Account Auth] Invalid token type received for {target_url}")
            return ""
        
        # Cache the token
        _token_cache[target_url] = (id_token_obj, time.time())
        
        return id_token_obj
    except Exception as e:
        print(f"[Cross-Account Auth] Error getting identity token for {target_url}: {e}")
        import traceback
        traceback.print_exc()
        # Fallback: return empty string (will fail auth, but won't crash)
        return ""


def should_use_identity_token(service_url: str) -> bool:
    """
    Determine if we should use identity token authentication.
    Only use for Cloud Run services (not localhost or VM IPs).
    """
    # Use identity token for Cloud Run URLs
    if ".run.app" in service_url or "run.googleapis.com" in service_url:
        return True
    # Don't use for localhost or direct IPs
    if "localhost" in service_url or service_url.startswith("http://10.") or service_url.startswith("http://192.168."):
        return False
    return True


def get_auth_headers(service_url: str, firebase_uid: Optional[str] = None, original_auth: Optional[str] = None) -> dict[str, str]:
    """
    Get authentication headers for calling a service.
    Uses identity token for Cloud Run services in other accounts.
    
    Args:
        service_url: URL of the target service
        firebase_uid: Firebase UID to forward
        original_auth: Original Authorization header (if any)
        
    Returns:
        Dictionary of headers to use
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json"
    }
    
    # Add Firebase UID
    if firebase_uid:
        headers["x-firebase-uid"] = firebase_uid
    
    # Add authentication
    if should_use_identity_token(service_url):
        # Use identity token for Cloud Run services
        identity_token = get_identity_token(service_url)
        if identity_token:
            headers["Authorization"] = f"Bearer {identity_token}"
        elif original_auth:
            # Fallback to original auth if identity token fails
            headers["Authorization"] = original_auth
    else:
        # For VM or localhost, use original auth or no auth
        if original_auth:
            headers["Authorization"] = original_auth
    
    return headers

