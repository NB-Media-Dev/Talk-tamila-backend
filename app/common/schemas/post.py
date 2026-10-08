from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PostAuthorInfo(BaseModel):
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "admin"
    avatar_url: Optional[str] = None
    location: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PostCreateRequest(BaseModel):
    title: Optional[str] = None
    caption: Optional[str] = None
    media_type: str = Field(default="image", description="image | video | text | poll")
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: Optional[float] = None
    platforms: Optional[List[str]] = Field(default_factory=lambda: ["Talk Tamila"])
    tags: Optional[List[str]] = Field(default_factory=list)
    poll_data: Optional[Dict[str, Any]] = None
    audience: str = "PUBLIC"
    status: str = "published"
    location: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class PostUpdateRequest(BaseModel):
    title: Optional[str] = None
    caption: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: Optional[float] = None
    platforms: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    location: Optional[str] = None


class PostCommentRequest(BaseModel):
    comment_text: str = Field(..., min_length=1)
    parent_comment_id: Optional[int] = None


class PostCommentResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    comment_text: str
    parent_comment_id: Optional[int] = None
    is_hidden: Optional[bool] = False
    created_at: str
    created_at_human: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PostShareRequest(BaseModel):
    platform: Optional[str] = "Talk Tamila"


class PostItemResponse(BaseModel):
    id: int
    post_id: int
    user_id: int
    author_id: int
    username: Optional[str] = None
    title: Optional[str] = None
    caption: Optional[str] = None
    content: Optional[str] = None
    media_type: str = "image"
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: Optional[float] = None
    platforms: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    poll_data: Optional[Dict[str, Any]] = None
    audience: str = "PUBLIC"
    status: str = "published"
    location: Optional[str] = None
    scheduled_at: Optional[str] = None
    views_count: int = 0
    likes_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    saves_count: int = 0
    is_liked: bool = False
    is_saved: bool = False
    created_at: str
    created_at_human: Optional[str] = None
    author: PostAuthorInfo
    analytics: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(from_attributes=True)


class PostFeedResponse(BaseModel):
    items: List[PostItemResponse]
    total: int


class PostPlatformStats(BaseModel):
    total_posts: int = 0
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    total_shares: int = 0
    total_saves: int = 0
