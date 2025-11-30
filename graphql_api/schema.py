"""
GraphQL Schema for User Feed/Activity Aggregation
Using Strawberry GraphQL for type-safe schema definition
"""
import strawberry
from typing import List, Optional
from datetime import datetime
from typing_extensions import Annotated


@strawberry.type
class User:
    """User type"""
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: Optional[str] = None
    
    # Resolved fields
    posts: Optional[List["Post"]] = None
    events: Optional[List["Event"]] = None
    schedules: Optional[List["Schedule"]] = None
    interests: Optional[List["Interest"]] = None


@strawberry.type
class Post:
    """Post type"""
    post_id: int
    title: str
    body: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[str] = None
    created_by: int
    
    # Resolved fields (from resolver)
    creator: Optional[User] = None
    interests: Optional[List["Interest"]] = None


@strawberry.type
class Event:
    """Event type"""
    event_id: int
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    capacity: Optional[int] = None
    created_at: Optional[str] = None
    created_by: int
    
    # Resolved fields (from resolver)
    creator: Optional[User] = None
    interests: Optional[List["Interest"]] = None


@strawberry.type
class Schedule:
    """Schedule type"""
    schedule_id: int
    title: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[str] = None


@strawberry.type
class Interest:
    """Interest type"""
    interest_id: int
    interest_name: str


@strawberry.input
class PaginationInput:
    """Pagination input"""
    skip: int = 0
    limit: int = 10


@strawberry.type
class Query:
    """Root Query type"""
    
    @strawberry.field
    async def user(
        self,
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
        Get user with optional related data (posts, events, schedules, interests).
        Uses resolvers to fetch from multiple services.
        """
        from .resolvers import resolve_user
        
        return await resolve_user(
            user_id=user_id,
            include_posts=include_posts,
            include_events=include_events,
            include_schedules=include_schedules,
            include_interests=include_interests,
            posts_limit=posts_limit,
            events_limit=events_limit,
            schedules_limit=schedules_limit
        )
    
    @strawberry.field
    async def events(
        self,
        skip: int = 0,
        limit: int = 10,
        location: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> List[Event]:
        """Get events with optional filters"""
        from .resolvers import resolve_events
        
        return await resolve_events(
            skip=skip,
            limit=limit,
            location=location,
            created_by=created_by
        )
    
    @strawberry.field
    async def posts(
        self,
        skip: int = 0,
        limit: int = 10,
        created_by: Optional[int] = None,
        interest_id: Optional[int] = None
    ) -> List[Post]:
        """Get posts with optional filters"""
        from .resolvers import resolve_posts
        
        return await resolve_posts(
            skip=skip,
            limit=limit,
            created_by=created_by,
            interest_id=interest_id
        )


# Create GraphQL schema
schema = strawberry.Schema(query=Query)

