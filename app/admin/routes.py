from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, get_current_admin
from app.admin.services import AdminService
from app.common.models.user import User
from app.admin.schemas import (
    AdminOverview,
    AdminPlatformStoryStats,
    AdminStoryItem,
    AdminReportItem,
)
from app.common.schemas.story import (
    StoryCreateRequest,
    StoryItemResponse,
    StoryStatsResponse,
    StoryWithMetrics,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/overview", response_model=AdminOverview)
def get_admin_overview(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminOverview:
    """Dashboard overview for Admin (total users, stories, views, likes, reports)."""
    return AdminService.get_overview(db)


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
    """Admin-only: fetch all stories across the platform with filtering, pagination, and metrics."""
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
    """Admin-only: create an official platform announcement story (strictly and always PUBLIC)."""
    from app.common.enums import StoryAudienceEnum
    from app.common.services.story_service import StoryService
    payload.audience = StoryAudienceEnum.PUBLIC
    return StoryService.create_story(payload, current_admin, db)


@router.get("/stories/stats", response_model=AdminPlatformStoryStats)
def get_platform_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminPlatformStoryStats:
    """Admin-only: platform-wide aggregate story statistics."""
    return AdminService.get_platform_story_stats(db)


@router.get("/stories/my", response_model=List[StoryWithMetrics])
def get_admin_my_stories(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    """Admin-only: fetch your own stories from the last 7 days with full engagement metrics."""
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stories_with_metrics(current_admin, db)


@router.get("/stories/my/stats", response_model=StoryStatsResponse)
def get_admin_my_story_stats(
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    """Admin-only: aggregate engagement stats for stories created by this admin."""
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stats(current_admin, db)


@router.get("/stories/reports", response_model=List[AdminReportItem])
def get_story_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> List[AdminReportItem]:
    """Admin-only: list all reported stories for moderation review."""
    return AdminService.get_story_reports(db, limit=limit, offset=offset)


@router.delete("/stories/{story_id:int}")
def admin_delete_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin-only: moderate/delete any story on the platform."""
    return AdminService.delete_story(story_id, db)


@router.patch("/stories/{story_id:int}/restore")
def admin_restore_story(
    story_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin-only: restore a previously deleted story."""
    return AdminService.restore_story(story_id, db)


@router.patch("/users/{user_id:int}/ban")
def admin_ban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin-only: suspend a user account. They can no longer log in, and any
    token they're already holding stops working on the next request."""
    return AdminService.ban_user(user_id, current_admin, db)


@router.patch("/users/{user_id:int}/unban")
def admin_unban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Admin-only: reinstate a previously suspended user account."""
    return AdminService.unban_user(user_id, db)