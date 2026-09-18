from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db, get_current_user, get_current_freelancer
from app.common.models.user import User
from app.common.schemas.story import StoryStatsResponse, StoryWithMetrics

router = APIRouter(prefix="/freelancer", tags=["Freelancer"])


@router.get("/health")
def freelancer_health():
    return {"status": "ok", "role": "freelancer"}


@router.get("/stats")
def get_freelancer_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dashboard stats for freelancer."""
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "message": "Freelancer dashboard stats",
    }

@router.get("/stories", response_model=List[StoryWithMetrics])
def get_freelancer_stories(
    current_user: User = Depends(get_current_freelancer),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    """Freelancer-only: fetch your stories from the last 7 days with
    full engagement metrics (views, likes, replies, shares, engagement rate).

    Only accessible by users with role = freelancer or admin.
    """
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stories_with_metrics(current_user, db)


@router.get("/stories/stats", response_model=StoryStatsResponse)
def get_freelancer_story_stats(
    current_user: User = Depends(get_current_freelancer),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    """Freelancer-only: aggregate story engagement stats (total views, likes, replies, shares)."""
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stats(current_user, db)
