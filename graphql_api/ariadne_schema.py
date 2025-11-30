"""
GraphQL Schema using Ariadne (more stable than Strawberry)
"""
from ariadne import QueryType, MutationType, make_executable_schema, gql
from ariadne.asgi import GraphQL
from typing import Dict, Any, List, Optional
import httpx
import os

# Type definitions
type_defs = gql("""
    type User {
        user_id: Int!
        first_name: String
        last_name: String
        username: String
        email: String
        profile_picture: String
        created_at: String
        posts: [Post!]
        events: [Event!]
        schedules: [Schedule!]
        interests: [Interest!]
    }
    
    type Post {
        post_id: Int!
        title: String!
        body: String
        image_url: String
        created_at: String
        created_by: Int!
        creator: User
        interests: [Interest!]
    }
    
    type Event {
        event_id: Int!
        title: String!
        description: String
        location: String
        start_time: String
        end_time: String
        capacity: Int
        created_at: String
        created_by: Int!
        creator: User
        interests: [Interest!]
    }
    
    type Schedule {
        schedule_id: Int!
        title: String!
        start_time: String
        end_time: String
        type: String
        created_at: String
    }
    
    type Interest {
        interest_id: Int!
        interest_name: String!
    }
    
    input EventInput {
        title: String!
        description: String
        location: String
        start_time: String!
        end_time: String!
        capacity: Int
    }
    
    input PostInput {
        title: String!
        body: String
        image_url: String
        interest_ids: [Int!]
    }
    
    type Mutation {
        createEvent(input: EventInput!): Event!
        createPost(input: PostInput!): Post!
    }
    
    type Query {
        user(
            userId: Int!,
            includePosts: Boolean = true,
            includeEvents: Boolean = true,
            includeSchedules: Boolean = false,
            includeInterests: Boolean = false,
            postsLimit: Int = 5,
            eventsLimit: Int = 5,
            schedulesLimit: Int = 10
        ): User
        events(
            skip: Int = 0,
            limit: Int = 10,
            location: String,
            createdBy: Int
        ): [Event!]!
        posts(
            skip: Int = 0,
            limit: Int = 10,
            createdBy: Int,
            interestId: Int
        ): [Post!]!
        event(eventId: Int!): Event
        post(postId: Int!): Post
    }
""")

# Initialize query and mutation types
query = QueryType()
mutation = MutationType()

# Service URLs
USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://localhost:8001")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://localhost:8002")
FEED_SERVICE_URL = os.getenv("FEED_SERVICE_URL", "http://localhost:8004")


async def fetch_user_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetch user data from Users Service"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{USERS_SERVICE_URL}/users/{user_id}",
            headers={"x-firebase-uid": "system"},
            timeout=10.0
        )
        if resp.status_code == 200:
            return resp.json()
        return None


