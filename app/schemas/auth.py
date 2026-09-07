from pydantic import BaseModel, EmailStr
from datetime import date
from app.schemas.user import UserOut
from app.models.user import UserRole

class TokenOut(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class RegisterIn(BaseModel):
    username: str
    first_name:str
    last_name: str
    email: EmailStr
    mobile_no: str
    password: str
    dob: date | None = None
    role: UserRole = UserRole.influencer
