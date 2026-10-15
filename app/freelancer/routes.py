from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_current_freelancer, get_db
from app.common.models.user import User
from app.common.schemas.story import StoryStatsResponse, StoryWithMetrics
from app.common.services.story.story_analytics_service import StoryAnalyticsService
from app.common.services.story.story_feed_service import StoryFeedService

router = APIRouter(prefix="/freelancer", tags=["Freelancer"])


@router.get("/stats")
def get_freelancer_stats(
    current_user: User = Depends(get_current_freelancer),
    db: Session = Depends(get_db),
):
    stats = StoryAnalyticsService.get_my_story_stats(current_user, db)
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "story_stats": stats,
        "message": "Freelancer dashboard stats",
    }

@router.get("/stories", response_model=List[StoryWithMetrics])
def get_freelancer_stories(
    current_user: User = Depends(get_current_freelancer),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    return StoryFeedService.get_my_stories_with_metrics(current_user, db)


@router.get("/stories/stats", response_model=StoryStatsResponse)
def get_freelancer_story_stats(
    current_user: User = Depends(get_current_freelancer),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    return StoryAnalyticsService.get_my_story_stats(current_user, db)