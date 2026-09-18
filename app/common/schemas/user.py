from pydantic import BaseModel, EmailStr
from datetime import date, datetime
from app.common.enums import UserRole

class UserOut(BaseModel):
    user_id: int
    username: str
    first_name: str
    last_name: str
    email: EmailStr
    mobile_no: str
    role: UserRole
    dob: date | None = None
    bio: str | None = None
    profile_pic_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True

class ProfileUpdateIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None
    profile_pic_url: str | None = None


