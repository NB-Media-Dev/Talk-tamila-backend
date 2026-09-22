import json
from app.common.schemas.auth import ForgotPasswordRequest, VerifyOtpRequest, ResetPasswordRequest
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin.routes import router as admin_router
from app.common.models import (
    MusicTrack,
    Notification,
    Profile,
    Story,
    StoryLike,
    StoryReply,
    StoryShare,
    StoryView,
    User,
)
from app.common.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    Token,
    UserResponse,
)
from app.common.schemas.music import MusicTrackResponse
from app.common.schemas.story import (
    StoryActivityResponse,
    StoryBatchResponse,
    StoryGroupResponse,
    StoryItemResponse,
    StoryJsonCreateRequest,
    StoryMuteResponse,
    StoryPauseRequest,
    StoryReplyRequest,
    StoryReplyResponse,
    StoryReportRequest,
    StoryShareRequest,
    StoryShareResponse,
    StorySlideResponse,
)
from app.common.services.auth_service import AuthService
from app.common.services.music_service import MusicService
from app.common.services.story_service import StoryService
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    get_db,
    get_optional_current_user,
)
from app.core.security import create_access_token, create_refresh_token, decode_token, verify_password, get_password_hash
from app.freelancer.routes import router as freelancer_router
from app.influencer.routes import router as influencer_router
from app.superadmin.routes import router as superadmin_router
from app.story.routes import router as story_router
from app.utils.seed import seed_db_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            if settings.ENVIRONMENT.lower() != "production" and db.query(User).first() is None:
                seed_db_data(db)
        finally:
            db.close()
    except Exception as e:
        print(f"Database auto-seeding/migration note: {e}")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Backend API for Authentication (Login, Sign Up) and Instagram Stories",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {
        "status": "ok",
        "app": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "api_prefix": settings.API_V1_PREFIX,
        "database": "mysql",
    }


auth_router = APIRouter(prefix="/auth", tags=["Auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordPayload(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)


@auth_router.get("/check-availability", status_code=status.HTTP_200_OK)
def check_availability(
    email: Optional[str] = Query(None),
    mobile_no: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:

    result: dict = {}

    if email is not None:
        taken = AuthService.get_by_email(db, email.strip()) is not None
        result["email"] = {
            "available": not taken,
            "message": "This email is already registered. Please use a different email."
            if taken
            else None,
        }

    if mobile_no is not None:
        taken = AuthService.get_by_mobile(db, mobile_no.strip()) is not None
        result["mobile_no"] = {
            "available": not taken,
            "message": "This mobile number is already registered. Please use a different mobile number."
            if taken
            else None,
        }

    if username is not None:
        taken = AuthService.get_by_username(db, username.strip()) is not None
        result["username"] = {
            "available": not taken,
            "message": "This username is already taken. Please choose a different username."
            if taken
            else None,
        }

    return result


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    user = AuthService.register(db, payload)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
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
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_dict,
        **user_dict,
    }


login_schema_extra = {
    "requestBody": {
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "email": {"type": "string"},
                        "username_or_email": {"type": "string"},
                        "password": {"type": "string"},
                    },
                    "required": ["password"],
                }
            },
            "application/x-www-form-urlencoded": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                    },
                    "required": ["username", "password"],
                }
            },
        }
    }
}


@auth_router.post("/login", openapi_extra=login_schema_extra ,status_code=status.HTTP_200_OK)
async def login(request: Request, db: Session = Depends(get_db)) -> dict:
    # 1. Try to get data from JSON, otherwise try Form data
    try:
        body = await request.json()
    except Exception:
        body = await request.form()

    # 2. Extract username/email and password
    username_val = body.get("username") or body.get("email") or body.get("username_or_email")
    password_val = body.get("password")

    if not username_val or not password_val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username/email and password are required.",
        )

    # 3. Authenticate the user
    user = AuthService.authenticate(db, str(username_val).strip(), str(password_val))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Return the standardized response from the service
    return AuthService.generate_token_response(user)


@auth_router.post("/refresh")
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)) -> dict:
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")
        user_id = int(decoded.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@auth_router.get("/profile")
def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "user_id": current_user.user_id,
        "username": current_user.username,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "full_name": current_user.full_name,
        "mobile_no": current_user.mobile_no,
        "dob": current_user.dob.isoformat() if current_user.dob else None,
        "role": current_user.role,
        "avatar_url": current_user.avatar_url,
        "bio": current_user.bio,
        "location": current_user.location,
        "followers_count": current_user.followers_count,
    }

@auth_router.patch("/profile")
def update_me(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    allowed = ["bio", "location", "avatar_url", "username", "full_name"]
    for field, value in payload.items():
        if field in allowed:
            setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return {"success": True, "message": "Profile updated."}


@auth_router.post("/change-password")
def change_password(
    payload: ChangePasswordPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.old_password, current_user.password):
        raise HTTPException(status_code=400, detail="Current password incorrect.")
    current_user.password = get_password_hash(payload.new_password)
    db.commit()
    return {"success": True, "message": "Password changed successfully"}

@auth_router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.create_otp(db, payload.identifier)
    return {"success": True, "message": "If that account exists, an OTP has been sent."}


@auth_router.post("/verify-otp")
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.verify_otp(db, payload.identifier, payload.otp)
    return {"success": True, "message": "OTP verified."}


@auth_router.post("/reset-password")
def reset_password_endpoint(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    AuthService.reset_password_with_otp(db, payload.identifier, payload.otp, payload.new_password)
    return {"success": True, "message": "Password reset successfully."}

routers = [
    auth_router,
    story_router,
    admin_router,
    influencer_router,
    freelancer_router,
    superadmin_router,
]

for r in routers:
    app.include_router(r, prefix=settings.API_V1_PREFIX)