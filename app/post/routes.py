import re
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.common.models.post import STATUS_PUBLISHED
from app.common.models.user import User
from app.common.schemas.post import (
    CommentCreate,
    CommentDeleteResult,
    CommentLikeState,
    CommentListResponse,
    CommentOut,
    FeedResponse,
    InsightsOut,
    LikersResponse,
    LikeState,
    PollOut,
    PostEditRequest,
    ReportRequest,
    SaveState,
    ScheduledListResponse,
    ScheduleRequest,
    ShareRequest,
    ShareState,
    VoteRequest,
)
from app.common.services.post_engagement_service import PostEngagementService as Engage
from app.common.services.post_service import PostService, max_bytes_for, to_utc_naive
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    get_db,
    get_optional_current_user,
)

router = APIRouter(prefix="/posts", tags=["Posts"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")

CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
OptionalUser = Annotated[Optional[User], Depends(get_optional_current_user)]
DB = Annotated[Session, Depends(get_db)]


@router.post("", response_model=FeedResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    current_user: CurrentUser,
    db: DB,
    post_type: str = Form(...),
    content: Optional[str] = Form(None),
    gif_url: Optional[str] = Form(None),
    poll_options: Optional[str] = Form(None, description="JSON list of option texts"),
    scheduled_at: Optional[str] = Form(
        None,
        description=(
            "ISO-8601 time WITH timezone, e.g. 2026-10-10T18:30:00+05:30 or ...Z. "
            "Between 1 minute and 365 days ahead. Leave empty to publish now."
        ),
    ),
    comments_disabled: bool = Form(False),
    hide_like_count: bool = Form(False),
    music_id: Optional[int] = Form(None),
    music_title: Optional[str] = Form(None),
    music_artist: Optional[str] = Form(None),
    music_url: Optional[str] = Form(None),
    music_thumbnail: Optional[str] = Form(None),
    music_start_time: Optional[float] = Form(None),
    music_duration: Optional[float] = Form(None),
    media: Optional[UploadFile] = File(None),
) -> FeedResponse:
    PostService.assert_can_create(current_user)
    when = PostService.parse_scheduled_at(scheduled_at)

    media_bytes: Optional[bytes] = None
    if media is not None and media.filename:
        limit = max_bytes_for(post_type.strip().lower())
        media_bytes = await media.read(limit + 1)
        if len(media_bytes) > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"That file is too large. Maximum size is {limit // (1024 * 1024)} MB.",
            )

    return PostService.create_post(
        db=db,
        user=current_user,
        post_type=post_type,
        content=content,
        media_bytes=media_bytes,
        gif_url=gif_url,
        poll_options=PostService.parse_poll_options(poll_options),
        scheduled_at=when,
        music=PostService.music_from_form(
            music_id,
            music_title,
            music_artist,
            music_url,
            music_thumbnail,
            music_start_time,
            music_duration,
        ),
        comments_disabled=comments_disabled,
        hide_like_count=hide_like_count,
    )


@router.get("", response_model=FeedResponse)
def get_feed(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=10, ge=1, le=30),
    before_id: Optional[int] = Query(default=None, ge=1),
) -> FeedResponse:
    return PostService.get_feed(db, current_user, limit, before_id)


@router.get("/scheduled", response_model=ScheduledListResponse)
def list_scheduled_posts(
    admin: AdminUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    from_at: Optional[datetime] = Query(
        default=None, description="Only posts due at or after this time (with timezone)"
    ),
    to_at: Optional[datetime] = Query(
        default=None, description="Only posts due at or before this time (with timezone)"
    ),
) -> ScheduledListResponse:
    start = to_utc_naive(from_at) if from_at else None
    end = to_utc_naive(to_at) if to_at else None
    if start and end and start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="from_at must be before to_at."
        )
    return PostService.list_scheduled(db, admin, limit, offset, start, end)


@router.get("/saved", response_model=FeedResponse)
def list_saved_posts(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
) -> FeedResponse:
    """Posts I saved, most recently saved first."""
    return PostService.get_saved(db, current_user, limit, offset)


