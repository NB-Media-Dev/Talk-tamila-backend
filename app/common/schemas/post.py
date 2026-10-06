from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


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
    content: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    gif_url: Optional[str] = None
    poll: Optional[PollOut] = None
    created_at: str  # ISO-8601 in UTC, ends with "Z"
    can_delete: bool = False

    model_config = ConfigDict(from_attributes=True)


class FeedResponse(BaseModel):
    items: List[PostOut]
    # Authors are sent once here (not inside every post) because avatars are large.
    authors: Dict[int, PostAuthor]
    has_more: bool = False
    next_before_id: Optional[int] = None


class VoteRequest(BaseModel):
    option_id: int

