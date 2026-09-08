import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models import Story, StoryLike, StoryReply, User
from app.services.music_service import get_music_track_by_id, search_music_tracks

logger = logging.getLogger("talktamila.stories")
router = APIRouter(prefix="/api/stories", tags=["Stories"])

DEFAULT_DURATION_HOURS = 24
UPLOAD_DIR = os.path.join(os.getcwd(), "uploads", "stories")
VALID_AUDIENCES_NON_ADMIN = {"public", "followers", "close_friends"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def story_is_active(story: Story) -> bool:
    now = utc_now()
    if story.expires_at is None:
        if story.created_at is None:
            return False
        created_at = story.created_at if story.created_at.tzinfo else story.created_at.replace(tzinfo=timezone.utc)
        return created_at + timedelta(hours=DEFAULT_DURATION_HOURS) > now
    expires_at = story.expires_at if story.expires_at.tzinfo else story.expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


def get_story(story_id: int, db: Session, require_active: bool = True) -> Story:
    story = db.query(Story).options(joinedload(Story.user)).filter(Story.story_id == story_id).first()
    if not story:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    if require_active and not story_is_active(story):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story has expired.")
    return story


def normalize_and_validate_audience(audience: Optional[str], user_role: Optional[str]) -> str:
    role = (user_role or "influencer").strip().lower()
    if role == "admin":
        return "public"

    raw = (audience or "public").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in ("close_circle", "closecircle", "close_friends", "closefriends"):
        normalized = "close_friends"
    elif raw in ("followers", "follower"):
        normalized = "followers"
    elif raw in ("public", "everyone", "all"):
        normalized = "public"
    else:
        normalized = raw

    if normalized not in VALID_AUDIENCES_NON_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid audience '{audience}'. Influencers and freelancers can select: 'public', 'followers', or 'close_friends'.",
        )
    return normalized


# --- Pydantic Schemas ---
class UserMiniResponse(BaseModel):
    user_id: int
    username: str
    email: str
    role: Optional[str] = "influencer"
    model_config = ConfigDict(from_attributes=True)


class AudienceOptionItem(BaseModel):
    id: str
    label: str
    description: str


class AudienceOptionsResponse(BaseModel):
    role: str
    default_audience: str = "public"
    allowed_audiences: List[AudienceOptionItem]


class MusicTrackResponse(BaseModel):
    track_id: int
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: int
    audio_url: str
    cover_url: Optional[str] = None
    genre: Optional[str] = None
    language: str
    is_trending: bool
    model_config = ConfigDict(from_attributes=True)


class MusicAttachRequest(BaseModel):
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_start_time: Optional[float] = 0.0
    music_duration: Optional[float] = Field(
        default=60.0, ge=1.0, le=60.0, description="Music playback duration in seconds (up to 1 minute maximum)"
    )


class StoryCreateRequest(BaseModel):
    media_url: str = Field(..., min_length=1, max_length=500)
    media_type: str = Field(default="image", pattern=r"^(image|video)$")
    caption: Optional[str] = Field(default=None, max_length=1000)
    audience: Optional[str] = Field(default="public", description="Story audience: public, followers, or close_friends")
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_start_time: Optional[float] = 0.0
    music_duration: Optional[float] = Field(default=60.0, ge=1.0, le=60.0, description="Music playback duration up to 1 minute maximum")


class StoryBatchItemRequest(BaseModel):
    media_url: str = Field(..., min_length=1, max_length=500)
    media_type: str = Field(default="image", pattern=r"^(image|video)$")
    caption: Optional[str] = Field(default=None, max_length=1000)
    audience: Optional[str] = Field(default=None, description="Audience override: public, followers, or close_friends")
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_start_time: Optional[float] = None
    music_duration: Optional[float] = Field(default=None, ge=1.0, le=60.0)


class StoryBatchCreateRequest(BaseModel):
    items: List[StoryBatchItemRequest] = Field(..., min_length=1, description="List of media items to publish together")
    shared_music: Optional[MusicAttachRequest] = Field(default=None, description="Music applied to all items lacking individual music")
    shared_audience: Optional[str] = Field(default="public", description="Default audience for all batch slides")


