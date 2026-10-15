from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class PostMusic(BaseModel):
    """A song on a post. Same shape is used to send it in and to read it back."""

    music_id: Optional[int] = None
    title: str
    artist: Optional[str] = None
    audio_url: str
    cover_url: Optional[str] = None
    start_time: float = 0.0
    duration: float = 30.0


class LikerPreview(BaseModel):
    user_id: int
    username: str


class PostOut(BaseModel):
    post_id: int
    author_id: int
    post_type: str
    status: str = "published"
    content: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    gif_url: Optional[str] = None
    poll: Optional[PollOut] = None
    created_at: str
    scheduled_at: Optional[str] = None
    published_at: Optional[str] = None
    can_delete: bool = False
    like_count: Optional[int] = 0
    likes_hidden: bool = False
    comment_count: int = 0
    share_count: int = 0
    liked_by_me: bool = False
    saved_by_me: bool = False
    shared_by_me: bool = False
    liked_by_preview: Optional[LikerPreview] = None
    is_owner: bool = False
    can_edit: bool = False
    following_author: bool = False
    comments_disabled: bool = False
    hide_like_count: bool = False
    is_pinned: bool = False
    edited_at: Optional[str] = None
    music: Optional[PostMusic] = None

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


class PostEditRequest(BaseModel):
    """Body for PATCH /posts/{id}. Only the fields that are sent are changed."""

    content: Optional[str] = None
    comments_disabled: Optional[bool] = None
    hide_like_count: Optional[bool] = None
    music: Optional[PostMusic] = None
    remove_music: bool = False


class LikeState(BaseModel):
    liked: bool
    like_count: Optional[int] = None


class SaveState(BaseModel):
    saved: bool


class ShareRequest(BaseModel):
    channel: Literal["link", "dm", "other"] = "link"
    recipients: int = 1


class ShareState(BaseModel):
    share_count: int


class ReportRequest(BaseModel):
    reason: str


class PostUserOut(BaseModel):
    user_id: int
    username: str
    name: str
    avatar_url: Optional[str] = None
    role: Optional[str] = None


class LikersResponse(BaseModel):
    items: List[PostUserOut]
    total: int


class CommentCreate(BaseModel):
    body: str
    parent_id: Optional[int] = None


class CommentOut(BaseModel):
    comment_id: int
    post_id: int
    parent_id: Optional[int] = None
    body: str
    created_at: str
    author: PostAuthor
    like_count: int = 0
    liked_by_me: bool = False
    reply_count: int = 0
    can_delete: bool = False
    by_post_owner: bool = False


class CommentListResponse(BaseModel):
    items: List[CommentOut]
    total: int = 0
    has_more: bool = False
    next_cursor: Optional[int] = None
    comments_disabled: bool = False


class CommentLikeState(BaseModel):
    liked: bool
    like_count: int


class CommentDeleteResult(BaseModel):
    success: bool = True
    comment_id: int
    comment_count: int


class InsightsDay(BaseModel):
    date: str
    likes: int = 0
    comments: int = 0


class InsightsOut(BaseModel):
    post_id: int
    status: str
    published_at: Optional[str] = None
    reach: int = 0
    followers_reach: int = 0
    non_followers_reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    engagement_rate: Optional[float] = None
    poll_votes: Optional[int] = None
    daily: List[InsightsDay] = Field(default_factory=list)
  