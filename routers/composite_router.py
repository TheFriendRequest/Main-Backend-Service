from fastapi import APIRouter, HTTPException, Depends, status, Query, Header, Response, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List, cast
from datetime import datetime
import httpx
import threading
import os
import mysql.connector
import json
import uuid
import time
from pydantic import BaseModel
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth import get_firebase_uid, get_verified_token

router = APIRouter(prefix="/api", tags=["Composite"])

# ----------------------
# Configuration
# ----------------------
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://localhost:8001")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://localhost:8002")
FEED_SERVICE_URL = os.getenv("FEED_SERVICE_URL", "http://localhost:8003")

# ----------------------
# Task Database Connection
# ----------------------
def get_task_db_connection():
    """Get connection to task database for async task tracking"""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASS", os.getenv("DB_PASSWORD", "admin")),
        database=os.getenv("TASK_DB_NAME", "task_db"),
        use_pure=True,
        port=3306,
        auth_plugin='mysql_native_password',
    )

# ----------------------
# Task Lock for thread safety
# ----------------------
task_lock = threading.Lock()

# ----------------------
# Helper: Extract Authorization header (for forwarding to atomic services)
# ----------------------
def get_auth_header(request: Request) -> Optional[str]:
    """Extract authorization header for forwarding to atomic services"""
    return request.headers.get("Authorization") or request.headers.get("authorization")


# ----------------------
# Helper: Forward request to atomic service
# ----------------------
async def forward_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict] = None,
    params: Optional[Dict] = None,
    response_obj: Optional[Response] = None
) -> Any:
    """Forward HTTP request to atomic service"""
    try:
        async with httpx.AsyncClient() as client:
            http_response = await client.request(
                method=method,
                url=url,
                headers=headers or {},
                json=json_data,
                params=params,
                timeout=30.0
            )
            # Log response status before raising
            if http_response.status_code >= 400:
                print(f"[Composite Service] Atomic service returned error: {http_response.status_code}")
                print(f"[Composite Service] Response text: {http_response.text[:500]}")
                print(f"[Composite Service] Response headers: {dict(http_response.headers)}")
            
            http_response.raise_for_status()
            # Forward ETag header if present
            if response_obj:
                etag = http_response.headers.get("ETag") or http_response.headers.get("etag")
                print(f"[Composite Service] Received ETag from atomic service: {etag}")
                if etag:
                    response_obj.headers["ETag"] = etag
                    print(f"[Composite Service] Forwarded ETag to client: {response_obj.headers.get('ETag')}")
                else:
                    print(f"[Composite Service] No ETag found in atomic service response")
                    print(f"[Composite Service] Available headers: {list(http_response.headers.keys())}")
            if not http_response.content:
                return [] if method == "GET" else {}
            
            # Try to parse JSON and log it
            try:
                result = http_response.json()
                print(f"[Composite Service] Successfully parsed response from {url}: type={type(result)}, is_list={isinstance(result, list)}")
                if isinstance(result, list) and len(result) > 0:
                    print(f"[Composite Service] First item: {result[0]}")
                return result
            except Exception as e:
                print(f"[Composite Service] Error parsing JSON response: {e}")
                print(f"[Composite Service] Response content: {http_response.text[:500]}")
                raise
    except httpx.HTTPStatusError as e:
        # Re-raise with more context
        error_detail = f"Atomic service error: {e.response.status_code}"
        try:
            error_body = e.response.json()
            if "detail" in error_body:
                error_detail = error_body["detail"]
        except:
            error_detail = e.response.text or str(e)
        raise HTTPException(status_code=e.response.status_code, detail=error_detail)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to atomic service: {str(e)}")


