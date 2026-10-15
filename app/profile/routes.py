from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.models.user import User
from app.common.services.post_service import PostService
from app.common.services.profile_service import ProfileService
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/by-username/{username}")
def get_public_profile(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ProfileService.get_public_profile(db, current_user, username)


@router.get("/by-username/{username}/posts")
def get_user_public_posts(
    username: str,
    limit: int = 30,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Public posts by this user (including admin posts) for their profile page."""
    return PostService.get_user_public_posts(
        username_or_id=username,
        db=db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )
