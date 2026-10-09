from datetime import datetime
from typing import Dict, List, Literal, Optional

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


class PostMusic(BaseModel):
    """A song on a post. Same shape is used to send it in and to read it back."""

    music_id: Optional[int] = None
    title: str
    artist: Optional[str] = None
    audio_url: str
    cover_url: Optional[str] = None
    # Where in the song the clip starts, and how long it plays (seconds)
    start_time: float = 0.0
    duration: float = 30.0


class LikerPreview(BaseModel):
    user_id: int
    username: str


class PostOut(BaseModel):
    post_id: int
    author_id: int
    post_type: str
    # "published", "scheduled" or "archived"
    status: str = "published"
    content: Optional[str] = None
    media_type: Optional[str] = None
    # First picture / the video. Kept so older screens keep working.
    media_url: Optional[str] = None
    # Every slide of a carousel, in order (just one entry for a normal photo post).
    media_urls: List[str] = []
    gif_url: Optional[str] = None
    poll: Optional[PollOut] = None
    # All timestamps are ISO-8601 in UTC and end with "Z".
    created_at: str
    # When the post is (or was) due to go live. Null for posts that were never scheduled.
    scheduled_at: Optional[str] = None
    # When the post became visible. Null while it is still scheduled.
    published_at: Optional[str] = None
    can_delete: bool = False

    # Engagement
    # like_count is null when the owner hid it (the owner still sees it).
    like_count: Optional[int] = 0
    likes_hidden: bool = False
    comment_count: int = 0
    share_count: int = 0
    liked_by_me: bool = False
    saved_by_me: bool = False
    # One person the viewer follows who liked this post ("Liked by <name> and others")
    liked_by_preview: Optional[LikerPreview] = None

    # Roles and owner settings
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
    # Send a song to set or replace it, or remove_music=true to take it off.
    music: Optional[PostMusic] = None
    remove_music: bool = False


# ------------------------------------------------------------------ likes
class LikeState(BaseModel):
    liked: bool
    # Null when the owner hid the like count and the caller is not the owner
    like_count: Optional[int] = None


class SaveState(BaseModel):
    saved: bool


class ShareRequest(BaseModel):
    channel: Literal["link", "dm", "other"] = "link"
    # How many people it was sent to (only used for "dm")
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


# --------------------------------------------------------------- comments
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
    # True when the person who wrote the comment is the owner of the post
    by_post_owner: bool = False


class CommentListResponse(BaseModel):
    items: List[CommentOut]
    # Every comment and reply on the post
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


# --------------------------------------------------------------- insights
class InsightsDay(BaseModel):
    date: str
    likes: int = 0
    comments: int = 0


class InsightsOut(BaseModel):
    post_id: int
    status: str
    published_at: Optional[str] = None
    # People who saw the post (the owner is not counted)
    reach: int = 0
    followers_reach: int = 0
    non_followers_reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    # (likes + comments + shares + saves) / reach, in percent. Null until someone has seen it.
    engagement_rate: Optional[float] = None
    poll_votes: Optional[int] = None
    daily: List[InsightsDay] = []