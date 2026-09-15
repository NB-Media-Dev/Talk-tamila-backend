from typing import Optional
from sqlalchemy.orm import Session
from app.common.models.social import Profile
from app.common.schemas.social import ProfileResponse


class SocialService:
    @staticmethod
    def get_profile(user_id: int, db: Session) -> Optional[ProfileResponse]:
        profile = db.query(Profile).filter(Profile.user_id == user_id).first()
        if not profile:
            return None
        return ProfileResponse.model_validate(profile)
