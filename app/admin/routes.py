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
    AdminWarnRequest,
    AdminWarnResponse,
)
from app.common.schemas.story import (
    StoryCreateRequest,
    StoryItemResponse,
    StoryStatsResponse,
    StoryWithMetrics,
)
from app.common.enums import StoryAudienceEnum
from app.common.services.story.story_analytics_service import StoryAnalyticsService
from app.common.services.story.story_creation_service import StoryCreationService
from app.common.services.story.story_feed_service import StoryFeedService

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
def create_story(
    payload: StoryCreateRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StoryItemResponse:
    payload.audience = StoryAudienceEnum.PUBLIC
    return StoryCreationService.create_story(payload, current_admin, db)


@router.get("/stories/stats", response_model=AdminPlatformStoryStats)
def get_platform_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminPlatformStoryStats:
    return AdminService.get_platform_story_stats(db)


@router.get("/stories/my", response_model=List[StoryWithMetrics])
def get_my_stories_with_metrics(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    return StoryFeedService.get_my_stories_with_metrics(current_admin, db)


@router.get("/stories/my/stats", response_model=StoryStatsResponse)
def get_my_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    return StoryAnalyticsService.get_my_story_stats(current_admin, db)


@router.get("/stories/reports", response_model=List[AdminReportItem])
def get_story_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[AdminReportItem]:
    return AdminService.get_story_reports(db, limit=limit, offset=offset)


@router.delete("/stories/{story_id:int}")
def delete_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.delete_story(story_id, db)


@router.patch("/stories/{story_id:int}/restore")
def restore_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.restore_story(story_id, db)


@router.patch("/users/{user_id:int}/ban")
@router.post("/users/{user_id:int}/ban")
def ban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.ban_user(user_id, current_admin, db)


@router.patch("/users/{user_id:int}/unban")
@router.post("/users/{user_id:int}/unban")
def unban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return AdminService.unban_user(user_id, db)


@router.post("/stories/{story_id:int}/warn", response_model=AdminWarnResponse)
def warn_story_creator(
    story_id: int,
    payload: AdminWarnRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminWarnResponse:
    result = AdminService.warn_story_creator(
        story_id=story_id,
        message=payload.message,
        current_admin=current_admin,
        db=db,
        target_user_id=payload.target_user_id,
        warning_type=payload.warning_type,
    )
    return AdminWarnResponse(**result)


@router.post("/users/{user_id:int}/warn", response_model=AdminWarnResponse)
def warn_user(
    user_id: int,
    payload: AdminWarnRequest,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminWarnResponse:
    result = AdminService.warn_user(
        user_id=user_id,
        message=payload.message,
        current_admin=current_admin,
        db=db,
        story_id=payload.story_id,
        warning_type=payload.warning_type,
    )
    return AdminWarnResponse(**result)

