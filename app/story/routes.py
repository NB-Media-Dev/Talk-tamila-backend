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
    return StoryService.get_privacy_feed(current_user, db, limit=limit, offset=offset)


@router.get("", response_model=List[StoryGroupResponse])
def list_active_stories(
    role: Optional[str] = Query(None, description="Filter by role: influencer | freelancer | admin"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryGroupResponse]:
    return StoryService.list_active_groups(current_user, db, role_filter=role)

@router.get("/profile", response_model=List[StoryItemResponse])
def get_my_active_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryItemResponse]:
    return StoryService.get_my_stories(current_user, db)


@router.get("/stats/me", response_model=StoryStatsResponse)
def get_my_story_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    return StoryService.get_my_stats(current_user, db)


@router.get("/my-story-analytics", response_model=MyStoryAnalyticsResponse)
def get_my_story_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.get_my_story_analytics(current_user, db)


@router.get("/owner-feed", response_model=List[StoryOwnerFeedResponse])
def get_owner_story_feed(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryOwnerFeedResponse]:
    return StoryService.get_owner_feed(current_user, db)


@router.get("/archived", response_model=List[StoryArchivedItem])
def get_archived_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[StoryArchivedItem]:
    return StoryService.get_archived_stories(current_user, db)


@router.get("/saved")
def get_saved_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    return StoryService.get_saved_stories(current_user, db)


@router.get("/mutes", response_model=List[int])
def get_muted_creators(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[int]:
    return StoryService.get_muted_creators(current_user, db)


@router.get("/music/trending", response_model=List[MusicTrackResponse])
def get_trending_music(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return MusicService.get_trending(db, limit)


@router.get("/music/search", response_model=List[MusicTrackResponse])
def search_music(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return MusicService.search(db, q, limit)


@router.get("/user/{user_id}", response_model=List[StoryItemResponse])
def get_user_stories(
    user_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryItemResponse]:
    caller_id = current_user.id if current_user else None
    return StoryService.get_user_stories(user_id, caller_id, db)


@router.get("/{story_id:int}", response_model=StoryItemResponse)
def get_single_story(
    story_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
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
    return await StoryService.upload_multiple(files, captions, audience, music_data, current_user, db, music_start_time=music_start_time or 0.0)


@router.post("", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_story(
    payload: StoryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    return StoryService.create_story(payload, current_user, db)


@router.post("/text", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_text_story(
    payload: StoryTextCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
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
        username=current_user.username,
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
    return StoryService.update_story(story_id, payload.caption, payload.audience, current_user, db)


@router.delete("/{story_id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    StoryService.delete_story(story_id, current_user, db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{story_id:int}/view")
def record_story_view(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.record_view(story_id, current_user, db)


@router.post("/{story_id:int}/like")
def like_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.like_story(story_id, current_user, db)


@router.delete("/{story_id:int}/like")
def unlike_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.unlike_story(story_id, current_user, db)


@router.post("/{story_id:int}/react", response_model=StoryReactResponse)
def react_to_story(
    story_id: int,
    payload: StoryReactRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryReactResponse:
    return StoryService.react_to_story(story_id, payload.emoji, current_user, db)


@router.post("/{story_id:int}/reply", status_code=status.HTTP_201_CREATED)
def reply_to_story(
    story_id: int,
    payload: StoryReplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.comment_story(story_id, payload.text, current_user, db)


@router.get("/{story_id:int}/comments", response_model=List[StoryReplyResponse])
def get_story_comments(
    story_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[StoryReplyResponse]:
    return StoryService.get_comments(story_id, db)


@router.post("/{story_id:int}/pause")
def pause_story(
    story_id: int,
    payload: Optional[StoryPauseRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
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
    return StoryService.get_activity(story_id, current_user, db)


@router.get("/{story_id:int}/viewers", response_model=PaginatedViewerResponse)
def get_story_viewers(
    story_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedViewerResponse:
    return StoryService.get_viewers(story_id, current_user, db, page=page, page_size=page_size)


@router.get("/{story_id:int}/likers", response_model=PaginatedLikerResponse)
def get_story_likers(
    story_id: int,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedLikerResponse:
    return StoryService.get_likers(story_id, current_user, db, page=page, page_size=page_size)


@router.post("/{story_id:int}/share", response_model=StoryShareResponse)
def share_story(
    story_id: int,
    payload: Optional[StoryShareRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StoryShareResponse:
    platform = payload.platform if payload and payload.platform else "copy_link"
    target_user_id = payload.target_user_id if payload else None
    return StoryService.share_story(story_id, platform, current_user, db, target_user_id=target_user_id)


@router.post("/{story_id:int}/save")
def save_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.save_story(story_id, current_user, db)


@router.delete("/{story_id:int}/save")
def unsave_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.unsave_story(story_id, current_user, db)


@router.post("/{story_id:int}/report")
def report_story(
    story_id: int,
    payload: StoryReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.report_story(story_id, payload.reason, current_user, db, details=payload.details)


@router.post("/mute/{user_id:int}", response_model=StoryMuteResponse)
def mute_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.mute_creator(user_id, current_user, db)


@router.delete("/mute/{user_id:int}", response_model=StoryMuteResponse)
def unmute_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.unmute_creator(user_id, current_user, db)


@router.post("/close-friends/{friend_id:int}")
def add_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.add_close_friend(current_user.id, friend_id, db)


@router.delete("/close-friends/{friend_id:int}")
def remove_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.remove_close_friend(current_user.id, friend_id, db)


@router.get("/close-friends", response_model=List[int])
def get_close_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[int]:
    return StoryService.get_close_friends(current_user.id, db)


@router.post("/follow/{user_id:int}")
def follow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.follow_user(current_user.id, user_id, db)


@router.delete("/follow/{user_id:int}")
def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StoryService.unfollow_user(current_user.id, user_id, db)
