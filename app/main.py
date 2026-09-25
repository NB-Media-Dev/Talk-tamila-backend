import json
import re
import app.core
from app.story.routes import router as story_router
from app.story.settings_routes import router as story_settings_router
from app.common.schemas.auth import ForgotPasswordRequest, VerifyOtpRequest, ResetPasswordRequest
from app.common.services.story_service import file_to_base64_data_url
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

        with engine.connect() as conn:
            for stmt in [
                "ALTER TABLE stories MODIFY COLUMN media_type VARCHAR(20) NOT NULL DEFAULT 'image'",
                "ALTER TABLE stories MODIFY COLUMN media_url LONGTEXT NOT NULL",
                "ALTER TABLE stories MODIFY COLUMN caption LONGTEXT NULL",
                "ALTER TABLE stories MODIFY COLUMN music_url LONGTEXT NULL",
                "ALTER TABLE stories MODIFY COLUMN music_thumbnail LONGTEXT NULL",
                "ALTER TABLE music_tracks ADD COLUMN language VARCHAR(50) DEFAULT 'Tamil'",
                "ALTER TABLE music_tracks ADD COLUMN genre VARCHAR(50) DEFAULT 'Tamil'",
                "ALTER TABLE music_tracks ADD COLUMN is_trending BOOLEAN DEFAULT TRUE",
                "ALTER TABLE music_tracks ADD COLUMN cover_url VARCHAR(500) NULL",
                "ALTER TABLE music_tracks ADD COLUMN duration_seconds FLOAT DEFAULT 60.0",
                "ALTER TABLE users ADD COLUMN reset_otp VARCHAR(6) NULL",
                "ALTER TABLE users ADD COLUMN reset_otp_expires DATETIME NULL",
                "ALTER TABLE users ADD COLUMN reset_otp_verified BOOLEAN DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN reset_otp_attempts INT NOT NULL DEFAULT 0",
                "ALTER TABLE users MODIFY COLUMN reset_otp VARCHAR(64) NULL",
                "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE stories ADD COLUMN username VARCHAR(100) NULL",
                "ALTER TABLE stories ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE stories ADD COLUMN deleted_at DATETIME NULL",
                "ALTER TABLE story_views ADD COLUMN story_sender VARCHAR(100) NULL",
                "ALTER TABLE story_views ADD COLUMN viewed_by VARCHAR(100) NULL",
                "ALTER TABLE story_likes ADD COLUMN liked_by VARCHAR(100) NULL",
                "ALTER TABLE story_likes ADD COLUMN user_name VARCHAR(100) NULL",
                "ALTER TABLE story_replies ADD COLUMN sender_name VARCHAR(100) NULL",
                "ALTER TABLE story_replies ADD COLUMN receiver_name VARCHAR(100) NULL",
                "ALTER TABLE stories ADD COLUMN reply LONGTEXT NULL",
                "ALTER TABLE profiles MODIFY COLUMN profile_pic_url LONGTEXT NULL",
            ]:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                except Exception:
                    pass

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
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
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


AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_MAX_DATA_URL_CHARS = 2_800_000  # about 2 MB of image data once base64-encoded
NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 300
LOCATION_MAX_LENGTH = 100
MOBILE_MAX_LENGTH = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^\+?[0-9\s\-]{7,20}$")


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


@auth_router.get("/profile", status_code=status.HTTP_200_OK)
def get_profile(current_user: User = Depends(get_current_user)) -> dict:
    return _profile_payload(current_user)


