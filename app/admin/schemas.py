from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.common.schemas.story import StoryUserResponse


class AdminOverview(BaseModel):
    total_users: int = 0
    total_stories: int = 0
    active_stories: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_reports: int = 0


class AdminPlatformStoryStats(BaseModel):
    total_stories: int = 0
    active_stories: int = 0
    expired_stories: int = 0
    deleted_stories: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_replies: int = 0
    total_shares: int = 0
    total_reports: int = 0


class AdminStoryItem(BaseModel):
    id: int
    story_id: int
    user_id: int
    author_id: int
    media_url: str
    media_type: str = "image"
    caption: Optional[str] = None
    content: Optional[str] = None
    audience: str = "PUBLIC"
    created_at: str
    expires_at: Optional[str] = None
    is_deleted: bool = False
    is_active: bool = True
    views_count: int = 0
    likes_count: int = 0
    replies_count: int = 0
    shares_count: int = 0
    reports_count: int = 0
    user: Optional[StoryUserResponse] = None
    model_config = ConfigDict(from_attributes=True)


class AdminReportItem(BaseModel):
    report_id: int
    story_id: int
    user_id: int
    reporter_username: Optional[str] = None
    reason: str
    created_at: str
    story: Optional[AdminStoryItem] = None
    model_config = ConfigDict(from_attributes=True)

