"""Settings + follow-list endpoints (names/avatars included).

Self-contained on purpose: it only depends on models and core dependencies,
so it works no matter what StoryService currently contains.

Final URLs (API prefix /api/v1 is added by main.py):
    GET    /api/v1/stories/settings/muted
    DELETE /api/v1/stories/settings/muted/{user_id}
    GET    /api/v1/stories/settings/close-friends
    POST   /api/v1/stories/settings/close-friends/{friend_id}
    DELETE /api/v1/stories/settings/close-friends/{friend_id}
    GET    /api/v1/stories/settings/followers/{user_id}
    GET    /api/v1/stories/settings/following/{user_id}
"""
from typing import List, Set

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

# IMPORTANT: keep app.core imported BEFORE the models. Importing the models
# first can trigger a circular import (models -> app.core -> models).
from app.core.dependencies import get_current_user, get_db
from app.common.models.social import CloseFriend, Follow
from app.common.models.story import StoryMute
from app.common.models.user import User

router = APIRouter(prefix="/stories/settings", tags=["Settings"])


def _person(u: User) -> dict:
    return {
        "id": u.user_id,
        "user_id": u.user_id,
        "username": u.username,
        "full_name": u.full_name,
        "avatar_url": u.avatar_url,
        "role": u.role,
        "bio": u.bio,
    }


# ───────────────────────── Muted creators ─────────────────────────
@router.get("/muted")
def list_muted_creators(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .join(StoryMute, StoryMute.muted_user_id == User.user_id)
        .filter(StoryMute.user_id == current_user.user_id)
        .order_by(StoryMute.created_at.desc())
        .all()
    )
    return [_person(u) for u in users]


@router.delete("/muted/{user_id:int}")
def unmute_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(StoryMute)
        .filter(
            StoryMute.user_id == current_user.user_id,
            StoryMute.muted_user_id == user_id,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return {"success": True, "muted_user_id": user_id, "is_muted": False}


# ───────────────────────── Close friends ─────────────────────────
@router.get("/close-friends")
def list_close_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .join(CloseFriend, CloseFriend.friend_id == User.user_id)
        .filter(CloseFriend.user_id == current_user.user_id)
        .order_by(CloseFriend.created_at.desc())
        .all()
    )
    return [_person(u) for u in users]


@router.post("/close-friends/{friend_id:int}")
def add_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if friend_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="You can't add yourself.")
    target = db.query(User).filter(User.user_id == friend_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    exists = (
        db.query(CloseFriend)
        .filter(
            CloseFriend.user_id == current_user.user_id,
            CloseFriend.friend_id == friend_id,
        )
        .first()
    )
    if not exists:
        db.add(CloseFriend(user_id=current_user.user_id, friend_id=friend_id))
        db.commit()
    return {"success": True, "friend_id": friend_id, "is_close_friend": True}


@router.delete("/close-friends/{friend_id:int}")
def remove_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(CloseFriend)
        .filter(
            CloseFriend.user_id == current_user.user_id,
            CloseFriend.friend_id == friend_id,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return {"success": True, "friend_id": friend_id, "is_close_friend": False}


# ───────────────────────── Followers / Following ─────────────────────────
def _my_following_ids(db: Session, me: int) -> Set[int]:
    rows = db.query(Follow.following_id).filter(Follow.follower_id == me).all()
    return {r[0] for r in rows}


def _follow_person(u: User, my_following: Set[int]) -> dict:
    data = _person(u)
    data["followers_count"] = u.followers_count
    data["is_following"] = u.user_id in my_following
    return data


def _ensure_user_exists(db: Session, user_id: int) -> None:
    if db.query(User.user_id).filter(User.user_id == user_id).first() is None:
        raise HTTPException(status_code=404, detail="User not found.")


@router.get("/followers/{user_id:int}")
def list_followers(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """People who follow `user_id`."""
    _ensure_user_exists(db, user_id)
    mine = _my_following_ids(db, current_user.user_id)
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .join(Follow, Follow.follower_id == User.user_id)
        .filter(Follow.following_id == user_id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_follow_person(u, mine) for u in users]


@router.get("/following/{user_id:int}")
def list_following(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    """People that `user_id` follows."""
    _ensure_user_exists(db, user_id)
    mine = _my_following_ids(db, current_user.user_id)
    users = (
        db.query(User)
        .options(joinedload(User.profile))
        .join(Follow, Follow.following_id == User.user_id)
        .filter(Follow.follower_id == user_id)
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_follow_person(u, mine) for u in users]