@auth_router.put("/profile", status_code=status.HTTP_200_OK)
async def update_profile(
    first_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    mobile_no: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # ---- validate everything first, so a bad request changes nothing ----
    if first_name is not None:
        first_name = first_name.strip()
        if not first_name:
            raise HTTPException(status_code=400, detail="First name cannot be empty.")
        if len(first_name) > NAME_MAX_LENGTH:
            raise HTTPException(status_code=400, detail=f"First name must be {NAME_MAX_LENGTH} characters or less.")

    if last_name is not None:
        last_name = last_name.strip()
        if len(last_name) > NAME_MAX_LENGTH:
            raise HTTPException(status_code=400, detail=f"Last name must be {NAME_MAX_LENGTH} characters or less.")

    if bio is not None:
        bio = bio.strip()
        if len(bio) > BIO_MAX_LENGTH:
            raise HTTPException(status_code=400, detail=f"Bio must be {BIO_MAX_LENGTH} characters or less.")

    if location is not None:
        location = location.strip()
        if len(location) > LOCATION_MAX_LENGTH:
            raise HTTPException(status_code=400, detail=f"Location must be {LOCATION_MAX_LENGTH} characters or less.")

    if email is not None:
        email = email.strip().lower()
        if not email or not EMAIL_RE.match(email):
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        existing = AuthService.get_by_email(db, email)
        if existing is not None and existing.user_id != current_user.user_id:
            raise HTTPException(status_code=400, detail="This email is already registered.")

    if mobile_no is not None:
        mobile_no = mobile_no.strip()
        if not mobile_no or not MOBILE_RE.match(mobile_no):
            raise HTTPException(status_code=400, detail="Please enter a valid phone number.")
        if len(mobile_no) > MOBILE_MAX_LENGTH:
            raise HTTPException(status_code=400, detail=f"Phone number must be {MOBILE_MAX_LENGTH} characters or less.")
        existing = AuthService.get_by_mobile(db, mobile_no)
        if existing is not None and existing.user_id != current_user.user_id:
            raise HTTPException(status_code=400, detail="This phone number is already registered.")

    avatar_data_url: Optional[str] = None
    if avatar is not None and avatar.filename:
        if avatar.content_type not in AVATAR_ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Avatar must be a JPG, PNG or WEBP image.")
        avatar_data_url, _ = await file_to_base64_data_url(avatar)
        if len(avatar_data_url) > AVATAR_MAX_DATA_URL_CHARS:
            raise HTTPException(status_code=400, detail="Avatar must be 2 MB or smaller.")

    # ---- apply ----
    if first_name is not None:
        current_user.first_name = first_name
    if last_name is not None:
        current_user.last_name = last_name
    if bio is not None:
        current_user.bio = bio
    if location is not None:
        current_user.location = location
    if email is not None:
        current_user.email = email
    if mobile_no is not None:
        current_user.mobile_no = mobile_no
    if avatar_data_url is not None:
        current_user.avatar_url = avatar_data_url

    db.commit()
    db.refresh(current_user)

    return _profile_payload(current_user)


@auth_router.post("/login", openapi_extra=login_schema_extra, status_code=status.HTTP_200_OK)
async def login(request: Request, db: Session = Depends(get_db)) -> dict:
    content_type = request.headers.get("content-type", "")
    username_val = None
    password_val = None

    if "application/json" in content_type:
        try:
            body = await request.json()
            username_val = body.get("username") or body.get("email") or body.get("username_or_email")
            password_val = body.get("password")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")
    elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        form = await request.form()
        username_val = form.get("username") or form.get("email") or form.get("username_or_email")
        password_val = form.get("password")
    else:
        try:
            body = await request.json()
            username_val = body.get("username") or body.get("email") or body.get("username_or_email")
            password_val = body.get("password")
        except Exception:
            form = await request.form()
            username_val = form.get("username") or form.get("email") or form.get("username_or_email")
            password_val = form.get("password")

    if not username_val or not password_val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username/email and password are required.",
        )

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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

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
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_dict,
        "id": user.id,
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "mobile_no": user.mobile_no,
        "dob": user.dob.isoformat() if user.dob else None,
        "role": user.role,
    }


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
    story_settings_router,
    admin_router,
    influencer_router,
    freelancer_router,
    superadmin_router,
]

for r in routers:
    app.include_router(r, prefix=settings.API_V1_PREFIX)