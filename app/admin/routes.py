from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, get_current_admin
from app.admin.services import AdminService
from app.common.models.user import User
from app.admin.schemas import (
    AdminPlatformStoryStats,
    AdminStoryItem,
    AdminReportItem,
    AdminStoryWarningRequest,
)
from app.common.schemas.story import (
    StoryCreateRequest,
    StoryItemResponse,
    StoryStatsResponse,
    StoryWithMetrics,
)
from app.common.schemas.post import (
    PostCreateRequest,
    PostFeedResponse,
    PostItemResponse,
    PostPlatformStats,
    PostUpdateRequest,
)
from app.common.services.post_service import PostService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stories", response_model=List[AdminStoryItem])
def get_all_stories(
    role: Optional[str] = Query(None, description="Filter by creator role: influencer | freelancer | admin"),
    audience: Optional[str] = Query(None, description="Filter by audience: PUBLIC | FOLLOWERS | CLOSE_FRIENDS"),
    is_deleted: Optional[bool] = Query(None, description="Filter active or deleted stories"),
    user_id: Optional[int] = Query(None, description="Filter stories by creator user ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[AdminStoryItem]:
    return AdminService.get_all_stories(
        db=db,
        role=role,
        audience=audience,
        is_deleted=is_deleted,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


@router.post("/stories", response_model=StoryItemResponse, status_code=status.HTTP_201_CREATED)
def admin_create_story(
    payload: StoryCreateRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    from app.common.enums import StoryAudienceEnum
    from app.common.services.story_service import StoryService
    payload.audience = StoryAudienceEnum.PUBLIC
    return StoryService.create_story(payload, current_admin, db)


@router.get("/stories/stats", response_model=AdminPlatformStoryStats)
def get_platform_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminPlatformStoryStats:
    return AdminService.get_platform_story_stats(db)


@router.get("/stories/my", response_model=List[StoryWithMetrics])
def get_admin_my_stories(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stories_with_metrics(current_admin, db)


@router.get("/stories/my/stats", response_model=StoryStatsResponse)
def get_admin_my_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stats(current_admin, db)


@router.get("/stories/reports", response_model=List[AdminReportItem])
def get_story_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[AdminReportItem]:
    return AdminService.get_story_reports(db, limit=limit, offset=offset)


@router.delete("/stories/{story_id:int}")
def admin_delete_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.delete_story(story_id, db)


@router.patch("/stories/{story_id:int}/restore")
def admin_restore_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.restore_story(story_id, db)


@router.patch("/users/{user_id:int}/ban")
def admin_ban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.ban_user(user_id, current_admin, db)


@router.patch("/users/{user_id:int}/unban")
def admin_unban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.unban_user(user_id, db)


@router.post("/stories/{story_id:int}/warn")
def admin_warn_story_creator(
    story_id: int,
    payload: AdminStoryWarningRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.warn_story_creator(
        story_id=story_id,
        message=payload.message,
        current_admin=current_admin,
        db=db,
        target_user_id=payload.user_id,
        warning_type=payload.warning_type,
    )


# ==================== ADMIN POST MODULE ====================

@router.post("/posts", response_model=PostItemResponse, status_code=status.HTTP_201_CREATED)
def admin_create_post(
    payload: PostCreateRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> PostItemResponse:
    """Admin-only endpoint to create and upload a post.
    The post is automatically assigned to the Admin ID and published publicly for all users to see.
    """
    return PostService.create_admin_post(
        payload=payload,
        current_admin=current_admin,
        db=db,
    )


@router.get("/posts", response_model=PostFeedResponse)
def get_admin_posts_list(
    media_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> PostFeedResponse:
    """Get all posts on the platform with admin management controls."""
    return PostService.get_feed(
        db=db,
        current_user=current_admin,
        media_type=media_type,
        tag=tag,
        limit=limit,
        offset=offset,
    )


@router.get("/posts/my", response_model=List[PostItemResponse])
def get_admin_my_posts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[PostItemResponse]:
    """Get all posts published by this admin."""
    return PostService.get_user_posts(
        username_or_id=str(current_admin.user_id),
        db=db,
        current_user=current_admin,
        limit=limit,
        offset=offset,
    )


@router.get("/posts/stats", response_model=PostPlatformStats)
def get_admin_post_platform_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> PostPlatformStats:
    """Get platform-wide post metrics."""
    return PostService.get_platform_post_stats(db=db)


@router.patch("/posts/{post_id:int}", response_model=PostItemResponse)
def admin_update_post(
    post_id: int,
    payload: PostUpdateRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> PostItemResponse:
    """Admin update post contents or status."""
    return PostService.update_post(
        post_id=post_id,
        payload=payload,
        current_user=current_admin,
        db=db,
    )


@router.delete("/posts/{post_id:int}")
def admin_delete_post(
    post_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin delete post from platform."""
    return PostService.delete_post(
        post_id=post_id,
        current_user=current_admin,
        db=db,
    )


