from sqlalchemy.orm import Session
from sqlalchemy import func
from app.common.models.user import User
from app.common.models.story import Story, StoryView, StoryLike


class InfluencerService:
    @staticmethod
    def get_dashboard_stats(user: User, db: Session) -> dict:
        my_story_ids = [s.story_id for s in db.query(Story.story_id).filter(Story.user_id == user.id, Story.is_deleted == False).all()]
        total_views = 0
        total_likes = 0
        if my_story_ids:
            total_views = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id.in_(my_story_ids)).scalar() or 0
            total_likes = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id.in_(my_story_ids)).scalar() or 0

        return {
            "active_stories_count": len(my_story_ids),
            "total_views": total_views,
            "total_likes": total_likes,
        }
