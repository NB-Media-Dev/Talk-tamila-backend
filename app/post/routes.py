import re
from datetime import datetime
from typing import List, Optional

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
from app.common.services.post_engagement_service import PostEngagementService
from app.common.services.post_service import (
    MAX_CAROUSEL_ITEMS,
    PostService,
    max_bytes_for,
    to_utc_naive,
)
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    get_db,
    get_optional_current_user,
)

router = APIRouter(prefix="/posts", tags=["Posts"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


# ---------------------------------------------------------------- create / read
@router.post("", response_model=FeedResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
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
    more_media: Optional[List[UploadFile]] = File(
        None, description="Pictures 2, 3, ... of a carousel post (up to 9 more)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    # Cheap checks first, before reading a potentially large upload.
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

    extra_media: List[bytes] = []
    extra_files = [f for f in (more_media or []) if f is not None and f.filename]
    if extra_files:
        if post_type.strip().lower() != "image" or media_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only photo posts can have more than one picture.",
            )
        if 1 + len(extra_files) > MAX_CAROUSEL_ITEMS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A carousel can have at most {MAX_CAROUSEL_ITEMS} pictures.",
            )
        image_limit = max_bytes_for("image")
        for extra in extra_files:
            data = await extra.read(image_limit + 1)
            if len(data) > image_limit:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"That file is too large. Maximum size is {image_limit // (1024 * 1024)} MB each.",
                )
            extra_media.append(data)

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
        extra_media=extra_media,
    )


@router.get("", response_model=FeedResponse)
def get_feed(
    limit: int = Query(default=10, ge=1, le=30),
    before_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.get_feed(db, current_user, limit, before_id)


@router.get("/scheduled", response_model=ScheduledListResponse)
def list_scheduled_posts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    from_at: Optional[datetime] = Query(default=None, description="Only posts due at or after this time (with timezone)"),
    to_at: Optional[datetime] = Query(default=None, description="Only posts due at or before this time (with timezone)"),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ScheduledListResponse:
    start = to_utc_naive(from_at) if from_at else None
    end = to_utc_naive(to_at) if to_at else None
    if start and end and start > end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="from_at must be before to_at.")
    return PostService.list_scheduled(db, admin, limit, offset, start, end)