@query.field("user")
async def resolve_user(
    obj: Any,
    info: Any,
    userId: int,
    includePosts: bool = True,
    includeEvents: bool = True,
    includeSchedules: bool = False,
    includeInterests: bool = False,
    postsLimit: int = 5,
    eventsLimit: int = 5,
    schedulesLimit: int = 10
) -> Optional[Dict[str, Any]]:
    """Resolve user query"""
    user_data = await fetch_user_data(userId)
    if not user_data:
        return None
    
    # Fetch related data in parallel if requested
    tasks = []
    async with httpx.AsyncClient() as client:
        if includePosts:
            tasks.append(client.get(
                f"{FEED_SERVICE_URL}/posts/",
                params={"created_by": userId, "skip": 0, "limit": postsLimit},
                headers={"x-firebase-uid": "system"},
                timeout=10.0
            ))
        
        if includeEvents:
            tasks.append(client.get(
                f"{EVENTS_SERVICE_URL}/events/",
                params={"created_by": userId, "skip": 0, "limit": eventsLimit},
                headers={"x-firebase-uid": "system"},
                timeout=10.0
            ))
        
        if includeSchedules:
            tasks.append(client.get(
                f"{USERS_SERVICE_URL}/users/{userId}/schedules",
                headers={"x-firebase-uid": "system"},
                timeout=10.0
            ))
        
        if includeInterests:
            tasks.append(client.get(
                f"{USERS_SERVICE_URL}/users/{userId}/interests",
                headers={"x-firebase-uid": "system"},
                timeout=10.0
            ))
        
        # Execute all requests in parallel
        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    posts_data = []
    events_data = []
    schedules_data = []
    interests_data = []
    
    result_idx = 0
    if includePosts:
        result = results[result_idx]
        if isinstance(result, httpx.Response) and result.status_code == 200:
            data = result.json()
            posts_data = data.get("items", []) if isinstance(data, dict) else data
        result_idx += 1
    
    if includeEvents:
        result = results[result_idx]
        if isinstance(result, httpx.Response) and result.status_code == 200:
            data = result.json()
            events_data = data.get("items", []) if isinstance(data, dict) else data
        result_idx += 1
    
    if includeSchedules:
        result = results[result_idx]
        if isinstance(result, httpx.Response) and result.status_code == 200:
            schedules_data = result.json()
            if not isinstance(schedules_data, list):
                schedules_data = []
        result_idx += 1
    
    if includeInterests:
        result = results[result_idx]
        if isinstance(result, httpx.Response) and result.status_code == 200:
            interests_data = result.json()
            if not isinstance(interests_data, list):
                interests_data = []
    
    # Build response
    response = user_data.copy()
    if includePosts:
        response["posts"] = posts_data
    if includeEvents:
        response["events"] = events_data
    if includeSchedules:
        response["schedules"] = schedules_data
    if includeInterests:
        response["interests"] = interests_data
    
    return response


@query.field("events")
async def resolve_events(
    obj: Any,
    info: Any,
    skip: int = 0,
    limit: int = 10,
    location: Optional[str] = None,
    createdBy: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Resolve events query"""
    # HTTP query parameters must be strings
    params: Dict[str, str] = {"skip": str(skip), "limit": str(limit)}
    if location:
        params["location"] = location
    if createdBy:
        params["created_by"] = str(createdBy)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{EVENTS_SERVICE_URL}/events/",
            params=params,
            headers={"x-firebase-uid": "system"},
            timeout=10.0
        )
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        return data.get("items", []) if isinstance(data, dict) else data


@query.field("posts")
async def resolve_posts(
    obj: Any,
    info: Any,
    skip: int = 0,
    limit: int = 10,
    createdBy: Optional[int] = None,
    interestId: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Resolve posts query"""
    # HTTP query parameters must be strings
    params: Dict[str, str] = {"skip": str(skip), "limit": str(limit)}
    if createdBy:
        params["created_by"] = str(createdBy)
    if interestId:
        params["interest_id"] = str(interestId)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{FEED_SERVICE_URL}/posts/",
            params=params,
            headers={"x-firebase-uid": "system"},
            timeout=10.0
        )
        
        if resp.status_code != 200:
            return []
        
        data = resp.json()
        return data.get("items", []) if isinstance(data, dict) else data


