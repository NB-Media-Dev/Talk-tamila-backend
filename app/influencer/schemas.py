from pydantic import BaseModel


class InfluencerDashboardStats(BaseModel):
    active_stories_count: int = 0
    total_views: int = 0
    total_likes: int = 0
