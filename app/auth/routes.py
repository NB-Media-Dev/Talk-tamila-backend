import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.models import Story, StoryLike, StoryReply, StoryView, User
from app.common.models.social import Follow
from app.common.schemas.auth import (
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyOtpRequest,
)
from app.common.services.auth_service import AuthService
from app.common.services.story_service import file_to_base64_data_url
from app.core.dependencies import get_current_user, get_db
from app.core.rate_limit import rate_limit
from app.core.security import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/auth", tags=["Auth"])

AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_MAX_DATA_URL_CHARS = 2_800_000  # about 2 MB of image data once base64-encoded
NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 300
LOCATION_MAX_LENGTH = 100
MOBILE_MAX_LENGTH = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^\+?[0-9\s\-]{7,20}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")

# Login and OTP endpoints are throttled per client IP.
login_limit = rate_limit("login", max_calls=10, window_seconds=60)
otp_limit = rate_limit("otp", max_calls=10, window_seconds=60)
otp_request_limit = rate_limit("otp-request", max_calls=5, window_seconds=60)


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordPayload(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)
    otp: str = Field(..., min_length=6, max_length=6)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _profile_payload(user: User) -> dict:
    return {
        "id": user.user_id,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "mobile_no": user.mobile_no,
        "dob": user.dob.isoformat() if user.dob else None,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "location": user.location,
        "followers_count": user.followers_count,
        "following_count": user.following_count,
        "posts_count": user.posts_count,
    }


def _availability(taken: bool, message: str) -> dict:
    return {"available": not taken, "message": message if taken else None}


