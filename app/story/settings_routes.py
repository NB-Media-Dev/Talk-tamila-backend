from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.common.models.user import User
from app.common.services.story.story_settings_service import StorySettingsService
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/stories/settings", tags=["Settings"])


# ============================================================ muted creators
@router.get("/muted")
def list_muted_creators(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    return StorySettingsService.list_muted_creators(db, current_user)


@router.delete("/muted/{user_id:int}")
def remove_muted_creator(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StorySettingsService.remove_muted_creator(db, current_user, user_id)


# ============================================================ close friends
@router.get("/close-friends")
def list_close_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    return StorySettingsService.list_close_friends(db, current_user)


@router.post("/close-friends/{friend_id:int}")
def add_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StorySettingsService.add_close_friend(db, current_user, friend_id)


@router.delete("/close-friends/{friend_id:int}")
def remove_close_friend(
    friend_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return StorySettingsService.remove_close_friend(db, current_user, friend_id)


# ============================================================ followers / following
@router.get("/followers/{user_id:int}")
def list_followers(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    return StorySettingsService.list_followers(db, current_user, user_id, limit)


@router.get("/following/{user_id:int}")
def list_following(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[dict]:
    return StorySettingsService.list_following(db, current_user, user_id, limit)
