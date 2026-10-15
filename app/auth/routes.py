from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.models import User
from app.common.schemas.auth import (
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyOtpRequest,
)
from app.common.services.auth_service import AuthService
from app.common.services.profile_service import ProfileService
from app.core.dependencies import get_current_user, get_db
from app.core.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["Auth"])

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


# ============================================================ sign up
@router.get("/check-availability", status_code=status.HTTP_200_OK)
def check_availability(
    email: Optional[str] = Query(None),
    mobile_no: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    return AuthService.check_availability(db, email, mobile_no, username)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    return AuthService.signup(db, payload)


# ============================================================ log in / tokens
async def _read_login_credentials(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Accept JSON or form bodies; return (username_or_email, password)."""
    content_type = request.headers.get("content-type", "")
    is_form = "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type
    try:
        body = await request.form() if is_form else await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid request body.") from None
    if not hasattr(body, "get"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid request body.")
    username_or_email = body.get("username") or body.get("email") or body.get("username_or_email")
    return username_or_email, body.get("password")


@router.post("/login", status_code=status.HTTP_200_OK, dependencies=[Depends(login_limit)])
async def login(request: Request, db: Session = Depends(get_db)) -> dict:
    username_or_email, password = await _read_login_credentials(request)
    if not username_or_email or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username/email and password are required.")
    return AuthService.login(db, str(username_or_email).strip(), str(password))


@router.post("/refresh", dependencies=[Depends(login_limit)])
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    return AuthService.refresh_token(db, payload.refresh_token)


# ============================================================ my profile
@router.get("/profile", status_code=status.HTTP_200_OK)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ProfileService.get_my_profile(db, current_user)


@router.put("/profile", status_code=status.HTTP_200_OK)
async def update_my_profile(
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
    return await ProfileService.update_my_profile(
        db, current_user, first_name, last_name, username, bio, location, email, mobile_no, avatar
    )


# ============================================================ passwords
@router.post("/change-password/request-otp", dependencies=[Depends(otp_request_limit)])
def request_change_password_otp(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    masked_email = AuthService.request_change_password_otp(db, current_user)
    return {"success": True, "message": f"We sent a 6-digit code to {masked_email}. It expires in 10 minutes."}


@router.post("/change-password", dependencies=[Depends(otp_limit)])
def change_password(
    payload: ChangePasswordPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    AuthService.change_password(db, current_user, payload.old_password, payload.otp, payload.new_password)
    return {"success": True, "message": "Password changed successfully"}


@router.post("/forgot-password", dependencies=[Depends(otp_request_limit)])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    # Same answer whether or not the account exists, so this cannot be used to find
    # out which emails are registered. forgot_password does nothing for unknown accounts.
    AuthService.forgot_password(db, payload.identifier)
    return {
        "success": True,
        "message": "If an account exists for this email, a 6-digit code has been sent.",
    }


@router.post("/verify-otp", dependencies=[Depends(otp_limit)])
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.verify_otp(db, payload.identifier, payload.otp)
    return {"success": True, "message": "OTP verified."}


@router.post("/reset-password", dependencies=[Depends(otp_limit)])
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.reset_password(db, payload.identifier, payload.otp, payload.new_password)
    return {"success": True, "message": "Password reset successfully."}
