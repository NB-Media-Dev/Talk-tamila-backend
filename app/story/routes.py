"""
app/story/routes.py
===================
Dedicated story router for TalkTamila.

Covers ALL roles: influencer, freelancer, admin.

API surface (all prefixed by /api/v1/stories or /api/stories):

  Feed & Discovery
  ─────────────────────────────────────────────────────
  GET   /                         Active 24-h story feed (grouped by user)
  GET   /feed                     Alias
  GET   /active                   Alias

  My Stories
  ─────────────────────────────────────────────────────
  GET   /my                       My active stories
  GET   /me                       Alias
  GET   /stats/me                 My aggregate engagement stats
  GET   /archived                 My expired stories (last 30 days)
  GET   /saved                    My saved stories

  Specific User / Story
  ─────────────────────────────────────────────────────
  GET   /user/{user_id}           Another user's active stories
  GET   /{story_id}               Single story detail

  Upload & Create
  ─────────────────────────────────────────────────────
  POST  /upload                   Upload single (multipart, image/video)
  POST  /upload-multiple          Upload batch (multipart)
  POST  /                         Create via JSON (external URL)

  Edit & Delete
  ─────────────────────────────────────────────────────
  PATCH /{story_id}               Edit caption / audience (owner only)
  DELETE/{story_id}               Delete story (owner or admin)

  Engagement
  ─────────────────────────────────────────────────────
  POST  /{story_id}/view          Record a view
  POST  /{story_id}/like          Like
  DELETE/{story_id}/like          Unlike
  POST  /{story_id}/react         Emoji reaction
  POST  /{story_id}/reply         Send a text reply
  POST  /{story_id}/comments      Alias for reply
  GET   /{story_id}/comments      Fetch all replies
  POST  /{story_id}/pause         Record pause / resume state

  Activity (owner only)
  ─────────────────────────────────────────────────────
  GET   /{story_id}/activity      Full activity (views + likes)
  GET   /{story_id}/viewers       Paginated viewer list
  GET   /{story_id}/likers        Paginated liker list

  Share, Save, Report
  ─────────────────────────────────────────────────────
  POST  /{story_id}/share         Record a share
  POST  /{story_id}/save          Save story
  DELETE/{story_id}/save          Unsave story
  POST  /{story_id}/report        Report story

  Mute
  ─────────────────────────────────────────────────────
  POST  /mute/{user_id}           Mute a creator's stories
  DELETE/mute/{user_id}           Unmute
  GET   /mutes                    My muted creator IDs

  Music
  ─────────────────────────────────────────────────────
  GET   /music/trending           Trending music tracks
  GET   /music/search             Search music tracks
"""

from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.common.models.story import Story
from app.common.models.user import User
from app.common.schemas.story import (
    PaginatedLikerResponse,
    PaginatedViewerResponse,
    StoryActivityResponse,
    StoryArchivedItem,
    StoryBatchResponse,
    StoryGroupResponse,
    StoryItemResponse,
    StoryCreateRequest,
    StoryJsonCreateRequest,
    StoryTextCreateRequest,
    StoryMuteResponse,
    StoryPatchRequest,
    StoryReactRequest,
    StoryReactResponse,
    StoryReplyRequest,
    StoryReplyResponse,
    StoryReportRequest,
    StoryShareRequest,
    StoryShareResponse,
    StoryStatsResponse,
    StoryWithMetrics,
    StoryPauseRequest,
    MyStoryAnalyticsResponse,
    StoryOwnerFeedResponse,
)
from app.common.services.music_service import MusicService
from app.common.services.story_service import (
    StoryService,
    build_story_item,
    make_naive,
    utc_now,
    DEFAULT_DURATION_HOURS,
)
from app.core.database import SessionLocal
from app.core.dependencies import (
    get_current_user,
    get_db,
    get_optional_current_user,
)
from app.common.schemas.music import MusicTrackResponse
from pydantic import BaseModel, Field
from datetime import timedelta

router = APIRouter(prefix="/stories", tags=["Stories"])