@router.get("/archived", response_model=FeedResponse)
def list_archived_posts(
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
) -> FeedResponse:
    """My own archived posts."""
    return PostService.get_archived(db, current_user, limit, offset)


@router.get("/{post_id:int}", response_model=FeedResponse)
def get_one_post(post_id: int,
     current_user: CurrentUser, 
     db: DB) -> FeedResponse:
    """One post (items[0]). Used by shared links and notifications."""
    return PostService.get_one(db, current_user, post_id)



@router.patch("/{post_id:int}/schedule", response_model=FeedResponse)
def reschedule_post(
    post_id: int, 
    payload: ScheduleRequest, 
    admin: AdminUser,
    db: DB
) -> FeedResponse:
    return PostService.reschedule(db, admin, post_id, payload.scheduled_at)


@router.post("/{post_id:int}/publish", response_model=FeedResponse)
def publish_post_now(post_id: int,
     admin: AdminUser, 
     db: DB) -> FeedResponse:
    return PostService.publish_now(db, admin, post_id)


@router.patch("/{post_id:int}", response_model=FeedResponse)
def edit_post(
    post_id: int, 
    payload: PostEditRequest,
    current_user: CurrentUser,
    db: DB
) -> FeedResponse:
    """Owner only: caption, song, comments on/off, hide like count."""
    return PostService.edit_post(db, current_user, post_id, payload)


@router.post("/{post_id:int}/archive", response_model=FeedResponse)
def archive_post(post_id: int,
    current_user: CurrentUser, 
    db: DB) -> FeedResponse:
    return PostService.set_archived(db, current_user, post_id, True)


@router.post("/{post_id:int}/restore", response_model=FeedResponse)
def restore_post(post_id: int,
    current_user: CurrentUser, 
    db: DB) -> FeedResponse:
    return PostService.set_archived(db, current_user, post_id, False)


@router.post("/{post_id:int}/pin", response_model=FeedResponse)
def pin_post(post_id: int, 
    current_user: CurrentUser,
    db: DB) -> FeedResponse:
    return PostService.set_pinned(db, current_user, post_id, True)


@router.delete("/{post_id:int}/pin", response_model=FeedResponse)
def unpin_post(post_id: int,
    current_user: CurrentUser, 
    db: DB) -> FeedResponse:
    return PostService.set_pinned(db, current_user, post_id, False)


@router.delete("/{post_id:int}")
def delete_post(post_id: int,
    current_user: CurrentUser, 
    db: DB) -> dict:
    """Delete a post. For a scheduled post this cancels it."""
    return PostService.delete_post(db, current_user, post_id)



@router.post("/{post_id:int}/vote", response_model=PollOut)
def vote_in_poll(post_id: int,
    payload: VoteRequest, 
    current_user: CurrentUser, 
    db: DB) -> PollOut:
    return PostService.vote(db, current_user, post_id, payload.option_id)


