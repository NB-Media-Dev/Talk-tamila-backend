from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db, get_current_user, get_current_influencer
from app.influencer.services import InfluencerService
from app.common.models.user import User
from app.common.schemas.story import StoryStatsResponse, StoryWithMetrics

router = APIRouter(prefix="/influencer", tags=["Influencer"])


@router.get("/stats")
def get_influencer_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return InfluencerService.get_dashboard_stats(current_user, db)

@router.get("/stories", response_model=List[StoryWithMetrics])
def get_influencer_stories(
    current_user: User = Depends(get_current_influencer),
    db: Session = Depends(get_db),
) -> List[StoryWithMetrics]:
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stories_with_metrics(current_user, db)


@router.get("/stories/stats", response_model=StoryStatsResponse)
def get_influencer_story_stats(
    current_user: User = Depends(get_current_influencer),
    db: Session = Depends(get_db),
) -> StoryStatsResponse:
    from app.common.services.story_service import StoryService
    return StoryService.get_my_stats(current_user, db)