class StoryResponse(BaseModel):
    story_id: int
    user_id: int
    media_url: str
    media_type: str
    created_at: datetime
    expires_at: datetime
    caption: Optional[str] = None
    audience: str = "public"
    is_active: bool = True
    music_id: Optional[int] = None
    music_title: Optional[str] = None
    music_artist: Optional[str] = None
    music_url: Optional[str] = None
    music_thumbnail: Optional[str] = None
    music_start_time: Optional[float] = 0.0
    music_duration: Optional[float] = 60.0
    user: Optional[UserMiniResponse] = None
    likes_count: int = 0
    replies_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class StoryBatchResponse(BaseModel):
    success: bool
    message: str
    total_published: int
    stories: List[StoryResponse]


class UserStoriesGroupResponse(BaseModel):
    user: UserMiniResponse
    stories: List[StoryResponse]
    stories_count: int
    latest_story_created_at: datetime


class StoryReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class StoryActionResponse(BaseModel):
    success: bool
    message: str
    story_id: int


class StoryUpdateRequest(BaseModel):
    caption: Optional[str] = Field(default=None, max_length=1000)


class LikeStatusResponse(BaseModel):
    story_id: int
    likes_count: int
    liked_by_me: bool


class StoryReplyResponse(BaseModel):
    reply_id: int
    story_id: int
    text: str
    created_at: datetime
    user: Optional[UserMiniResponse] = None
    model_config = ConfigDict(from_attributes=True)


# --- Serialization Helpers ---
def serialize_story(story: Story) -> StoryResponse:
    user_data = UserMiniResponse.model_validate(story.user) if getattr(story, "user", None) else None
    likes_cnt = len(story.likes) if hasattr(story, "likes") and story.likes is not None else 0
    replies_cnt = len(story.replies) if hasattr(story, "replies") and story.replies is not None else 0

    return StoryResponse(
        story_id=story.story_id,
        user_id=story.user_id,
        media_url=story.media_url,
        media_type=story.media_type,
        created_at=story.created_at,
        expires_at=story.expires_at,
        caption=story.caption,
        audience=getattr(story, "audience", "public") or "public",
        is_active=story_is_active(story),
        music_id=story.music_id,
        music_title=story.music_title,
        music_artist=story.music_artist,
        music_url=story.music_url,
        music_thumbnail=story.music_thumbnail,
        music_start_time=story.music_start_time or 0.0,
        music_duration=story.music_duration or 60.0,
        user=user_data,
        likes_count=likes_cnt,
        replies_count=replies_cnt,
    )


def serialize_reply(reply: StoryReply) -> StoryReplyResponse:
    user_data = UserMiniResponse.model_validate(reply.user) if getattr(reply, "user", None) else None
    return StoryReplyResponse(
        reply_id=reply.reply_id,
        story_id=reply.story_id,
        text=reply.text,
        created_at=reply.created_at,
        user=user_data,
    )


