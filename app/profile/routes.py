"""Another person's public profile (the Instagram-style "visit profile" page)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.common.models.social import Follow
from app.common.models.user import User
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/by-username/{username}")
def get_public_profile(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Public details of one person plus how they relate to me.

    Never includes email, phone number or date of birth.
    """
    term = username.strip().lstrip("@")
    user = (
        db.query(User)
        .filter(func.lower(User.username) == term.lower(), User.is_active.is_(True))
        .first()
    )
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Live counts straight from the follows table, same as GET /auth/profile.
    followers = db.query(Follow).filter(Follow.following_id == user.user_id).count()
    following = db.query(Follow).filter(Follow.follower_id == user.user_id).count()

    is_me = user.user_id == current_user.user_id
    is_following = False
    follows_you = False
    if not is_me:
        is_following = (
            db.query(Follow.id)
            .filter(Follow.follower_id == current_user.user_id, Follow.following_id == user.user_id)
            .first()
            is not None
        )
        follows_you = (
            db.query(Follow.id)
            .filter(Follow.follower_id == user.user_id, Follow.following_id == current_user.user_id)
            .first()
            is not None
        )

    return {
        "user_id": user.user_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "location": user.location,
        "followers_count": followers,
        "following_count": following,
        "posts_count": user.posts_count,
        "is_following": is_following,
        "follows_you": follows_you,
        "is_me": is_me,
        "joined_at": user.created_at.isoformat() if user.created_at else None,
    }