@router.get("/feed", response_model=List[StoryItemResponse])
def get_stories_feed(
    limit: int = Query(default=20, ge=1, le=100, description="Number of stories to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryItemResponse]:
    """Privacy-aware stories feed for authenticated user.
    Returns only stories visible to the authenticated user based on privacy rules:
    - PUBLIC stories
    - User's own stories
    - FOLLOWERS stories where the user follows the story author
    - CLOSE_FRIENDS stories where the author designated the user as a close friend
    """
    return StoryService.get_privacy_feed(current_user, db, limit=limit, offset=offset)


@router.get("", response_model=List[StoryGroupResponse])
@router.get("/active", response_model=List[StoryGroupResponse])
@router.get("/grouped", response_model=List[StoryGroupResponse])
def list_active_stories(
    role: Optional[str] = Query(None, description="Filter by role: influencer | freelancer | admin"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryGroupResponse]:
    """Active 24-hour stories grouped by creator.
    - Viewer's own story ('Your Story') is pinned first with is_my_story=True.
    - Unseen stories appear before fully-viewed ones.
    - Respects privacy visibility permissions (PUBLIC, FOLLOWERS, CLOSE_FRIENDS).
    """
    return StoryService.list_active_groups(current_user, db, role_filter=role)

@router.get("/profile", response_model=List[StoryItemResponse])
def get_my_active_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryItemResponse]:
    """Fetch only the active stories belonging to the currently authenticated user."""
    return StoryService.get_my_stories(current_user, db)


@router.get("/stats/me", response_model=StoryStatsResponse)
def get_my_story_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    """Aggregate engagement totals (views, likes, replies, shares) across ALL stories
    ever created by the current user — active and expired.
    """
    return StoryService.get_my_stats(current_user, db)


@router.get("/my-story-analytics", response_model=MyStoryAnalyticsResponse)
def get_my_story_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Detailed Instagram-style breakdown of who viewed, liked, and replied to the logged-in user's active stories."""
    return StoryService.get_my_story_analytics(current_user, db)


@router.get("/owner-feed", response_model=List[StoryOwnerFeedResponse])
def get_owner_story_feed(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryOwnerFeedResponse]:
    """Stories data structure for the owner with granular per-slide view metrics."""
    return StoryService.get_owner_feed(current_user, db)




@router.get("/archived", response_model=List[StoryArchivedItem])
def get_archived_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryArchivedItem]:
    """Fetch expired stories from the last 30 days belonging to the current user.
    Useful for 'Story Archive' / highlights planning.
    """
    return StoryService.get_archived_stories(current_user, db)


@router.get("/saved")
def get_saved_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    """Fetch all stories the current user has saved."""
    return StoryService.get_saved_stories(current_user, db)


@router.get("/mutes", response_model=List[int])
def get_muted_creators(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[int]:
    """Return the list of user IDs whose stories the current user has muted."""
    return StoryService.get_muted_creators(current_user, db)



@router.get("/music/trending", response_model=List[MusicTrackResponse])
def get_trending_music(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Return top trending Tamil music tracks for story background music."""
    return MusicService.get_trending(db, limit)


@router.get("/music/search", response_model=List[MusicTrackResponse])
def search_music(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Search for music tracks by title or artist name."""
    return MusicService.search(db, q, limit)



@router.get("/user/{user_id}", response_model=List[StoryItemResponse])
def get_user_stories(
    user_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryItemResponse]:
    """Fetch active 24-hour stories for a specific creator by user_id."""
    caller_id = current_user.id if current_user else None
    return StoryService.get_user_stories(user_id, caller_id, db)



@router.get("/{story_id:int}", response_model=StoryItemResponse)
def get_single_story(
    story_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    """Fetch full detail for a single story by ID."""
    caller_id = current_user.id if current_user else None
    return StoryService.get_story_by_id(story_id, caller_id, db)



@router.post("/upload", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
async def upload_single_story(
    file: UploadFile = File(..., description="Image or video file from device"),
    caption: Optional[str] = Form(None),
    audience: Optional[str] = Form("public"),
    music_data: Optional[str] = Form(None, description="JSON string with music metadata"),
    music_start_time: Optional[float] = Form(0.0, description="Clip start position in seconds (e.g. 30.0)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    """Upload a single image or video story (multipart/form-data).

    - **file**: JPEG, PNG, WEBP, MP4, MOV, etc.
    - **caption**: optional text overlay (max 2200 chars)
    - **audience**: `public` | `followers` | `close_friends`
    - **music_data**: optional JSON `{music_id, music_title, music_artist, music_url, music_duration}`
    - **music_start_time**: second offset where the 60-second clip begins (default 0.0)

    Story expires automatically after 24 hours.
    """
    return await StoryService.upload_single(file, caption, audience, music_data, current_user, db, music_start_time=music_start_time or 0.0)


@router.post("/upload-multiple", response_model=StoryBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_multiple_stories(
    files: List[UploadFile] = File(..., description="Up to 10 image/video files"),
    captions: Optional[str] = Form(None, description="JSON array of captions, one per slide"),
    audience: Optional[str] = Form("public"),
    music_data: Optional[str] = Form(None),
    music_start_time: Optional[float] = Form(0.0, description="Clip start position in seconds (e.g. 30.0)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryBatchResponse:
    """Batch-upload multiple story slides.

    - **files**: list of image/video files (max 10)
    - **captions**: JSON array e.g. `["Slide 1", "Slide 2"]`
    - **music_start_time**: second offset for the 60-second clip window
    - Each slide becomes an independent story sharing the same 24-h expiry window.
    """
    return await StoryService.upload_multiple(files, captions, audience, music_data, current_user, db, music_start_time=music_start_time or 0.0)


@router.post("", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_story(
    payload: StoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    """Create a story with privacy permissions (PUBLIC, FOLLOWERS, CLOSE_FRIENDS).
    - Authenticated user ID is strictly used as author_id.
    - Audience accepts: PUBLIC, FOLLOWERS, CLOSE_FRIENDS.
    """
    return StoryService.create_story(payload, current_user, db)



@router.post("/text", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_text_story(
    payload: StoryTextCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    """Create a text-only story with gradient theme styling."""
    now_naive = make_naive(utc_now())
    expires_naive = now_naive + timedelta(hours=payload.duration_hours or DEFAULT_DURATION_HOURS)

    resolved_music_id = MusicService.resolve_or_create_music_track(
        db=db,
        music_id=payload.music_id,
        music_title=payload.music_title,
        music_artist=payload.music_artist,
        music_url=payload.music_url,
        music_thumbnail=payload.music_thumbnail,
        music_duration=payload.music_duration or 60.0,
    )

    theme_val = (payload.theme or "insta").strip().lower()
    media_url = payload.media_url or f"gradient:{theme_val}"

    story = Story(
        user_id=current_user.id,
        media_url=media_url,
        media_type="text",
        caption=payload.caption,
        audience=payload.audience or "public",
        created_at=now_naive,
        expires_at=expires_naive,
        music_id=resolved_music_id,
        music_title=payload.music_title,
        music_artist=payload.music_artist,
        music_url=payload.music_url,
        music_thumbnail=payload.music_thumbnail,
        music_duration=payload.music_duration or 60.0,
        music_start_time=max(0.0, float(payload.music_start_time or 0.0)),
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    return build_story_item(story, current_user.id, db)



@router.patch("/{story_id:int}", response_model=StoryItemResponse)
def edit_story(
    story_id: int,
    payload: StoryPatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    """Edit the caption and/or audience of your own story (owner only).

    - **caption**: new text overlay (set to empty string to clear)
    - **audience**: `public` | `followers` | `close_friends`
    """
    return StoryService.update_story(story_id, payload.caption, payload.audience, current_user, db)


@router.delete("/{story_id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete a story. Only the owner or an admin can do this."""
    StoryService.delete_story(story_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)



@router.post("/slides/{slide_id:int}/view")
@router.post("/{story_id:int}/view")
def record_story_view(
    story_id: Optional[int] = None,
    slide_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record that the current user viewed a specific slide or story.
    Duplicate views from the same user are silently ignored (deduplicated).
    """
    target_id = slide_id if slide_id is not None else story_id
    if target_id is None:
        raise HTTPException(status_code=400, detail="Missing slide or story id")
    return StoryService.record_view(target_id, current_user, db)


@router.post("/{story_id:int}/like")
def like_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Like a story. You cannot like your own story."""
    return StoryService.like_story(story_id, current_user, db)


@router.delete("/{story_id:int}/like")
def unlike_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove a like from a story."""
    return StoryService.unlike_story(story_id, current_user, db)


@router.post("/{story_id:int}/react", response_model=StoryReactResponse)
def react_to_story(
    story_id: int,
    payload: StoryReactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryReactResponse:
    """Send an emoji reaction to a story (e.g. ❤️ 🔥 😂 😮).
    Reactions are stored separately from regular likes.
    Duplicate reactions with the same emoji are deduplicated.
    """
    return StoryService.react_to_story(story_id, payload.emoji, current_user, db)


@router.post("/{story_id:int}/reply", status_code=status.HTTP_201_CREATED)
@router.post("/{story_id:int}/comments", status_code=status.HTTP_201_CREATED)
def reply_to_story(
    story_id: int,
    payload: StoryReplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Send a text reply to a story. You cannot reply to your own story."""
    return StoryService.comment_story(story_id, payload.text, current_user, db)


class StoryReplyLegacyPayload(BaseModel):
    story_id: int
    text: str = Field(..., min_length=1, max_length=1000)


@router.post("/reply")
def reply_legacy(
    payload: StoryReplyLegacyPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Legacy reply endpoint that accepts story_id in the request body."""
    return StoryService.comment_story(payload.story_id, payload.text, current_user, db)


@router.get("/{story_id:int}/comments", response_model=List[StoryReplyResponse])
def get_story_comments(
    story_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryReplyResponse]:
    """Fetch all text replies for a story (newest first)."""
    return StoryService.get_comments(story_id, db)


@router.post("/{story_id:int}/pause")
def pause_story(
    story_id: int,
    payload: Optional[StoryPauseRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record that the user paused or resumed a story (for analytics / playback state)."""
    action = payload.action if payload else "pause"
    progress_ms = payload.progress_ms if payload else None
    slide_index = payload.slide_index if payload else None
    return StoryService.record_pause_state(story_id, action, progress_ms, slide_index, current_user, db)



@router.get("/{story_id:int}/activity", response_model=StoryActivityResponse)
def get_story_activity(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryActivityResponse:
    """Full activity summary for a story: viewers + likers (owner only).
    Returns user details for every person who viewed or liked the story.
    """
    return StoryService.get_activity(story_id, current_user, db)


@router.get("/{story_id:int}/viewers", response_model=PaginatedViewerResponse)
def get_story_viewers(
    story_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedViewerResponse:
    """Paginated list of users who viewed this story (owner or admin only).

    Returns: user_id, username, full_name, avatar_url, viewed_at for each viewer.
    Use ?page=2&page_size=20 to paginate through large view counts.
    """
    return StoryService.get_viewers(story_id, current_user, db, page=page, page_size=page_size)


@router.get("/{story_id:int}/likers", response_model=PaginatedLikerResponse)
def get_story_likers(
    story_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedLikerResponse:
    """Paginated list of users who liked this story (owner or admin only).

    Returns: user_id, username, full_name, avatar_url, liked_at for each liker.
    """
    return StoryService.get_likers(story_id, current_user, db, page=page, page_size=page_size)



@router.post("/{story_id:int}/share", response_model=StoryShareResponse)
def share_story(
    story_id: int,
    payload: Optional[StoryShareRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryShareResponse:
    """Record that the current user shared a story.

    - **platform**: `copy_link` | `whatsapp` | `dm` | `other`
    - **target_user_id**: optional – if sharing directly to another user (sends notification)
    """
    platform = payload.platform if payload and payload.platform else "copy_link"
    target_user_id = payload.target_user_id if payload else None
    return StoryService.share_story(story_id, platform, current_user, db, target_user_id=target_user_id)


@router.post("/{story_id:int}/save")
def save_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Save a story to the current user's personal archive."""
    return StoryService.save_story(story_id, current_user, db)


@router.delete("/{story_id:int}/save")
def unsave_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove a story from the current user's saved archive."""
    return StoryService.unsave_story(story_id, current_user, db)


@router.post("/{story_id:int}/report")
def report_story(
    story_id: int,
    payload: StoryReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Report a story for policy violations.

    - **reason**: e.g. "Spam", "Hate speech", "Nudity"
    - **details**: optional elaboration
    """
    return StoryService.report_story(story_id, payload.reason, current_user, db, details=payload.details)



@router.post("/mute/{user_id:int}", response_model=StoryMuteResponse)
@router.post("/users/{user_id:int}/mute", response_model=StoryMuteResponse)
def mute_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Mute a creator's stories — their stories will no longer appear in your feed."""
    return StoryService.mute_creator(user_id, current_user, db)


@router.delete("/mute/{user_id:int}", response_model=StoryMuteResponse)
@router.delete("/users/{user_id:int}/mute", response_model=StoryMuteResponse)
def unmute_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Unmute a previously muted creator — their stories will reappear in your feed."""
    return StoryService.unmute_creator(user_id, current_user, db)


@router.post("/close-friends/{friend_id:int}")
def add_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Add a user to your close friends list for CLOSE_FRIENDS stories visibility."""
    return StoryService.add_close_friend(current_user.id, friend_id, db)


@router.delete("/close-friends/{friend_id:int}")
def remove_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Remove a user from your close friends list."""
    return StoryService.remove_close_friend(current_user.id, friend_id, db)


@router.get("/close-friends", response_model=List[int])
def get_close_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[int]:
    """Get list of user IDs in your close friends list."""
    return StoryService.get_close_friends(current_user.id, db)


@router.post("/follow/{user_id:int}")
def follow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Follow a user to gain access to their FOLLOWERS stories."""
    return StoryService.follow_user(current_user.id, user_id, db)


@router.delete("/follow/{user_id:int}")
def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Unfollow a user."""
    return StoryService.unfollow_user(current_user.id, user_id, db)