# ----------------------
# Helper: Get user_id from firebase_uid via User Service
# ----------------------
async def get_user_id_from_firebase_uid(firebase_uid: str, auth_header: Optional[str], decoded_token: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """
    Get user_id from User Service using firebase_uid.
    If user doesn't exist and decoded_token is provided, attempts to auto-sync the user.
    """
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USERS_SERVICE_URL}/users/me",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                user = response.json()
                return user.get("user_id")
            
            # If user not found and we have token info, try to auto-sync
            if response.status_code == 404 and decoded_token:
                print(f"[Composite Service] User not found, attempting auto-sync for firebase_uid: {firebase_uid}")
                # Firebase token typically has: email, name, picture at root level
                email = decoded_token.get("email") or ""
                name = decoded_token.get("name") or ""
                picture = decoded_token.get("picture") or None
                
                if email:
                    # Extract first/last name from name or email
                    name_parts = name.split() if name else []
                    first_name = name_parts[0] if name_parts else email.split("@")[0]
                    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
                    username = email.split("@")[0]
                    
                    # Try to sync user
                    sync_data = {
                        "first_name": first_name,
                        "last_name": last_name,
                        "username": username,
                        "email": email,
                        "profile_picture": picture
                    }
                    
                    print(f"[Composite Service] Auto-syncing user with data: {sync_data}")
                    sync_response = await client.post(
                        f"{USERS_SERVICE_URL}/users/sync",
                        headers=headers,
                        json=sync_data,
                        timeout=10.0
                    )
                    
                    if sync_response.status_code in [200, 201]:
                        result = sync_response.json()
                        print(f"[Composite Service] Auto-synced user successfully: {result.get('user_id')}")
                        return result.get("user_id")
                    else:
                        try:
                            error_text = sync_response.text
                        except:
                            error_text = "Unknown error"
                        print(f"[Composite Service] Auto-sync failed: {sync_response.status_code} - {error_text}")
        
        return None
    except Exception as e:
        print(f"[Composite Service] Error getting user_id from firebase_uid: {e}")
        return None


