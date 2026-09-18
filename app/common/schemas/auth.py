from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional[dict] = None


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None
    type: Optional[str] = None


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    username_or_email: Optional[str] = None
    password: str


class RegisterRequest(BaseModel):
    username: Optional[str] = None
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = ""
    full_name: Optional[str] = None
    mobile_no: Optional[str] = None
    role: Literal["admin", "influencer", "freelancer"] = "influencer"
    dob: Optional[date] = None


class UserResponse(BaseModel):
    id: int
    user_id: int
    username: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    mobile_no: str
    role: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    followers_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)