from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StorySlideResponse(BaseModel):
    id: int
    imageUrl: str
    media_url: Optional[str] = None
    media_type: str = "image"
    caption: Optional[str] = None
    duration: int = 5000  # ms for auto-advance progress bar
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    liked: bool = False
    likes_count: int = 0
    views_count: int = 0
    shares_count: int = 0
    replies_count: int = 0
    musicTrack: Optional[str] = None
    music_url: Optional[str] = None
    replyPlaceholder: str = "Reply..."
    model_config = ConfigDict(from_attributes=True)


class StoryUserResponse(BaseModel):
    id: int
    user_id: int
    userName: str
    username: str
    avatar: Optional[str] = None
    avatar_url: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "influencer"
    verified: bool = True
    model_config = ConfigDict(from_attributes=True)


class StoryItemResponse(BaseModel):
    story_id: int
    id: int
    user_id: int
    media_url: str
    imageUrl: Optional[str] = None
    media_type: str = "image"
    created_at: str
    expires_at: str
    caption: Optional[str] = None
    audience: str = "public"
    is_active: bool = True
    has_active_story: bool = True
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_duration: Optional[float] = 60.0
    music_start_time: Optional[float] = 0.0
    likes_count: int = 0
    replies_count: int = 0
    views_count: int = 0
    shares_count: int = 0
    viewed_by_me: bool = False
    liked_by_me: bool = False
    user: Optional[StoryUserResponse] = None
    model_config = ConfigDict(from_attributes=True)


class StoryGroupResponse(BaseModel):
    id: int
    user: StoryUserResponse
    userName: str
    avatar: Optional[str] = None
    verified: bool = True
    role: str = "influencer"
    timeAgo: str = "Just now"
    musicTrack: Optional[str] = None
    slides: List[StorySlideResponse] = []
    stories: List[StoryItemResponse] = []
    stories_count: int = 0
    latest_story_created_at: str = ""
    is_my_story: bool = False
    all_viewed: bool = False
    has_unseen_stories: bool = True
    has_active_story: bool = True
    media_url: Optional[str] = None
    story_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


class StoryBatchResponse(BaseModel):
    success: bool
    message: str
    total_published: int
    stories: List[StoryItemResponse]


class ActivityViewer(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    full_name: Optional[str] = None
    viewed_at: str


class ActivityLiker(BaseModel):
    user_id: int
    username: str
    avatar_url: Optional[str] = None
    full_name: Optional[str] = None


class StoryActivityResponse(BaseModel):
    story_id: int
    total_views: int
    total_likes: int
    liked_by_me: bool
    viewers: List[ActivityViewer]
    likers: List[ActivityLiker]


class StoryReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class StoryReplyResponse(BaseModel):
    reply_id: int
    story_id: int
    user_id: int
    text: str
    created_at: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None


class StoryShareRequest(BaseModel):
    platform: Optional[str] = "copy_link"
    target_user_id: Optional[int] = None


class StoryShareResponse(BaseModel):
    success: bool
    message: str
    story_id: int
    shares_count: int
    share_url: str


class StoryReportRequest(BaseModel):
    reason: str = Field(..., min_length=2, max_length=255)
    details: Optional[str] = None


class StoryPauseRequest(BaseModel):
    action: str = Field(default="pause", pattern="^(pause|resume)$")
    progress_ms: Optional[int] = Field(default=None, ge=0)
    slide_index: Optional[int] = Field(default=None, ge=0)


class StoryMuteResponse(BaseModel):
    success: bool
    message: str
    muted_user_id: int
    is_muted: bool


class StoryJsonCreateRequest(BaseModel):
    media_url: str = Field(..., min_length=1)
    media_type: Optional[str] = "image"
    caption: Optional[str] = None
    audience: Optional[str] = "public"
    duration_hours: Optional[int] = Field(default=24, ge=1, le=72)
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_duration: Optional[float] = 60.0
    music_start_time: Optional[float] = 0.0


# ── New schemas ───────────────────────────────────────────────────────────────

class StoryPatchRequest(BaseModel):
    """Edit caption and/or audience of an existing story (owner only)."""
    caption: Optional[str] = Field(default=None, max_length=2200)
    audience: Optional[str] = Field(default=None, pattern="^(public|followers|close_friends)$")


class StoryReactRequest(BaseModel):
    """Emoji reaction to a story (e.g. ❤️ 🔥 😂)."""
    emoji: str = Field(..., min_length=1, max_length=10)


class StoryReactResponse(BaseModel):
    success: bool
    story_id: int
    emoji: str
    message: str


class StoryViewerItem(BaseModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    viewed_at: str


class StoryLikerItem(BaseModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    liked_at: str


class PaginatedViewerResponse(BaseModel):
    story_id: int
    total_views: int
    page: int
    page_size: int
    viewers: List[StoryViewerItem]


class PaginatedLikerResponse(BaseModel):
    story_id: int
    total_likes: int
    page: int
    page_size: int
    likers: List[StoryLikerItem]


class StoryStatsResponse(BaseModel):
    """Aggregate engagement stats across ALL stories owned by the current user."""
    user_id: int
    total_stories: int
    total_views: int
    total_likes: int
    total_replies: int
    total_shares: int
    active_stories: int
    expired_stories: int


class StoryArchivedItem(BaseModel):
    story_id: int
    id: int
    media_url: str
    media_type: str
    caption: Optional[str] = None
    created_at: str
    expired_at: str
    views_count: int
    likes_count: int


class StoryWithMetrics(BaseModel):
    """Story enriched with engagement metrics for role-specific dashboards."""
    story_id: int
    id: int
    media_url: str
    media_type: str
    caption: Optional[str] = None
    audience: str
    created_at: str
    expires_at: str
    is_active: bool
    views_count: int
    likes_count: int
    replies_count: int
    shares_count: int
    engagement_rate: float = 0.0
    model_config = ConfigDict(from_attributes=True)
