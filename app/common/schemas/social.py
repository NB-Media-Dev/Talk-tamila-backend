from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProfileResponse(BaseModel):
    profile_id: int
    user_id: int
    profile_pic_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    posts_count: int = 0
    account_type: str = "influencer"
    total_reach: int = 0
    total_earned: float = 0.0

    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    message: Optional[str] = None
    reference_id: Optional[int] = None
    is_read: bool = False
    created_at: str

    model_config = ConfigDict(from_attributes=True)