# ----------------------
# Helper: Ensure local user exists (create if needed)
# ----------------------
async def ensure_local_user(firebase_uid: str, auth_header: Optional[str], user_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Ensure local user exists, create if needed. Returns user_id."""
    # First try to get existing user
    user_id = await get_user_id_from_firebase_uid(firebase_uid, auth_header)
    if user_id:
        return user_id
    
    # If user doesn't exist and we have user_data, create it
    if user_data:
        try:
            headers = {}
            if auth_header:
                headers["Authorization"] = auth_header
            headers["Content-Type"] = "application/json"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{USERS_SERVICE_URL}/users/sync",
                    headers=headers,
                    json=user_data,
                    timeout=10.0
                )
                if response.status_code in [200, 201]:
                    result = response.json()
                    return result.get("user_id")
        except Exception as e:
            print(f"[Composite Service] Error creating user: {e}")
    
    return None


# ----------------------
# Helper: Validate logical foreign key constraints
# ----------------------
async def validate_user_exists(user_id: int, auth_header: Optional[str]) -> bool:
    """Validate that a user exists (logical FK constraint)"""
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USERS_SERVICE_URL}/users/",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                users = response.json()
                return any(u.get("user_id") == user_id for u in users)
        return False
    except Exception:
        return False


async def validate_event_exists(event_id: int, auth_header: Optional[str]) -> bool:
    """Validate that an event exists (logical FK constraint)"""
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{EVENTS_SERVICE_URL}/events/{event_id}",
                headers=headers,
                timeout=10.0
            )
            return response.status_code == 200
    except Exception:
        return False


async def validate_post_exists(post_id: int, auth_header: Optional[str]) -> bool:
    """Validate that a post exists (logical FK constraint)"""
    try:
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{FEED_SERVICE_URL}/posts/{post_id}",
                headers=headers,
                timeout=10.0
            )
            return response.status_code == 200
    except Exception:
        return False


# ----------------------
# Composite Models
# ----------------------
class UserFeedResponse(BaseModel):
    user: Dict[str, Any]
    posts: List[Dict[str, Any]]
    events: List[Dict[str, Any]]


class UserEventPostResponse(BaseModel):
    user_id: int
    user: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = []
    posts: List[Dict[str, Any]] = []


# ----------------------
# Composite Endpoints - Parallel Execution
# ----------------------
@router.get("/users/{user_id}/feed", response_model=UserFeedResponse)
async def get_user_feed(
    user_id: int,
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    skip_posts: int = Query(0, ge=0),
    limit_posts: int = Query(10, ge=1, le=100),
    skip_events: int = Query(0, ge=0),
    limit_events: int = Query(10, ge=1, le=100)
):
    """
    Get user feed with posts and events in parallel.
    Demonstrates thread-based parallel execution.
    Implements logical FK constraint: validates user exists.
    """
    authorization = get_auth_header(request)
    # Validate user exists (logical FK constraint)
    if not await validate_user_exists(user_id, authorization):
        raise HTTPException(status_code=404, detail="User not found")
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    # Results storage
    results = {"user": None, "posts": [], "events": []}
    errors = {}
    
    # Thread function for fetching user
    def fetch_user():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{USERS_SERVICE_URL}/users/",
                        headers=headers,
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        users = resp.json()
                        for u in users:
                            if u.get("user_id") == user_id:
                                results["user"] = u
                                break
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["user"] = str(e)
    
    # Thread function for fetching posts
    def fetch_posts():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{FEED_SERVICE_URL}/posts/",
                        headers=headers,
                        params={"created_by": user_id, "skip": skip_posts, "limit": limit_posts},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results["posts"] = data.get("items", [])
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["posts"] = str(e)
    
    # Thread function for fetching events
    def fetch_events():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{EVENTS_SERVICE_URL}/events/",
                        headers=headers,
                        params={"created_by": user_id, "skip": skip_events, "limit": limit_events},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results["events"] = data.get("items", [])
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["events"] = str(e)
    
    # Execute in parallel using threads
    threads = [
        threading.Thread(target=fetch_user),
        threading.Thread(target=fetch_posts),
        threading.Thread(target=fetch_events)
    ]
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    # Check for errors
    if errors:
        raise HTTPException(
            status_code=500,
            detail=f"Errors fetching data: {errors}"
        )
    
    if not results["user"]:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserFeedResponse(
        user=results["user"],
        posts=results["posts"],
        events=results["events"]
    )


@router.get("/users/{user_id}/activity", response_model=UserEventPostResponse)
async def get_user_activity(
    user_id: int,
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Get all user activity (events and posts) in parallel.
    Demonstrates thread-based parallel execution.
    Implements logical FK constraint: validates user exists.
    """
    authorization = get_auth_header(request)
    # Validate user exists (logical FK constraint)
    if not await validate_user_exists(user_id, authorization):
        raise HTTPException(status_code=404, detail="User not found")
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    results = {"user": None, "events": [], "posts": []}
    errors = {}
    
    # Thread function for fetching user
    def fetch_user():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{USERS_SERVICE_URL}/users/",
                        headers=headers,
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        users = resp.json()
                        for u in users:
                            if u.get("user_id") == user_id:
                                results["user"] = u
                                break
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["user"] = str(e)
    
    # Thread function for fetching all events
    def fetch_events():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{EVENTS_SERVICE_URL}/events/",
                        headers=headers,
                        params={"created_by": user_id, "limit": 100},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results["events"] = data.get("items", [])
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["events"] = str(e)
    
    # Thread function for fetching all posts
    def fetch_posts():
        try:
            async def _fetch():
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{FEED_SERVICE_URL}/posts/",
                        headers=headers,
                        params={"created_by": user_id, "limit": 100},
                        timeout=10.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results["posts"] = data.get("items", [])
            import asyncio
            asyncio.run(_fetch())
        except Exception as e:
            errors["posts"] = str(e)
    
    # Execute in parallel using threads
    threads = [
        threading.Thread(target=fetch_user),
        threading.Thread(target=fetch_events),
        threading.Thread(target=fetch_posts)
    ]
    
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()
    
    if errors:
        raise HTTPException(
            status_code=500,
            detail=f"Errors fetching data: {errors}"
        )
    
    return UserEventPostResponse(
        user_id=user_id,
        user=results["user"],
        events=results["events"],
        posts=results["posts"]
    )


# ----------------------
# Composite Endpoints - Delegating to Atomic Services
# ----------------------
@router.get("/users/me")
async def get_current_user(
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service - Get current authenticated user"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    result = await forward_request(
        "GET",
        f"{USERS_SERVICE_URL}/users/me",
        headers=headers,
        response_obj=response
    )
    # Return JSONResponse with headers from the Response object
    response_headers = dict(response.headers)
    return JSONResponse(content=result, headers=response_headers)


@router.post("/users/sync", status_code=status.HTTP_201_CREATED)
async def sync_user(
    user_data: Dict[str, Any],
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service - Sync Firebase user to database"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    result = await forward_request(
        "POST",
        f"{USERS_SERVICE_URL}/users/sync",
        headers=headers,
        json_data=user_data
    )
    
    return result


@router.get("/users")
async def get_users(
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    return await forward_request(
        "GET",
        f"{USERS_SERVICE_URL}/users/",
        headers=headers,
        params={"skip": skip, "limit": limit} if skip or limit else None
    )

@router.get("/users/interests")
async def get_interests(
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service - Get all available interests"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    try:
        result = await forward_request(
            "GET",
            f"{USERS_SERVICE_URL}/users/interests",
            headers=headers
        )
        # Ensure we return a list - use JSONResponse to avoid FastAPI validation issues
        if isinstance(result, list):
            return JSONResponse(content=result)
        elif isinstance(result, dict) and "items" in result:
            return JSONResponse(content=result["items"])
        else:
            return JSONResponse(content=[])
    except HTTPException as e:
        print(f"[Composite Service] Error in get_interests: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        print(f"[Composite Service] Unexpected error in get_interests: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    # Get all users and find the one with matching user_id
    users = await forward_request(
        "GET",
        f"{USERS_SERVICE_URL}/users/",
        headers=headers
    )
    
    if isinstance(users, list):
        for user in users:
            if isinstance(user, dict) and user.get("user_id") == user_id:
                return user
    
    raise HTTPException(status_code=404, detail="User not found")


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: Dict[str, Any],
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    return await forward_request(
        "PUT",
        f"{USERS_SERVICE_URL}/users/{user_id}",
        headers=headers,
        json_data=user_data
    )


@router.get("/users/{user_id}/schedules")
async def get_user_schedules(
    user_id: int,
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    result = await forward_request(
        "GET",
        f"{USERS_SERVICE_URL}/users/{user_id}/schedules",
        headers=headers,
        response_obj=response
    )
    # Return JSONResponse with headers from the Response object
    response_headers = dict(response.headers)
    return JSONResponse(content=result, headers=response_headers)


@router.post("/users/{user_id}/schedules", status_code=status.HTTP_201_CREATED)
async def create_user_schedule(
    user_id: int,
    schedule: Dict[str, Any],
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    result = await forward_request(
        "POST",
        f"{USERS_SERVICE_URL}/users/{user_id}/schedules",
        headers=headers,
        json_data=schedule
    )
    
    if "schedule_id" in result:
        response.headers["Location"] = f"/api/users/{user_id}/schedules/{result['schedule_id']}"
    
    return result


@router.delete("/users/{user_id}/schedules/{schedule_id}")
async def delete_user_schedule(
    user_id: int,
    schedule_id: int,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    return await forward_request(
        "DELETE",
        f"{USERS_SERVICE_URL}/users/{user_id}/schedules/{schedule_id}",
        headers=headers
    )


@router.get("/users/{user_id}/interests")
async def get_user_interests(
    user_id: int,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    return await forward_request(
        "GET",
        f"{USERS_SERVICE_URL}/users/{user_id}/interests",
        headers=headers
    )


@router.post("/users/{user_id}/interests", status_code=status.HTTP_201_CREATED)
async def update_user_interests(
    user_id: int,
    interest_ids: List[int],
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Users Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    # Forward as JSON body (interest_ids is a list, not a dict)
    async with httpx.AsyncClient() as client:
        response_http = await client.post(
            f"{USERS_SERVICE_URL}/users/{user_id}/interests",
            headers=headers,
            json=interest_ids,
            timeout=30.0
        )
        response_http.raise_for_status()
        return response_http.json() if response_http.content else {}


@router.get("/events")
async def get_events(
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    location: Optional[str] = None,
    created_by: Optional[int] = None
):
    """Delegate to Events Service with query parameters"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if location:
        params["location"] = location
    if created_by:
        params["created_by"] = created_by
    
    result = await forward_request(
        "GET",
        f"{EVENTS_SERVICE_URL}/events/",
        headers=headers,
        params=params,
        response_obj=response
    )
    # Return JSONResponse with headers from the Response object
    response_headers = dict(response.headers)
    return JSONResponse(content=result, headers=response_headers)


@router.get("/events/{event_id}")
async def get_event(
    event_id: int,
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    if_none_match: Optional[str] = Header(None, alias="If-None-Match")
):
    """Delegate to Events Service with eTag support"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    if if_none_match:
        headers["If-None-Match"] = if_none_match
    
    async with httpx.AsyncClient() as client:
        http_response = await client.get(
            f"{EVENTS_SERVICE_URL}/events/{event_id}",
            headers=headers,
            timeout=10.0
        )
        if http_response.status_code == 304:
            # Forward ETag header from atomic service
            etag = http_response.headers.get("ETag") or http_response.headers.get("etag")
            response_obj = Response(status_code=304)
            if etag:
                response_obj.headers["ETag"] = etag
            return response_obj
        
        http_response.raise_for_status()
        # Forward ETag header from atomic service
        etag = http_response.headers.get("ETag") or http_response.headers.get("etag")
        response_headers = {}
        if etag:
            response_headers["ETag"] = etag
        content = http_response.json() if http_response.content else {}
        return JSONResponse(content=content, headers=response_headers)


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_event(
    event: Dict[str, Any],
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    decoded_token: dict = Depends(get_verified_token)  # Get full token for auto-sync
):
    """
    Create event - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service (auto-sync if needed)
    3. Pass user_id to Event Service as created_by
    4. Enforce logical FK constraint
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service (auto-syncs if user doesn't exist)
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization, decoded_token)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please complete your profile setup first by visiting your profile page."
        )
    
    # Add created_by to event data
    event["created_by"] = user_id
    # Note: No need to call validate_user_exists - get_user_id_from_firebase_uid already confirms user exists
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    result = await forward_request(
        "POST",
        f"{EVENTS_SERVICE_URL}/events/",
        headers=headers,
        json_data=event
    )
    
    if "event_id" in result:
        response.headers["Location"] = f"/api/events/{result['event_id']}"
    
    return result


@router.post("/events/async", status_code=status.HTTP_202_ACCEPTED)
async def create_event_async(
    event: Dict[str, Any],
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    decoded_token: dict = Depends(get_verified_token)  # Get full token for auto-sync
):
    """
    Create event asynchronously - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service (auto-sync if needed)
    3. Pass user_id to Event Service as created_by
    4. Returns 202 Accepted with task ID for polling
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service (auto-syncs if user doesn't exist)
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization, decoded_token)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please complete your profile setup first by visiting your profile page."
        )
    
    # Add created_by to event data
    event["created_by"] = user_id
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    # Forward to Event Service async endpoint
    result = await forward_request(
        "POST",
        f"{EVENTS_SERVICE_URL}/events/async",
        headers=headers,
        json_data=event,
        response_obj=response
    )
    
    # Forward Location header if present
    if "task_id" in result:
        response.headers["Location"] = f"/api/events/tasks/{result['task_id']}"
    
    return result


@router.get("/events/tasks/{task_id}")
async def get_event_task_status(
    task_id: str,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Poll the status of an async event creation task.
    Forwards to Event Service which stores tasks in event_db.
    """
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    # Forward to Event Service task status endpoint (tasks stored in event_db)
    return await forward_request(
        "GET",
        f"{EVENTS_SERVICE_URL}/events/tasks/{task_id}",
        headers=headers
    )


@router.put("/events/{event_id}")
async def update_event(
    event_id: int,
    event_data: Dict[str, Any],
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Update event - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service
    3. Pass user_id to Event Service as query parameter for authorization
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please sync your account first."
        )
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    # Pass user_id as query parameter for authorization check in Event Service
    params = {"created_by": user_id}
    
    return await forward_request(
        "PUT",
        f"{EVENTS_SERVICE_URL}/events/{event_id}",
        headers=headers,
        json_data=event_data,
        params=params
    )


@router.get("/posts")
async def get_posts(
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level (for logging/audit)
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    interest_id: Optional[int] = None,
    created_by: Optional[int] = None
):
    """Delegate to Feed Service with query parameters"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if interest_id:
        params["interest_id"] = interest_id
    if created_by:
        params["created_by"] = created_by
    
    result = await forward_request(
        "GET",
        f"{FEED_SERVICE_URL}/posts/",
        headers=headers,
        params=params,
        response_obj=response
    )
    # Return JSONResponse with headers from the Response object
    response_headers = dict(response.headers)
    return JSONResponse(content=result, headers=response_headers)

@router.get("/posts/interests")
async def get_post_interests(
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Feed Service - Get all available interests for posts"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    try:
        result = await forward_request(
            "GET",
            f"{FEED_SERVICE_URL}/posts/interests/",
            headers=headers
        )
        # Ensure we return a list - use JSONResponse to avoid FastAPI validation issues
        if isinstance(result, list):
            return JSONResponse(content=result)
        elif isinstance(result, dict) and "items" in result:
            return JSONResponse(content=result["items"])
        else:
            return JSONResponse(content=[])
    except HTTPException as e:
        print(f"[Composite Service] Error in get_post_interests: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        print(f"[Composite Service] Unexpected error in get_post_interests: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/posts/{post_id}")
async def get_post(
    post_id: int,
    request: Request,
    response: Response,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """Delegate to Feed Service"""
    authorization = get_auth_header(request)
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    result = await forward_request(
        "GET",
        f"{FEED_SERVICE_URL}/posts/{post_id}",
        headers=headers,
        response_obj=response
    )
    # Return JSONResponse with headers from the Response object
    response_headers = dict(response.headers)
    return JSONResponse(content=result, headers=response_headers)


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    post: Dict[str, Any],
    response: Response,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid),  # Authentication at composite level
    decoded_token: dict = Depends(get_verified_token)  # Get full token for auto-sync
):
    """
    Create post - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service (auto-sync if needed)
    3. Pass user_id to Feed Service as created_by
    4. Enforce logical FK constraint
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service (auto-syncs if user doesn't exist)
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization, decoded_token)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please complete your profile setup first by visiting your profile page."
        )
    
    # Add created_by to post data
    post["created_by"] = user_id
    # Note: No need to call validate_user_exists - get_user_id_from_firebase_uid already confirms user exists
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    result = await forward_request(
        "POST",
        f"{FEED_SERVICE_URL}/posts/",
        headers=headers,
        json_data=post
    )
    
    if "post_id" in result:
        response.headers["Location"] = f"/api/posts/{result['post_id']}"
    
    return result


@router.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    post_data: Dict[str, Any],
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Update post - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service
    3. Pass user_id to Feed Service as query parameter for authorization
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please sync your account first."
        )
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    headers["Content-Type"] = "application/json"
    
    # Pass user_id as query parameter for authorization check in Feed Service
    params = {"created_by": user_id}
    
    return await forward_request(
        "PUT",
        f"{FEED_SERVICE_URL}/posts/{post_id}",
        headers=headers,
        json_data=post_data,
        params=params
    )


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: int,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Delete event - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service
    3. Pass user_id to Event Service as query parameter for authorization
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please sync your account first."
        )
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    # Pass user_id as query parameter for authorization check in Event Service
    params = {"created_by": user_id}
    
    return await forward_request(
        "DELETE",
        f"{EVENTS_SERVICE_URL}/events/{event_id}",
        headers=headers,
        params=params
    )


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    request: Request,
    firebase_uid: str = Depends(get_firebase_uid)  # Authentication at composite level
):
    """
    Delete post - Composite Service workflow:
    1. Validate Firebase token → firebase_uid
    2. Get user_id from User Service
    3. Pass user_id to Feed Service as query parameter for authorization
    """
    authorization = get_auth_header(request)
    
    # Get user_id from User Service
    user_id = await get_user_id_from_firebase_uid(firebase_uid, authorization)
    if not user_id:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please sync your account first."
        )
    
    headers: Dict[str, str] = {}
    if authorization:
        headers["Authorization"] = authorization
    
    # Pass user_id as query parameter for authorization check in Feed Service
    params = {"created_by": user_id}
    
    return await forward_request(
        "DELETE",
        f"{FEED_SERVICE_URL}/posts/{post_id}",
        headers=headers,
        params=params
    )