# Mutation resolvers
@mutation.field("createEvent")
async def resolve_create_event(
    obj: Any,
    info: Any,
    input: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new event"""
    # Get firebase_uid from GraphQL context (set by main.py)
    request = info.context.get("request")
    firebase_uid = info.context.get("firebase_uid")
    
    if not firebase_uid and request:
        # Try to get from request headers (set by API Gateway middleware)
        firebase_uid = request.headers.get("x-firebase-uid") or request.headers.get("X-Firebase-Uid")
        if not firebase_uid:
            # Try to get from request state (if set by middleware)
            firebase_uid = getattr(request.state, "firebase_uid", None)
    
    if not firebase_uid:
        raise Exception("Authentication required - x-firebase-uid header missing")
    
    # Get user_id from User Service (auto-sync if needed)
    async with httpx.AsyncClient() as client:
        # Get current user to get user_id
        user_resp = await client.get(
            f"{USERS_SERVICE_URL}/users/me",
            headers={"x-firebase-uid": firebase_uid},
            timeout=10.0
        )
        
        if user_resp.status_code != 200:
            raise Exception("User not found. Please sync your account first.")
        
        user_data = user_resp.json()
        user_id = user_data.get("user_id")
        
        if not user_id:
            raise Exception("User ID not found")
        
        # Prepare event data
        event_data = {
            "title": input["title"],
            "description": input.get("description"),
            "location": input.get("location"),
            "start_time": input["start_time"],
            "end_time": input["end_time"],
            "capacity": input.get("capacity"),
            "created_by": user_id
        }
        
        # Create event via Event Service REST endpoint
        event_resp = await client.post(
            f"{EVENTS_SERVICE_URL}/events/",
            headers={"x-firebase-uid": firebase_uid, "Content-Type": "application/json"},
            json=event_data,
            timeout=10.0
        )
        
        if event_resp.status_code != 201:
            error_detail = "Failed to create event"
            try:
                error_data = event_resp.json()
                error_detail = error_data.get("detail", error_detail)
            except:
                error_detail = f"{event_resp.status_code} {event_resp.reason_phrase or 'Unknown error'}"
            raise Exception(error_detail)
        
        return event_resp.json()


@mutation.field("createPost")
async def resolve_create_post(
    obj: Any,
    info: Any,
    input: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new post"""
    # Get firebase_uid from GraphQL context
    request = info.context.get("request")
    firebase_uid = info.context.get("firebase_uid")
    
    if not firebase_uid and request:
        firebase_uid = request.headers.get("x-firebase-uid") or request.headers.get("X-Firebase-Uid")
        if not firebase_uid:
            firebase_uid = getattr(request.state, "firebase_uid", None)
    
    if not firebase_uid:
        raise Exception("Authentication required - x-firebase-uid header missing")
    
    # Get user_id from User Service
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{USERS_SERVICE_URL}/users/me",
            headers={"x-firebase-uid": firebase_uid},
            timeout=10.0
        )
        
        if user_resp.status_code != 200:
            raise Exception("User not found. Please sync your account first.")
        
        user_data = user_resp.json()
        user_id = user_data.get("user_id")
        
        if not user_id:
            raise Exception("User ID not found")
        
        # Prepare post data
        post_data = {
            "title": input["title"],
            "body": input.get("body"),
            "image_url": input.get("image_url"),
            "interest_ids": input.get("interest_ids", [])
        }
        
        # Create post via Feed Service REST endpoint
        post_resp = await client.post(
            f"{FEED_SERVICE_URL}/posts/",
            headers={"x-firebase-uid": firebase_uid, "Content-Type": "application/json"},
            json=post_data,
            timeout=10.0
        )
        
        if post_resp.status_code != 201:
            error_detail = "Failed to create post"
            try:
                error_data = post_resp.json()
                error_detail = error_data.get("detail", error_detail)
            except:
                error_detail = f"{post_resp.status_code} {post_resp.reason_phrase or 'Unknown error'}"
            raise Exception(error_detail)
        
        return post_resp.json()


@query.field("event")
async def resolve_event(
    obj: Any,
    info: Any,
    eventId: int
) -> Optional[Dict[str, Any]]:
    """Get a single event by ID"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{EVENTS_SERVICE_URL}/events/{eventId}",
            headers={"x-firebase-uid": "system"},
            timeout=10.0
        )
        
        if resp.status_code != 200:
            return None
        
        return resp.json()


@query.field("post")
async def resolve_post(
    obj: Any,
    info: Any,
    postId: int
) -> Optional[Dict[str, Any]]:
    """Get a single post by ID"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{FEED_SERVICE_URL}/posts/{postId}",
            headers={"x-firebase-uid": "system"},
            timeout=10.0
        )
        
        if resp.status_code != 200:
            return None
        
        return resp.json()


# Create executable schema with both query and mutation
schema = make_executable_schema(type_defs, query, mutation)

