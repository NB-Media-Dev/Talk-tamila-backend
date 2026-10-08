from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db, get_optional_current_user
from app.common.models.user import User
from app.common.services.post_service import PostService
from app.common.services.story_service import file_to_base64_data_url
from app.common.schemas.post import (
    PostCommentRequest,
    PostCommentResponse,
    PostFeedResponse,
    PostItemResponse,
    PostShareRequest,
)

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.get("", response_model=PostFeedResponse)
@router.get("/", response_model=PostFeedResponse)
def get_posts_feed(
    media_type: Optional[str] = Query(None, description="Filter by media type: image | video | text | poll"),
    tag: Optional[str] = Query(None, description="Filter by hashtag"),
    user_id: Optional[int] = Query(None, description="Filter by creator user ID"),
    search: Optional[str] = Query(None, description="Search keyword in title or caption"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> PostFeedResponse:
    """Public feed of all published posts (including admin posts visible to all users)."""
    return PostService.get_feed(
        db=db,
        current_user=current_user,
        media_type=media_type,
        tag=tag,
        user_id=user_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/{post_id:int}", response_model=PostItemResponse)
def get_post_detail(
    post_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> PostItemResponse:
    """Fetch detail for a single post."""
    return PostService.get_post_by_id(post_id=post_id, db=db, current_user=current_user)


@router.post("/upload-media")
async def upload_post_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a media file (image or video) and receive the data URL & media type."""
    data_url, media_type = await file_to_base64_data_url(file)
    return {
        "media_url": data_url,
        "media_type": media_type,
        "filename": file.filename,
    }


@router.get("/user/{username_or_id}", response_model=List[PostItemResponse])
def get_user_posts(
    username_or_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> List[PostItemResponse]:
    """Get all public posts by a specific user (admin or any creator) for profile display."""
    return PostService.get_user_posts(
        username_or_id=username_or_id,
        db=db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )


@router.post("/{post_id:int}/like")
def toggle_post_like(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Toggle like on a post."""
    return PostService.toggle_like(post_id=post_id, current_user=current_user, db=db)


@router.post("/{post_id:int}/comment", response_model=PostCommentResponse)
def add_post_comment(
    post_id: int,
    payload: PostCommentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PostCommentResponse:
    """Add a comment to a post."""
    return PostService.add_comment(
        post_id=post_id,
        payload=payload,
        current_user=current_user,
        db=db,
    )


@router.get("/{post_id:int}/comments", response_model=List[PostCommentResponse])
def get_post_comments(
    post_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> List[PostCommentResponse]:
    """List comments for a post."""
    return PostService.get_comments(post_id=post_id, db=db, limit=limit, offset=offset)


@router.post("/{post_id:int}/save")
def toggle_post_save(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Toggle bookmark/save on a post."""
    return PostService.toggle_save(post_id=post_id, current_user=current_user, db=db)


@router.post("/{post_id:int}/share")
def record_post_share(
    post_id: int,
    payload: Optional[PostShareRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record a share on a post."""
    platform = payload.platform if payload else "Talk Tamila"
    return PostService.record_share(
        post_id=post_id,
        platform=platform,
        current_user=current_user,
        db=db,
    )


@router.post("/{post_id:int}/view")
def record_post_view(
    post_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Record a view on a post."""
    return PostService.record_view(post_id=post_id, current_user=current_user, db=db)
