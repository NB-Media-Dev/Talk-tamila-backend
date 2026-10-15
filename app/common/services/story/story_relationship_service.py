"""Creator relationships seen from stories: mute, follow, suggestions."""

import logging
from typing import List

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.common.models.social import Notification, Follow
from app.common.models.story import (
    StoryMute,
)
from app.common.models.user import User

from app.common.services.story.story_helpers import (
    make_naive,
    utc_now,
)

logger = logging.getLogger(__name__)


class StoryRelationshipService:
    @staticmethod
    def mute_creator(muted_user_id: int, current_user: User, db: Session) -> dict:
        caller_id = int(getattr(current_user, "user_id", None) or getattr(current_user, "id", None))
        muted_id = int(muted_user_id)
        if muted_id == caller_id:
            raise HTTPException(status_code=400, detail="Cannot mute yourself.")

        existing = db.query(StoryMute).filter(
            StoryMute.user_id == caller_id,
            StoryMute.muted_user_id == muted_id,
        ).first()
        if not existing:
            mute = StoryMute(
                user_id=caller_id,
                muted_user_id=muted_id,
                created_at=make_naive(utc_now()),
            )
            db.add(mute)
            db.commit()
        return {
            "success": True,
            "message": "Stories from this user muted.",
            "muted_user_id": muted_id,
            "is_muted": True,
        }

    @staticmethod
    def unmute_creator(muted_user_id: int, current_user: User, db: Session) -> dict:
        caller_id = int(getattr(current_user, "user_id", None) or getattr(current_user, "id", None))
        muted_id = int(muted_user_id)
        existing = db.query(StoryMute).filter(
            StoryMute.user_id == caller_id,
            StoryMute.muted_user_id == muted_id,
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
        return {
            "success": True,
            "message": "Stories from this user unmuted.",
            "muted_user_id": muted_id,
            "is_muted": False,
        }

    @staticmethod
    def follow_user(follower_id: int, following_id: int, db: Session) -> dict:
        if follower_id == following_id:
            raise HTTPException(status_code=400, detail="You can't follow yourself.")

        target = db.query(User).filter(User.user_id == following_id).first()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")

        follower = db.query(User).filter(User.user_id == follower_id).first()
        if follower is None:
            raise HTTPException(status_code=404, detail="Follower not found.")

        existing = db.query(Follow).filter(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        ).first()

        owner_name = follower.username

        if existing is None:
            db.add(Follow(follower_id=follower_id, following_id=following_id, user_name=owner_name))
            follower._ensure_profile().following_count += 1
            target._ensure_profile().followers_count += 1
            db.commit()
            db.refresh(target)
        else:
            if not existing.user_name and owner_name:
                existing.user_name = owner_name
                db.commit()

        return {
            "success": True,
            "is_following": True,
            "followers_count": target.followers_count,
            "user_name": owner_name,
        }

    @staticmethod
    def unfollow_user(follower_id: int, following_id: int, db: Session) -> dict:
        target = db.query(User).filter(User.user_id == following_id).first()

        existing = db.query(Follow).filter(
            Follow.follower_id == follower_id,
            Follow.following_id == following_id,
        ).first()

        if existing is not None:
            db.delete(existing)
            try:
                db.query(Notification).filter(
                    Notification.user_id == following_id,
                    Notification.type == "follow",
                    Notification.reference_id == follower_id,
                ).delete(synchronize_session=False)
            except Exception:
                pass
            follower = db.query(User).filter(User.user_id == follower_id).first()
            if follower is not None and follower.profile is not None:
                follower.profile.following_count = max(0, follower.profile.following_count - 1)
            if target is not None and target.profile is not None:
                target.profile.followers_count = max(0, target.profile.followers_count - 1)
            db.commit()
            if target is not None:
                db.refresh(target)

        return {
            "success": True,
            "is_following": False,
            "followers_count": target.followers_count if target else 0,
        }

    @staticmethod
    def get_suggestions(current_user: User, db: Session, limit: int = 10) -> List[dict]:
        already_following = db.query(Follow.following_id).filter(
            Follow.follower_id == current_user.id
        )
        candidates = (
            db.query(User)
            .filter(User.user_id != current_user.id)
            .filter(~User.user_id.in_(already_following))
            .order_by(func.rand())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": u.user_id,
                "user_id": u.user_id,
                "username": u.username,
                "full_name": u.full_name,
                "avatar_url": u.avatar_url,
                "role": u.role,
                "bio": u.bio,
                "followers_count": u.followers_count,
                "is_following": False,
            }
            for u in candidates
        ]
