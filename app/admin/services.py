from sqlalchemy.orm import Session
from sqlalchemy import func
from app.common.models.user import User
from app.common.models.story import Story


class AdminService:
    @staticmethod
    def get_overview(db: Session) -> dict:
        total_users = db.query(func.count(User.user_id)).scalar() or 0
        total_stories = db.query(func.count(Story.story_id)).scalar() or 0
        return {"total_users": total_users, "total_stories": total_stories}