# --- API Routes ---
@router.get("", response_model=List[StoryResponse])
def list_active_stories(skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    """Get all currently active stories."""
    now = make_naive_utc(utc_now())
    stories = (
        db.query(Story)
        .options(joinedload(Story.user))
        .filter(Story.expires_at > now)
        .order_by(desc(Story.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serialize_story(s) for s in stories if story_is_active(s)]


@router.post("", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
def create_story(payload: StoryCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new single story with music and role-based audience."""
    user_role = getattr(current_user, "role", "influencer")
    validated_audience = normalize_and_validate_audience(payload.audience, user_role)
    created_at = make_naive_utc(utc_now())
    expires_at = created_at + timedelta(hours=DEFAULT_DURATION_HOURS)

    music_dur = (
        min(60.0, max(1.0, float(payload.music_duration or 60.0)))
        if (payload.music_id or payload.music_title or payload.music_url)
        else None
    )

    story = Story(
        user_id=current_user.user_id,
        media_url=payload.media_url,
        media_type=payload.media_type,
        caption=payload.caption,
        created_at=created_at,
        expires_at=expires_at,
        audience=validated_audience,
        music_id=payload.music_id,
        music_title=payload.music_title,
        music_artist=payload.music_artist,
        music_url=payload.music_url,
        music_thumbnail=payload.music_thumbnail,
        music_start_time=payload.music_start_time or 0.0,
        music_duration=music_dur,
    )
    try:
        db.add(story)
        db.commit()
        db.refresh(story)
        logger.info("Story created: story_id=%s user_id=%s audience=%s", story.story_id, current_user.user_id, validated_audience)
        return serialize_story(story)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to create story")
        raise HTTPException(status_code=500, detail="Failed to create story.") from exc


@router.post("/batch", response_model=StoryBatchResponse, status_code=status.HTTP_201_CREATED)
def create_stories_batch(payload: StoryBatchCreateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Publish multiple images or videos at once as stories (JSON payload)."""
    if not payload.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one media item must be provided.")

    user_role = getattr(current_user, "role", "influencer")
    now = utc_now()
    expires_at = now + timedelta(hours=DEFAULT_DURATION_HOURS)
    naive_now = make_naive_utc(now)
    naive_expires_at = make_naive_utc(expires_at)

    created_stories = []
    for item in payload.items:
        raw_aud = item.audience or payload.shared_audience or "public"
        validated_audience = normalize_and_validate_audience(raw_aud, user_role)

        music_id = item.music_id or (payload.shared_music.music_id if payload.shared_music else None)
        music_title = item.music_title or (payload.shared_music.music_title if payload.shared_music else None)
        music_artist = item.music_artist or (payload.shared_music.music_artist if payload.shared_music else None)
        music_url = item.music_url or (payload.shared_music.music_url if payload.shared_music else None)
        music_thumbnail = item.music_thumbnail or (payload.shared_music.music_thumbnail if payload.shared_music else None)
        music_start_time = item.music_start_time if item.music_start_time is not None else (payload.shared_music.music_start_time if payload.shared_music else 0.0)
        raw_duration = item.music_duration if item.music_duration is not None else (payload.shared_music.music_duration if payload.shared_music else 60.0)
        music_duration = (
            max(1.0, min(float(raw_duration or 60.0), 60.0))
            if (music_id or music_title or music_url)
            else None
        )

        story = Story(
            user_id=current_user.user_id,
            media_url=item.media_url,
            media_type=item.media_type,
            created_at=naive_now,
            expires_at=naive_expires_at,
            caption=item.caption,
            audience=validated_audience,
            reply=None,
            music_id=music_id,
            music_title=music_title,
            music_artist=music_artist,
            music_url=music_url,
            music_thumbnail=music_thumbnail,
            music_start_time=music_start_time,
            music_duration=music_duration,
        )
        created_stories.append(story)
        db.add(story)

    try:
        db.commit()
        for story in created_stories:
            db.refresh(story)

        logger.info("Batch stories published: count=%d user_id=%s", len(created_stories), current_user.user_id)
        story_ids = [s.story_id for s in created_stories]
        loaded_stories = db.query(Story).options(joinedload(Story.user)).filter(Story.story_id.in_(story_ids)).order_by(Story.story_id.asc()).all()
        return StoryBatchResponse(
            success=True,
            message=f"Successfully published {len(loaded_stories)} stories.",
            total_published=len(loaded_stories),
            stories=[serialize_story(s) for s in loaded_stories],
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to publish batch stories")
        raise HTTPException(status_code=500, detail="Failed to publish batch stories.") from exc


@router.post("/upload", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def upload_single_story_from_device(
    file: UploadFile = File(..., description="Image or video file from user device (gallery/album)"),
    caption: Optional[str] = Form(None, description="Optional caption for story"),
    audience: Optional[str] = Form("public", description="Story audience: public, followers, or close_friends"),
    music_data: Optional[str] = Form(None, description="Optional JSON string of song selected from live music API"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Direct upload of a single image or video selected from user device gallery/album."""
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided.")

    user_role = getattr(current_user, "role", "influencer")
    validated_audience = normalize_and_validate_audience(audience, user_role)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    music_info = {}
    if music_data:
        try:
            music_info = json.loads(music_data)
        except Exception:
            logger.warning("Could not parse music_data JSON: %s", music_data)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext:
        content_type = file.content_type or ""
        ext = ".mp4" if "video" in content_type else ".jpg"

    video_extensions = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
    media_type = "video" if (ext in video_extensions or (file.content_type and "video" in file.content_type)) else "image"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        logger.exception("Failed to write uploaded story file %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {file.filename}") from exc

    now = utc_now()
    expires_at = now + timedelta(hours=DEFAULT_DURATION_HOURS)
    naive_now = make_naive_utc(now)
    naive_expires_at = make_naive_utc(expires_at)

    has_music = bool(music_info.get("music_id") or music_info.get("music_title") or music_info.get("title") or music_info.get("music_url") or music_info.get("audio_url"))
    music_dur = max(1.0, min(float(music_info.get("music_duration", 60.0)), 60.0)) if has_music else None

    story = Story(
        user_id=current_user.user_id,
        media_url=f"/uploads/stories/{unique_filename}",
        media_type=media_type,
        created_at=naive_now,
        expires_at=naive_expires_at,
        caption=caption,
        audience=validated_audience,
        reply=None,
        music_id=music_info.get("music_id"),
        music_title=music_info.get("music_title") or music_info.get("title"),
        music_artist=music_info.get("music_artist") or music_info.get("artist"),
        music_url=music_info.get("music_url") or music_info.get("audio_url"),
        music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url") or music_info.get("thumbnail"),
        music_duration=music_dur,
    )
    try:
        db.add(story)
        db.commit()
        db.refresh(story)
        logger.info("Story uploaded from device: story_id=%s user_id=%s audience=%s", story.story_id, current_user.user_id, validated_audience)
        return serialize_story(story)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save uploaded story")
        raise HTTPException(status_code=500, detail="Failed to save story.") from exc


@router.post("/upload-multiple", response_model=StoryBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_publish_multiple_stories(
    files: List[UploadFile] = File(..., description="Multiple image or video files from user device gallery/album"),
    captions: Optional[str] = Form(None, description="Optional JSON array of captions or single caption string"),
    audience: Optional[str] = Form("public", description="Story audience: public, followers, or close_friends"),
    music_data: Optional[str] = Form(None, description="Optional JSON string of song selected from live music API"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Direct multipart upload of multiple files from device gallery/album publishing simultaneously."""
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided.")


    user_role = getattr(current_user, "role", "influencer")
    validated_audience = normalize_and_validate_audience(audience, user_role)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    parsed_captions = []
    if captions:
        try:
            parsed = json.loads(captions)
            if isinstance(parsed, list):
                parsed_captions = [str(c) for c in parsed]
            elif isinstance(parsed, str):
                parsed_captions = [parsed]
        except Exception:
            parsed_captions = [captions]

    music_info = {}
    if music_data:
        try:
            music_info = json.loads(music_data)
        except Exception:
            logger.warning("Could not parse music_data JSON: %s", music_data)

    now = utc_now()
    expires_at = now + timedelta(hours=DEFAULT_DURATION_HOURS)
    naive_now = make_naive_utc(now)
    naive_expires_at = make_naive_utc(expires_at)

    saved_stories = []
    video_extensions = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}

    for idx, file in enumerate(files):
        ext = os.path.splitext(file.filename or "")[1].lower()
        if not ext:
            content_type = file.content_type or ""
            ext = ".mp4" if "video" in content_type else ".jpg"

        media_type = "video" if (ext in video_extensions or (file.content_type and "video" in file.content_type)) else "image"
        unique_filename = f"{uuid.uuid4().hex}_{idx}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        try:
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as exc:
            logger.exception("Failed to write uploaded story file %s", file.filename)
            raise HTTPException(status_code=500, detail=f"Failed to save file: {file.filename}") from exc

        caption = parsed_captions[idx] if idx < len(parsed_captions) else (parsed_captions[0] if len(parsed_captions) == 1 else None)
        has_music = bool(music_info.get("music_id") or music_info.get("music_title") or music_info.get("title") or music_info.get("music_url") or music_info.get("audio_url"))
        music_dur = max(1.0, min(float(music_info.get("music_duration", 60.0)), 60.0)) if has_music else None

        story = Story(
            user_id=current_user.user_id,
            media_url=f"/uploads/stories/{unique_filename}",
            media_type=media_type,
            created_at=naive_now,
            expires_at=naive_expires_at,
            caption=caption,
            audience=validated_audience,
            reply=None,
            music_id=music_info.get("music_id"),
            music_title=music_info.get("music_title") or music_info.get("title"),
            music_artist=music_info.get("music_artist") or music_info.get("artist"),
            music_url=music_info.get("music_url") or music_info.get("audio_url"),
            music_thumbnail=music_info.get("music_thumbnail") or music_info.get("cover_url") or music_info.get("thumbnail"),
            music_duration=music_dur,
        )
        saved_stories.append(story)
        db.add(story)

    try:
        db.commit()
        for story in saved_stories:
            db.refresh(story)

        logger.info("Uploaded and published %d stories for user %s with audience %s", len(saved_stories), current_user.user_id, validated_audience)
        story_ids = [s.story_id for s in saved_stories]
        loaded_stories = db.query(Story).options(joinedload(Story.user)).filter(Story.story_id.in_(story_ids)).order_by(Story.story_id.asc()).all()
        return StoryBatchResponse(
            success=True,
            message=f"Successfully uploaded and published {len(loaded_stories)} stories.",
            total_published=len(loaded_stories),
            stories=[serialize_story(s) for s in loaded_stories],
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to commit uploaded stories")
        raise HTTPException(status_code=500, detail="Failed to publish uploaded stories to database.") from exc


@router.get("/audience-options", response_model=AudienceOptionsResponse)
def get_audience_options(current_user: User = Depends(get_current_user)):
    """Get allowed audience options for current user based on role."""
    role = (getattr(current_user, "role", None) or "influencer").strip().lower()
    if role == "admin":
        return AudienceOptionsResponse(
            role=role,
            default_audience="public",
            allowed_audiences=[AudienceOptionItem(id="public", label="Public", description="Visible to everyone on Talk Tamila")],
        )
    return AudienceOptionsResponse(
        role=role,
        default_audience="public",
        allowed_audiences=[
            AudienceOptionItem(id="public", label="Public", description="Visible to everyone on Talk Tamila"),
            AudienceOptionItem(id="followers", label="Followers", description="Visible to your followers only"),
            AudienceOptionItem(id="close_friends", label="Close Circle", description="Visible to your close circle friends only"),
        ],
    )


@router.get("/feed", response_model=List[UserStoriesGroupResponse])
def get_stories_feed(db: Session = Depends(get_db)):
    """Get stories feed grouped by user (stories tray format)."""
    now = make_naive_utc(utc_now())
    active_stories = db.query(Story).options(joinedload(Story.user)).filter(Story.expires_at > now).order_by(desc(Story.created_at)).all()

    groups_map = {}
    for story in active_stories:
        if not story_is_active(story) or not story.user:
            continue
        u_id = story.user_id
        if u_id not in groups_map:
            groups_map[u_id] = {
                "user": UserMiniResponse.model_validate(story.user),
                "stories": [],
                "latest_story_created_at": story.created_at,
            }
        groups_map[u_id]["stories"].append(serialize_story(story))

    result = []
    for u_id, group in groups_map.items():
        group["stories"].sort(key=lambda s: s.created_at)
        result.append(
            UserStoriesGroupResponse(
                user=group["user"],
                stories=group["stories"],
                stories_count=len(group["stories"]),
                latest_story_created_at=group["latest_story_created_at"],
            )
        )
    result.sort(key=lambda g: g.latest_story_created_at, reverse=True)
    return result


@router.get("/music/search", response_model=List[MusicTrackResponse])
def search_songs(
    q: Optional[str] = Query(default=None, description="Search song title, artist, album, or genre"),
    genre: Optional[str] = Query(default=None, description="Filter by genre"),
    language: Optional[str] = Query(default=None, description="Filter by language"),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Search songs dynamically from live servers to add as background music."""
    tracks = search_music_tracks(db=db, query=q, genre=genre, language=language, trending_only=False, limit=limit)
    return [MusicTrackResponse.model_validate(t) for t in tracks]


@router.get("/music/trending", response_model=List[MusicTrackResponse])
def get_trending_songs(limit: int = Query(default=20, ge=1, le=50), db: Session = Depends(get_db)):
    """Get trending Tamil songs for story background music."""
    tracks = search_music_tracks(db=db, trending_only=True, limit=limit)
    return [MusicTrackResponse.model_validate(t) for t in tracks]



@router.get("/music/{track_id}", response_model=MusicTrackResponse)
def get_song(track_id: int, db: Session = Depends(get_db)):
    """Get a single music track by ID."""
    track = get_music_track_by_id(db, track_id)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Music track not found.")
    return MusicTrackResponse.model_validate(track)


@router.get("/{story_id}", response_model=StoryResponse)
def get_single_story(story_id: int, db: Session = Depends(get_db)):
    """Get one active story."""
    story = get_story(story_id, db, require_active=True)
    return serialize_story(story)


@router.patch("/{story_id}", response_model=StoryResponse)
def update_story(story_id: int, payload: StoryUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Edit an existing story's caption."""
    story = get_story(story_id, db, require_active=True)
    if story.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the story owner can edit this story.")

    story.caption = payload.caption
    try:
        db.commit()
        db.refresh(story)
        logger.info("Story updated: story_id=%s user_id=%s", story_id, current_user.user_id)
        return serialize_story(story)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update story")
        raise HTTPException(status_code=500, detail="Failed to update story.") from exc


@router.get("/user/{user_id}", response_model=List[StoryResponse])
def get_user_stories(user_id: int, skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    """Get all active stories belonging to a user."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    now = make_naive_utc(utc_now())
    stories = (
        db.query(Story)
        .options(joinedload(Story.user))
        .filter(Story.user_id == user_id, Story.expires_at > now)
        .order_by(desc(Story.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serialize_story(story) for story in stories if story_is_active(story)]


@router.post("/{story_id}/replies", response_model=StoryReplyResponse, status_code=status.HTTP_201_CREATED)
def add_story_reply(story_id: int, payload: StoryReplyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a reply to a story."""
    story = get_story(story_id, db, require_active=True)
    reply = StoryReply(story_id=story.story_id, user_id=current_user.user_id, text=payload.text)
    try:
        db.add(reply)
        db.commit()
        db.refresh(reply)
        reply = db.query(StoryReply).options(joinedload(StoryReply.user)).filter(StoryReply.reply_id == reply.reply_id).first()
        logger.info("Story reply added: story_id=%s sender=%s", story_id, current_user.user_id)
        return serialize_reply(reply)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save story reply")
        raise HTTPException(status_code=500, detail="Failed to save story reply.") from exc


@router.get("/{story_id}/replies", response_model=List[StoryReplyResponse])
def list_story_replies(story_id: int, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    """List all replies to a story."""
    get_story(story_id, db, require_active=False)
    replies = (
        db.query(StoryReply)
        .options(joinedload(StoryReply.user))
        .filter(StoryReply.story_id == story_id)
        .order_by(StoryReply.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [serialize_reply(r) for r in replies]


@router.post("/{story_id}/like", response_model=LikeStatusResponse)
def like_story(story_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Like an active story."""
    story = get_story(story_id, db, require_active=True)
    existing = db.query(StoryLike).filter(StoryLike.story_id == story.story_id, StoryLike.user_id == current_user.user_id).first()

    if not existing:
        like = StoryLike(story_id=story.story_id, user_id=current_user.user_id)
        try:
            db.add(like)
            db.commit()
            logger.info("Story liked: story_id=%s user_id=%s", story.story_id, current_user.user_id)
        except IntegrityError:
            db.rollback()
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to like story")
            raise HTTPException(status_code=500, detail="Failed to like story.") from exc

    likes_count = db.query(func.count(StoryLike.like_id)).filter(StoryLike.story_id == story.story_id).scalar()
    return LikeStatusResponse(story_id=story.story_id, likes_count=likes_count, liked_by_me=True)


@router.delete("/{story_id}/like", response_model=LikeStatusResponse)
def unlike_story(story_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove caller's like from a story."""
    story = get_story(story_id, db, require_active=False)
    existing = db.query(StoryLike).filter(StoryLike.story_id == story.story_id, StoryLike.user_id == current_user.user_id).first()

    if existing:
        try:
            db.delete(existing)
            db.commit()
            logger.info("Story unliked: story_id=%s user_id=%s", story.story_id, current_user.user_id)
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to unlike story")
            raise HTTPException(status_code=500, detail="Failed to unlike story.") from exc

    likes_count = db.query(func.count(StoryLike.like_id)).filter(StoryLike.story_id == story.story_id).scalar()
    return LikeStatusResponse(story_id=story.story_id, likes_count=likes_count, liked_by_me=False)


@router.get("/{story_id}/likes", response_model=LikeStatusResponse)
def get_story_likes(story_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get the like count for a story and whether current user liked it."""
    story = get_story(story_id, db, require_active=False)
    likes_count = db.query(func.count(StoryLike.like_id)).filter(StoryLike.story_id == story.story_id).scalar()
    liked_by_me = db.query(StoryLike).filter(StoryLike.story_id == story.story_id, StoryLike.user_id == current_user.user_id).first() is not None
    return LikeStatusResponse(story_id=story.story_id, likes_count=likes_count, liked_by_me=liked_by_me)


@router.delete("/{story_id}", response_model=StoryActionResponse)
def delete_story(story_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a story (only story owner)."""
    story = get_story(story_id, db, require_active=False)
    if story.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the story owner can delete this story.")

    try:
        db.delete(story)
        db.commit()
        logger.info("Story deleted: story_id=%s user_id=%s", story_id, current_user.user_id)
        return StoryActionResponse(success=True, message="Story deleted successfully.", story_id=story_id)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete story")
        raise HTTPException(status_code=500, detail="Failed to delete story.") from exc
