from pydantic import BaseModel, EmailStr, Field
from datetime import date
from typing import Literal
from app.common.schemas.user import UserOut

class RegisterIn(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: EmailStr
    mobile_no: str
    password: str
    role: Literal["influencer", "freelancer", "admin"] = "influencer"
    dob: date | None = None

class TokenOut(BaseModel):
    access_token: str
    token_type: str
    user: UserOut