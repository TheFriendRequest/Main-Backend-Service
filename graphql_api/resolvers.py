"""
GraphQL Resolvers - Fetch data from microservices
"""
import httpx
import os
from typing import Optional, List, Dict, Any
from .schema import User, Post, Event, Schedule, Interest


USERS_SERVICE_URL = os.getenv("USERS_SERVICE_URL", "http://localhost:8001")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://localhost:8002")
FEED_SERVICE_URL = os.getenv("FEED_SERVICE_URL", "http://localhost:8004")


async def resolve_user(
    user_id: int,
    include_posts: bool = True,
    include_events: bool = True,
    include_schedules: bool = False,
    include_interests: bool = False,
    posts_limit: int = 5,
    events_limit: int = 5,
    schedules_limit: int = 10
) -> Optional[User]:
    """
    Resolve user with related data from multiple services.
    Fetches data in parallel for performance.
    """
    # Fetch user data
    async with httpx.AsyncClient() as client:
        # Fetch user
        user_resp = await client.get(
            f"{USERS_SERVICE_URL}/users/{user_id}",
            headers={"x-firebase-uid": "system"},  # Internal call
            timeout=10.0
        )
        
        if user_resp.status_code != 200:
            return None
        
        user_data = user_resp.json()
        
        # Prepare parallel requests
        tasks = []
        
        # Fetch posts if requested
        posts_data = []
        if include_posts:
            tasks.append((
                "posts",
                client.get(
                    f"{FEED_SERVICE_URL}/posts/",
                    params={"created_by": user_id, "skip": 0, "limit": posts_limit},
                    headers={"x-firebase-uid": "system"},
                    timeout=10.0
                )
            ))
        
        # Fetch events if requested
        events_data = []
        if include_events:
            tasks.append((
                "events",
                client.get(
                    f"{EVENTS_SERVICE_URL}/events/",
                    params={"created_by": user_id, "skip": 0, "limit": events_limit},
                    headers={"x-firebase-uid": "system"},
                    timeout=10.0
                )
            ))
        
        # Fetch schedules if requested
        schedules_data = []
        if include_schedules:
            tasks.append((
                "schedules",
                client.get(
                    f"{USERS_SERVICE_URL}/users/{user_id}/schedules",
                    headers={"x-firebase-uid": "system"},
                    timeout=10.0
                )
            ))
        
        # Fetch interests if requested
        interests_data = []
        if include_interests:
            tasks.append((
                "interests",
                client.get(
                    f"{USERS_SERVICE_URL}/users/{user_id}/interests",
                    headers={"x-firebase-uid": "system"},
                    timeout=10.0
                )
            ))
        
        # Execute parallel requests
        import asyncio
        results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
        
        # Process results
        for i, (name, _) in enumerate(tasks):
            result = results[i]
            if isinstance(result, Exception):
                print(f"Error fetching {name}: {result}")
                continue
            
            if name == "posts" and result.status_code == 200:
                data = result.json()
                posts_data = data.get("items", []) if isinstance(data, dict) else data
            elif name == "events" and result.status_code == 200:
                data = result.json()
                events_data = data.get("items", []) if isinstance(data, dict) else data
            elif name == "schedules" and result.status_code == 200:
                schedules_data = result.json()
                if not isinstance(schedules_data, list):
                    schedules_data = []
            elif name == "interests" and result.status_code == 200:
                interests_data = result.json()
                if not isinstance(interests_data, list):
                    interests_data = []
        
        # Convert to GraphQL types
        posts = [dict_to_post(post) for post in posts_data] if posts_data else None
        events = [dict_to_event(event) for event in events_data] if events_data else None
        schedules = [dict_to_schedule(schedule) for schedule in schedules_data] if schedules_data else None
        interests = [dict_to_interest(interest) for interest in interests_data] if interests_data else None
        
        return User(
            user_id=user_data.get("user_id"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
            email=user_data.get("email"),
            profile_picture=user_data.get("profile_picture"),
            created_at=str(user_data.get("created_at")) if user_data.get("created_at") else None,
            posts=posts,
            events=events,
            schedules=schedules,
            interests=interests
        )


async def resolve_events(
    skip: int = 0,
    limit: int = 10,
    location: Optional[str] = None,
    created_by: Optional[int] = None
) -> List[Event]:
    """Resolve events from Events Service"""
    params = {"skip": skip, "limit": limit}
    if location:
        params["location"] = location
    if created_by:
        params["created_by"] = created_by
    
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
        events_data = data.get("items", []) if isinstance(data, dict) else data
        
        return [dict_to_event(event) for event in events_data]


async def resolve_posts(
    skip: int = 0,
    limit: int = 10,
    created_by: Optional[int] = None,
    interest_id: Optional[int] = None
) -> List[Post]:
    """Resolve posts from Feed Service"""
    params = {"skip": skip, "limit": limit}
    if created_by:
        params["created_by"] = created_by
    if interest_id:
        params["interest_id"] = interest_id
    
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
        posts_data = data.get("items", []) if isinstance(data, dict) else data
        
        return [dict_to_post(post) for post in posts_data]


# Helper functions to convert dict to GraphQL types
def dict_to_user(data: Dict[str, Any]) -> User:
    return User(
        user_id=data.get("user_id"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        username=data.get("username"),
        email=data.get("email"),
        profile_picture=data.get("profile_picture"),
        created_at=str(data.get("created_at")) if data.get("created_at") else None
    )


def dict_to_post(data: Dict[str, Any]) -> Post:
    # Fetch creator if needed (lazy loading)
    creator = None
    if data.get("created_by"):
        # This would trigger another resolver in a real implementation
        # For now, we can fetch it inline if needed
        pass
    
    interests = None
    if data.get("interests"):
        interests = [dict_to_interest(i) for i in data["interests"]]
    
    return Post(
        post_id=data.get("post_id"),
        title=data.get("title", ""),
        body=data.get("body"),
        image_url=data.get("image_url"),
        created_at=str(data.get("created_at")) if data.get("created_at") else None,
        created_by=data.get("created_by"),
        creator=creator,
        interests=interests
    )


def dict_to_event(data: Dict[str, Any]) -> Event:
    creator = None
    interests = None
    if data.get("interests"):
        interests = [dict_to_interest(i) for i in data["interests"]]
    
    return Event(
        event_id=data.get("event_id"),
        title=data.get("title", ""),
        description=data.get("description"),
        location=data.get("location"),
        start_time=str(data.get("start_time")) if data.get("start_time") else None,
        end_time=str(data.get("end_time")) if data.get("end_time") else None,
        capacity=data.get("capacity"),
        created_at=str(data.get("created_at")) if data.get("created_at") else None,
        created_by=data.get("created_by"),
        creator=creator,
        interests=interests
    )


def dict_to_schedule(data: Dict[str, Any]) -> Schedule:
    return Schedule(
        schedule_id=data.get("schedule_id"),
        title=data.get("title", ""),
        start_time=str(data.get("start_time")) if data.get("start_time") else None,
        end_time=str(data.get("end_time")) if data.get("end_time") else None,
        type=data.get("type"),
        created_at=str(data.get("created_at")) if data.get("created_at") else None
    )


def dict_to_interest(data: Dict[str, Any]) -> Interest:
    return Interest(
        interest_id=data.get("interest_id"),
        interest_name=data.get("interest_name", "")
    )

