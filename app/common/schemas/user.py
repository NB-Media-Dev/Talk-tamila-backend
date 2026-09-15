from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    mobile_no: str
    role: str = "influencer"
    dob: Optional[date] = None


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    avatar_url: Optional[str] = None


class UserOut(UserBase):
    id: int
    user_id: int
    full_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    followers_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
