"""
Helper functions for Composite Service
"""
from fastapi import Request, HTTPException
from typing import Optional


def get_firebase_uid_from_request(request: Request) -> str:
    """
    Extract firebase_uid from request state (set by middleware).
    Raises 401 if not found.
    """
    firebase_uid = getattr(request.state, "firebase_uid", None)
    if not firebase_uid:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. firebase_uid not found in request."
        )
    return firebase_uid


def get_email_from_request(request: Request) -> Optional[str]:
    """Extract email from request state (set by middleware)"""
    return getattr(request.state, "email", None)


def get_role_from_request(request: Request) -> str:
    """Extract role from request state (set by middleware), defaults to 'user'"""
    return getattr(request.state, "role", "user")


def prepare_headers_for_downstream(request: Request, additional_headers: Optional[dict] = None) -> dict:
    """
    Prepare headers for forwarding to downstream services.
    Includes x-firebase-uid from request state.
    """
    headers = {}
    
    # Add x-firebase-uid from request state (set by middleware)
    firebase_uid = getattr(request.state, "firebase_uid", None)
    if firebase_uid:
        headers["x-firebase-uid"] = firebase_uid
    
    # Add any additional headers
    if additional_headers:
        headers.update(additional_headers)
    
    # Always set Content-Type for JSON
    headers["Content-Type"] = "application/json"
    
    return headers

