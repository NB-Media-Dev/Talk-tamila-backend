from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class PostAuthor(BaseModel):
    user_id: int
    name: str
    username: str
    role: str
    avatar_url: Optional[str] = None


class PollOptionOut(BaseModel):
    option_id: int
    text: str
    votes: int = 0


class PollOut(BaseModel):
    options: List[PollOptionOut]
    total_votes: int = 0
    my_vote_option_id: Optional[int] = None


class PostOut(BaseModel):
    post_id: int
    author_id: int
    post_type: str
    # "published" or "scheduled"
    status: str = "published"
    content: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    gif_url: Optional[str] = None
    poll: Optional[PollOut] = None
    # All timestamps are ISO-8601 in UTC and end with "Z".
    created_at: str
    # When the post is (or was) due to go live. Null for posts that were never scheduled.
    scheduled_at: Optional[str] = None
    # When the post became visible. Null while it is still scheduled.
    published_at: Optional[str] = None
    can_delete: bool = False

    model_config = ConfigDict(from_attributes=True)


class FeedResponse(BaseModel):
    items: List[PostOut]
    authors: Dict[int, PostAuthor]
    has_more: bool = False
    next_before_id: Optional[int] = None


class ScheduledListResponse(BaseModel):
    items: List[PostOut]
    authors: Dict[int, PostAuthor]
    total: int
    limit: int
    offset: int


class VoteRequest(BaseModel):
    option_id: int


class ScheduleRequest(BaseModel):
    """Body for PATCH /posts/{id}/schedule."""

    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "scheduled_at must include a timezone, e.g. 2026-10-10T18:30:00+05:30 or ...Z"
            )
        return value