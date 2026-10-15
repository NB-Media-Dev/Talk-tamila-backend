"""Story privacy settings: muted creators, close friends, and follower / following lists."""

from typing import List, Set

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.common.models.social import CloseFriend, Follow
from app.common.models.story import StoryMute
from app.common.models.user import User


class StorySettingsService:
    # ------------------------------------------------------------- muted creators
    @staticmethod
    def list_muted_creators(db: Session, current_user: User) -> List[dict]:
        muted_users = (
            db.query(User)
            .options(joinedload(User.profile))
            .join(StoryMute, StoryMute.muted_user_id == User.user_id)
            .filter(StoryMute.user_id == current_user.user_id)
            .order_by(StoryMute.created_at.desc())
            .all()
        )
        return [StorySettingsService._person_summary(user) for user in muted_users]

    @staticmethod
    def remove_muted_creator(db: Session, current_user: User, muted_user_id: int) -> dict:
        mute = (
            db.query(StoryMute)
            .filter(
                StoryMute.user_id == current_user.user_id,
                StoryMute.muted_user_id == muted_user_id,
            )
            .first()
        )
        if mute:
            db.delete(mute)
            db.commit()
        return {"success": True, "muted_user_id": muted_user_id, "is_muted": False}

    # -------------------------------------------------------------- close friends
    @staticmethod
    def list_close_friends(db: Session, current_user: User) -> List[dict]:
        close_friends = (
            db.query(User)
            .options(joinedload(User.profile))
            .join(CloseFriend, CloseFriend.friend_id == User.user_id)
            .filter(CloseFriend.user_id == current_user.user_id)
            .order_by(CloseFriend.created_at.desc())
            .all()
        )
        return [StorySettingsService._person_summary(user) for user in close_friends]

    @staticmethod
    def add_close_friend(db: Session, current_user: User, friend_id: int) -> dict:
        if friend_id == current_user.user_id:
            raise HTTPException(status_code=400, detail="You can't add yourself.")
        if db.query(User).filter(User.user_id == friend_id).first() is None:
            raise HTTPException(status_code=404, detail="User not found.")

        already_close_friend = (
            db.query(CloseFriend)
            .filter(
                CloseFriend.user_id == current_user.user_id,
                CloseFriend.friend_id == friend_id,
            )
            .first()
        )
        if not already_close_friend:
            db.add(CloseFriend(user_id=current_user.user_id, friend_id=friend_id))
            db.commit()
        return {"success": True, "friend_id": friend_id, "is_close_friend": True}

    @staticmethod
    def remove_close_friend(db: Session, current_user: User, friend_id: int) -> dict:
        close_friend = (
            db.query(CloseFriend)
            .filter(
                CloseFriend.user_id == current_user.user_id,
                CloseFriend.friend_id == friend_id,
            )
            .first()
        )
        if close_friend:
            db.delete(close_friend)
            db.commit()
        return {"success": True, "friend_id": friend_id, "is_close_friend": False}

    # ------------------------------------------------------ followers / following
    @staticmethod
    def list_followers(db: Session, current_user: User, user_id: int, limit: int) -> List[dict]:
        """People who follow `user_id`."""
        StorySettingsService._ensure_user_exists(db, user_id)
        people_i_follow = StorySettingsService._ids_followed_by(db, current_user.user_id)
        followers = (
            db.query(User)
            .options(joinedload(User.profile))
            .join(Follow, Follow.follower_id == User.user_id)
            .filter(Follow.following_id == user_id)
            .order_by(Follow.created_at.desc())
            .limit(limit)
            .all()
        )
        return [StorySettingsService._follow_list_entry(user, people_i_follow) for user in followers]

    @staticmethod
    def list_following(db: Session, current_user: User, user_id: int, limit: int) -> List[dict]:
        """People that `user_id` follows."""
        StorySettingsService._ensure_user_exists(db, user_id)
        people_i_follow = StorySettingsService._ids_followed_by(db, current_user.user_id)
        following = (
            db.query(User)
            .options(joinedload(User.profile))
            .join(Follow, Follow.following_id == User.user_id)
            .filter(Follow.follower_id == user_id)
            .order_by(Follow.created_at.desc())
            .limit(limit)
            .all()
        )
        return [StorySettingsService._follow_list_entry(user, people_i_follow) for user in following]

    # -------------------------------------------------------------------- helpers
    @staticmethod
    def _person_summary(user: User) -> dict:
        return {
            "id": user.user_id,
            "user_id": user.user_id,
            "username": user.username,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "role": user.role,
            "bio": user.bio,
        }

    @staticmethod
    def _follow_list_entry(user: User, people_i_follow: Set[int]) -> dict:
        entry = StorySettingsService._person_summary(user)
        entry["followers_count"] = user.followers_count
        entry["is_following"] = user.user_id in people_i_follow
        return entry

    @staticmethod
    def _ids_followed_by(db: Session, user_id: int) -> Set[int]:
        rows = db.query(Follow.following_id).filter(Follow.follower_id == user_id).all()
        return {row[0] for row in rows}

    @staticmethod
    def _ensure_user_exists(db: Session, user_id: int) -> None:
        if db.query(User.user_id).filter(User.user_id == user_id).first() is None:
            raise HTTPException(status_code=404, detail="User not found.")