@router.get("/check-availability", status_code=status.HTTP_200_OK)
def check_availability(
    email: Optional[str] = Query(None),
    mobile_no: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    result: dict = {}
    if email is not None:
        taken = AuthService.get_by_email(db, email.strip()) is not None
        result["email"] = _availability(
            taken, "This email is already registered. Please use a different email."
        )
    if mobile_no is not None:
        taken = AuthService.get_by_mobile(db, mobile_no.strip()) is not None
        result["mobile_no"] = _availability(
            taken, "This mobile number is already registered. Please use a different mobile number."
        )
    if username is not None:
        taken = AuthService.get_by_username(db, username.strip()) is not None
        result["username"] = _availability(
            taken, "This username is already taken. Please choose a different username."
        )
    return result


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    user = AuthService.register(db, payload)
    user_dict = {
        "id": user.user_id,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "mobile_no": user.mobile_no,
        "dob": user.dob.isoformat() if user.dob else None,
        "role": user.role,
    }
    return {"user": user_dict, **user_dict}


@router.get("/profile", status_code=status.HTTP_200_OK)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    payload = _profile_payload(current_user)
    payload["followers_count"] = (
        db.query(Follow).filter(Follow.following_id == current_user.user_id).count()
    )
    payload["following_count"] = (
        db.query(Follow).filter(Follow.follower_id == current_user.user_id).count()
    )
    return payload


# ------------------------------------------------------------- profile update
def _clean_name(value: Optional[str], label: str, required: bool) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if required and not value:
        raise _bad_request(f"{label} cannot be empty.")
    if len(value) > NAME_MAX_LENGTH:
        raise _bad_request(f"{label} must be {NAME_MAX_LENGTH} characters or less.")
    return value


def _clean_text(value: Optional[str], label: str, max_length: int) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if len(value) > max_length:
        raise _bad_request(f"{label} must be {max_length} characters or less.")
    return value


def _clean_email(db: Session, value: Optional[str], me: User) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().lower()
    if not value or not EMAIL_RE.match(value):
        raise _bad_request("Please enter a valid email address.")
    existing = AuthService.get_by_email(db, value)
    if existing is not None and existing.user_id != me.user_id:
        raise _bad_request("This email is already registered.")
    return value


def _clean_mobile(db: Session, value: Optional[str], me: User) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value or not MOBILE_RE.match(value):
        raise _bad_request("Please enter a valid phone number.")
    if len(value) > MOBILE_MAX_LENGTH:
        raise _bad_request(f"Phone number must be {MOBILE_MAX_LENGTH} characters or less.")
    existing = AuthService.get_by_mobile(db, value)
    if existing is not None and existing.user_id != me.user_id:
        raise _bad_request("This phone number is already registered.")
    return value


def _clean_username(db: Session, value: Optional[str], me: User) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not USERNAME_RE.match(value):
        raise _bad_request(
            "Username must be 3-30 characters: letters, numbers, dots and underscores only."
        )
    existing = AuthService.get_by_username(db, value)
    if existing is not None and existing.user_id != me.user_id:
        raise _bad_request("This username is already taken.")
    return value


async def _read_avatar(avatar: Optional[UploadFile]) -> Optional[str]:
    if avatar is None or not avatar.filename:
        return None
    if avatar.content_type not in AVATAR_ALLOWED_TYPES:
        raise _bad_request("Avatar must be a JPG, PNG or WEBP image.")
    data_url, _ = await file_to_base64_data_url(avatar)
    if len(data_url) > AVATAR_MAX_DATA_URL_CHARS:
        raise _bad_request("Avatar must be 2 MB or smaller.")
    return data_url


def _propagate_username(db: Session, user: User, username: str) -> None:
    """Keep the copies of the username stored on story rows in sync."""
    uid = user.user_id
    user.username = username
    if user.profile is not None:
        user.profile.username = username

    my_story_ids = select(Story.story_id).where(Story.user_id == uid)
    updates = (
        (Story, Story.user_id == uid, {Story.username: username}),
        (StoryView, StoryView.user_id == uid, {StoryView.viewed_by: username}),
        (StoryView, StoryView.story_id.in_(my_story_ids), {StoryView.story_sender: username}),
        (StoryLike, StoryLike.user_id == uid, {StoryLike.liked_by: username}),
        (StoryLike, StoryLike.story_id.in_(my_story_ids), {StoryLike.user_name: username}),
        (StoryReply, StoryReply.user_id == uid, {StoryReply.sender_name: username}),
        (StoryReply, StoryReply.story_id.in_(my_story_ids), {StoryReply.receiver_name: username}),
    )
    for model, condition, values in updates:
        db.query(model).filter(condition).update(values, synchronize_session=False)


@router.put("/profile", status_code=status.HTTP_200_OK)
async def update_profile(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    mobile_no: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Validate everything first, change nothing until all checks pass.
    first_name = _clean_name(first_name, "First name", required=True)
    last_name = _clean_name(last_name, "Last name", required=False)
    bio = _clean_text(bio, "Bio", BIO_MAX_LENGTH)
    location = _clean_text(location, "Location", LOCATION_MAX_LENGTH)
    email = _clean_email(db, email, current_user)
    mobile_no = _clean_mobile(db, mobile_no, current_user)
    username = _clean_username(db, username, current_user)
    avatar_data_url = await _read_avatar(avatar)

    simple_fields = {
        "first_name": first_name,
        "last_name": last_name,
        "bio": bio,
        "location": location,
        "email": email,
        "mobile_no": mobile_no,
        "avatar_url": avatar_data_url,
    }
    for field, value in simple_fields.items():
        if value is not None:
            setattr(current_user, field, value)

    if username is not None and username != current_user.username:
        _propagate_username(db, current_user, username)

    db.commit()
    db.refresh(current_user)
    return _profile_payload(current_user)


# ------------------------------------------------------------------ login
async def _read_credentials(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Accept JSON or form bodies; return (username_or_email, password)."""
    content_type = request.headers.get("content-type", "")
    is_form = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
    try:
        body = await request.form() if is_form else await request.json()
    except Exception:
        raise _bad_request("Invalid request body.") from None
    if not hasattr(body, "get"):
        raise _bad_request("Invalid request body.") from None
    name = body.get("username") or body.get("email") or body.get("username_or_email")
    return name, body.get("password")


@router.post("/login", status_code=status.HTTP_200_OK, dependencies=[Depends(login_limit)])
async def login(request: Request, db: Session = Depends(get_db)) -> dict:
    username_val, password_val = await _read_credentials(request)
    if not username_val or not password_val:
        raise _bad_request("Username/email and password are required.")

    user = AuthService.authenticate(db, str(username_val).strip(), str(password_val))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been suspended. Contact support for help.",
        )

    user_dict = {
        "id": user.id,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "mobile_no": user.mobile_no,
        "dob": user.dob.isoformat() if user.dob else None,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "followers_count": user.followers_count,
    }
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": user_dict,
        "id": user.id,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "mobile_no": user.mobile_no,
        "dob": user_dict["dob"],
        "role": user.role,
    }


@router.post("/refresh", dependencies=[Depends(login_limit)])
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise ValueError("wrong token type")
        user_id = int(decoded.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token.") from None

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found.")

    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
    }


# --------------------------------------------------------------- passwords
@router.post("/change-password/request-otp", dependencies=[Depends(otp_request_limit)])
def request_change_password_otp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    masked = AuthService.send_change_password_otp(db, current_user)
    return {"success": True, "message": f"We sent a 6-digit code to {masked}. It expires in 10 minutes."}


@router.post("/change-password", dependencies=[Depends(otp_limit)])
def change_password(
    payload: ChangePasswordPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    AuthService.change_password_with_otp(
        db, current_user, payload.old_password, payload.otp, payload.new_password
    )
    return {"success": True, "message": "Password changed successfully"}


@router.post("/forgot-password", dependencies=[Depends(otp_request_limit)])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    # Same answer whether or not the account exists, so this cannot be used to find
    # out which emails are registered. create_otp does nothing for unknown accounts.
    AuthService.create_otp(db, payload.identifier)
    return {
        "success": True,
        "message": "If an account exists for this email, a 6-digit code has been sent.",
    }


@router.post("/verify-otp", dependencies=[Depends(otp_limit)])
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.verify_otp(db, payload.identifier, payload.otp)
    return {"success": True, "message": "OTP verified."}


@router.post("/reset-password", dependencies=[Depends(otp_limit)])
def reset_password_endpoint(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.reset_password_with_otp(
        db, payload.identifier, payload.otp, payload.new_password
    )
    return {"success": True, "message": "Password reset successfully."}