@router.get("/saved", response_model=FeedResponse)
def list_saved_posts(
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Posts I saved, most recently saved first."""
    return PostService.get_saved(db, current_user, limit, offset)


@router.get("/archived", response_model=FeedResponse)
def list_archived_posts(
    limit: int = Query(default=30, ge=1, le=60),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """My own archived posts."""
    return PostService.get_archived(db, current_user, limit, offset)


@router.get("/{post_id:int}", response_model=FeedResponse)
def get_one_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """One post (items[0]). Used by shared links and notifications."""
    return PostService.get_one(db, current_user, post_id)


# ----------------------------------------------------------- scheduling / edit
@router.patch("/{post_id:int}/schedule", response_model=FeedResponse)
def reschedule_post(
    post_id: int,
    payload: ScheduleRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.reschedule(db, admin, post_id, payload.scheduled_at)


@router.post("/{post_id:int}/publish", response_model=FeedResponse)
def publish_post_now(
    post_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.publish_now(db, admin, post_id)


@router.patch("/{post_id:int}", response_model=FeedResponse)
def edit_post(
    post_id: int,
    payload: PostEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    """Owner only: caption, song, comments on/off, hide like count."""
    return PostService.edit_post(db, current_user, post_id, payload)


@router.post("/{post_id:int}/archive", response_model=FeedResponse)
def archive_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.set_archived(db, current_user, post_id, True)


@router.post("/{post_id:int}/restore", response_model=FeedResponse)
def restore_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.set_archived(db, current_user, post_id, False)


@router.post("/{post_id:int}/pin", response_model=FeedResponse)
def pin_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.set_pinned(db, current_user, post_id, True)


@router.delete("/{post_id:int}/pin", response_model=FeedResponse)
def unpin_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.set_pinned(db, current_user, post_id, False)


@router.delete("/{post_id:int}")
def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Delete a post. For a scheduled post this cancels it."""
    return PostService.delete_post(db, current_user, post_id)


@router.post("/{post_id:int}/vote", response_model=PollOut)
def vote_in_poll(
    post_id: int,
    payload: VoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PollOut:
    return PostService.vote(db, current_user, post_id, payload.option_id)


# ------------------------------------------------------------------- likes
@router.post("/{post_id:int}/like", response_model=LikeState)
def like_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LikeState:
    return PostEngagementService.like(db, current_user, post_id)


@router.delete("/{post_id:int}/like", response_model=LikeState)
def unlike_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LikeState:
    return PostEngagementService.unlike(db, current_user, post_id)


@router.get("/{post_id:int}/likes", response_model=LikersResponse)
def list_post_likers(
    post_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LikersResponse:
    return PostEngagementService.list_likers(db, current_user, post_id, limit, offset)


# ------------------------------------------------------------ save / share
@router.post("/{post_id:int}/save", response_model=SaveState)
def save_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaveState:
    return PostEngagementService.save(db, current_user, post_id)


@router.delete("/{post_id:int}/save", response_model=SaveState)
def unsave_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaveState:
    return PostEngagementService.unsave(db, current_user, post_id)


@router.post("/{post_id:int}/share", response_model=ShareState)
def share_post(
    post_id: int,
    payload: ShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareState:
    """Count a share (link copied, or sent to people in messages)."""
    return PostEngagementService.share(
        db, current_user, post_id, payload.channel, payload.recipients
    )


@router.post("/{post_id:int}/view")
def view_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Count one view per person. Powers the reach number in insights."""
    return PostEngagementService.record_view(db, current_user, post_id)


@router.post("/{post_id:int}/report")
def report_post(
    post_id: int,
    payload: ReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return PostEngagementService.report(db, current_user, post_id, payload.reason)


@router.get("/{post_id:int}/insights", response_model=InsightsOut)
def post_insights(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightsOut:
    """Owner (or admin) only: how the post is performing."""
    return PostEngagementService.insights(db, current_user, post_id)


# ---------------------------------------------------------------- comments
@router.get("/{post_id:int}/comments", response_model=CommentListResponse)
def list_post_comments(
    post_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    before_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    return PostEngagementService.list_comments(db, current_user, post_id, limit, before_id)


@router.post(
    "/{post_id:int}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED
)
def add_post_comment(
    post_id: int,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    return PostEngagementService.add_comment(
        db, current_user, post_id, payload.body, payload.parent_id
    )


@router.get("/{post_id:int}/comments/{comment_id:int}/replies", response_model=CommentListResponse)
def list_comment_replies(
    post_id: int,
    comment_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    after_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentListResponse:
    return PostEngagementService.list_replies(
        db, current_user, post_id, comment_id, limit, after_id
    )


@router.delete("/{post_id:int}/comments/{comment_id:int}", response_model=CommentDeleteResult)
def delete_post_comment(
    post_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentDeleteResult:
    return PostEngagementService.delete_comment(db, current_user, post_id, comment_id)


@router.post("/{post_id:int}/comments/{comment_id:int}/like", response_model=CommentLikeState)
def like_post_comment(
    post_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentLikeState:
    return PostEngagementService.like_comment(db, current_user, post_id, comment_id)


@router.delete("/{post_id:int}/comments/{comment_id:int}/like", response_model=CommentLikeState)
def unlike_post_comment(
    post_id: int,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentLikeState:
    return PostEngagementService.unlike_comment(db, current_user, post_id, comment_id)


# ------------------------------------------------------------------- media
def _parse_range(range_header: Optional[str], size: int):
    """Return (start, end, partial) or None when the range cannot be satisfied."""
    start, end = 0, size - 1
    if not range_header:
        return start, end, False
    m = _RANGE_RE.match(range_header.strip())
    if not m or not (m.group(1) or m.group(2)):
        return start, end, False
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  # "bytes=-500" means the last 500 bytes
        start = max(0, size - int(m.group(2)))
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end, True


def _serve_media(
    post_id: int,
    position: int,
    request: Request,
    viewer: Optional[User],
    db: Session,
) -> Response:
    info = PostService.media_info(db, post_id, viewer, position)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")
    mime, size, post_status = info

    cache = (
        "public, max-age=31536000, immutable" if post_status == STATUS_PUBLISHED else "private, no-store"
    )
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": cache,
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }

    byte_range = _parse_range(request.headers.get("range"), size)
    if byte_range is None:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    start, end, partial = byte_range

    body = PostService.media_bytes(db, post_id, start, end - start + 1, position)
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(content=body, status_code=206, media_type=mime, headers=headers)
    return Response(content=body, media_type=mime, headers=headers)


@router.get("/{post_id:int}/media")
def get_post_media(
    post_id: int,
    request: Request,
    viewer: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Public for published posts (<img>/<video> tags cannot send a token).

    Media of a scheduled post is only served to a logged-in admin. Media of an archived
    post is only served to its owner.
    """
    return _serve_media(post_id, 0, request, viewer, db)


@router.get("/{post_id:int}/media/{position:int}")
def get_post_media_slide(
    post_id: int,
    position: int,
    request: Request,
    viewer: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Slide `position` (1, 2, 3 ...) of a carousel post. Same visibility rules as /media."""
    return _serve_media(post_id, position, request, viewer, db)