@router.post("/{post_id:int}/like", response_model=LikeState)
def like_post(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> LikeState:
    return Engage.like(db, current_user, post_id)


@router.delete("/{post_id:int}/like", response_model=LikeState)
def unlike_post(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> LikeState:
    return Engage.unlike(db, current_user, post_id)


@router.get("/{post_id:int}/likes", response_model=LikersResponse)
def list_post_likers(
    post_id: int,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LikersResponse:
    return Engage.list_likers(db, current_user, post_id, limit, offset)


@router.post("/{post_id:int}/save", response_model=SaveState)
def save_post(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> SaveState:
    return Engage.save(db, current_user, post_id)


@router.delete("/{post_id:int}/save", response_model=SaveState)
def unsave_post(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> SaveState:
    return Engage.unsave(db, current_user, post_id)


@router.post("/{post_id:int}/share", response_model=ShareState)
def share_post(
    post_id: int, 
    payload: ShareRequest, 
    current_user: CurrentUser, 
    db: DB
) -> ShareState:
    """Count a share (link copied, or sent to people in messages)."""
    return Engage.share(db, current_user, post_id, payload.channel, payload.recipients)


@router.post("/{post_id:int}/view")
def view_post(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> dict:
    """Count one view per person. Powers the reach number in insights."""
    return Engage.record_view(db, current_user, post_id)


@router.post("/{post_id:int}/report")
def report_post(post_id: int, 
    payload: ReportRequest,
    current_user: CurrentUser, 
    db: DB) -> dict:
    return Engage.report(db, current_user, post_id, payload.reason)


@router.get("/{post_id:int}/insights", response_model=InsightsOut)
def post_insights(post_id: int, 
    current_user: CurrentUser, 
    db: DB) -> InsightsOut:
    """Owner (or admin) only: how the post is performing."""
    return Engage.insights(db, current_user, post_id)



@router.get("/{post_id:int}/comments" \
"", response_model=CommentListResponse)
def list_post_comments(
    post_id: int,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=50),
    before_id: Optional[int] = Query(default=None, ge=1),
) -> CommentListResponse:
    return Engage.list_comments(db, current_user, post_id, limit, before_id)


@router.post(
    "/{post_id:int}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
def add_post_comment(
    post_id: int, 
    payload: CommentCreate, 
    current_user: CurrentUser, 
    db: DB
) -> CommentOut:
    return Engage.add_comment(db, current_user, post_id, payload.body, payload.parent_id)


@router.get("/{post_id:int}/comments/{comment_id:int}/replies", response_model=CommentListResponse)
def list_comment_replies(
    post_id: int,
    comment_id: int,
    current_user: CurrentUser,
    db: DB,
    limit: int = Query(default=20, ge=1, le=50),
    after_id: Optional[int] = Query(default=None, ge=1),
) -> CommentListResponse:
    return Engage.list_replies(db, current_user, post_id, comment_id, limit, after_id)


@router.delete("/{post_id:int}/comments/{comment_id:int}", response_model=CommentDeleteResult)
def delete_post_comment(
    post_id: int, 
    comment_id: int, 
    current_user: CurrentUser, 
    db: DB
) -> CommentDeleteResult:
    return Engage.delete_comment(db, current_user, post_id, comment_id)


@router.post("/{post_id:int}/comments/{comment_id:int}/like", response_model=CommentLikeState)
def like_post_comment(
    post_id: int, 
    comment_id: int, 
    current_user: CurrentUser, 
    db: DB,
    action: Optional[str] = Query(None),
) -> CommentLikeState:
    if action == "unlike":
        return Engage.unlike_comment(db, current_user, post_id, comment_id)
    return Engage.like_comment(db, current_user, post_id, comment_id)


@router.delete("/{post_id:int}/comments/{comment_id:int}/like", response_model=CommentLikeState)
@router.post("/{post_id:int}/comments/{comment_id:int}/unlike", response_model=CommentLikeState)
def unlike_post_comment(
    post_id: int, 
    comment_id: int, 
    current_user: CurrentUser, 
    db: DB
) -> CommentLikeState:
    return Engage.unlike_comment(db, current_user, post_id, comment_id)


def _parse_range(range_header: Optional[str], size: int):
    """Return (start, end, partial) or None when the range cannot be satisfied."""
    start, end = 0, size - 1
    m = _RANGE_RE.match(range_header.strip()) if range_header else None
    if not m or not (m.group(1) or m.group(2)):
        return start, end, False
    if m.group(1): 
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  
        suffix = int(m.group(2))
        if suffix == 0:
            return None
        start = max(0, size - suffix)
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end, True


@router.get("/{post_id:int}/media")
def get_post_media(post_id: int, request: Request, viewer: OptionalUser, db: DB) -> Response:
    """Public for published posts (<img>/<video> tags cannot send a token).

    Media of a scheduled post is only served to a logged-in admin. Media of an archived
    post is only served to its owner.
    """
    info = PostService.media_info(db, post_id, viewer)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")
    mime, size, post_status = info

    byte_range = _parse_range(request.headers.get("range"), size)
    if byte_range is None:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start, end, partial = byte_range

    headers = {
        "Accept-Ranges": "bytes",

        "Cache-Control": "public, max-age=86400" if post_status == STATUS_PUBLISHED else "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    body = PostService.media_bytes(db, post_id, start, end - start + 1)
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(content=body, status_code=206, media_type=mime, headers=headers)
    return Response(content=body, media_type=mime, headers=headers)

