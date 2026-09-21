import re
from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

MOBILE_RE = re.compile(r"^\+?\d{10,15}$")


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
    """Everything the signup form asks for is required here too, so accounts
    can no longer be created through the API with blank / placeholder data."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: str
    last_name: str
    full_name: Optional[str] = None
    mobile_no: str
    role: Literal["influencer", "freelancer"] = "influencer"
    dob: date

    @model_validator(mode="before")
    @classmethod
    def split_full_name(cls, data):
        if isinstance(data, dict):
            first = str(data.get("first_name") or "").strip()
            last = str(data.get("last_name") or "").strip()
            full = str(data.get("full_name") or "").strip()
            if (not first or not last) and full:
                parts = full.split(None, 1)
                first = first or parts[0]
                last = last or (parts[1] if len(parts) > 1 else "")
            data = {**data, "first_name": first, "last_name": last}
        return data

    @field_validator("username")
    @classmethod
    def clean_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters.")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def names_required(cls, v: str, info) -> str:
        v = (v or "").strip()
        label = "First name" if info.field_name == "first_name" else "Last name"
        if not v:
            raise ValueError(f"{label} is required.")
        if len(v) > 100:
            raise ValueError(f"{label} is too long (max 100 characters).")
        return v

    @field_validator("mobile_no")
    @classmethod
    def valid_mobile(cls, v: str) -> str:
        v = (v or "").strip()
        if not MOBILE_RE.match(v):
            raise ValueError("Enter a valid mobile number: 10-15 digits, no spaces or dashes.")
        return v

    @field_validator("dob")
    @classmethod
    def valid_dob(cls, v: date) -> date:
        today = date.today()
        if v > today:
            raise ValueError("Date of birth cannot be in the future.")
        if v.year < today.year - 120:
            raise ValueError("Please enter a valid date of birth.")
        return v


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


class ForgotPasswordRequest(BaseModel):
    identifier: str

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        v = v.strip()
        if "@" in v:
            if "." not in v.split("@")[-1]:
                raise ValueError("Enter a valid email address.")
        else:
            digits = v.replace("+", "").replace(" ", "")
            if not digits.isdigit() or not (7 <= len(digits) <= 15):
                raise ValueError("Enter a valid phone number.")
        return v


class VerifyOtpRequest(BaseModel):
    identifier: str
    otp: str = Field(..., min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    identifier: str
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)