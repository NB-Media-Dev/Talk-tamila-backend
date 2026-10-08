import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.common.models.post import STATUS_PUBLISHED
from app.common.models.user import User
from app.common.schemas.post import (
    FeedResponse,
    PollOut,
    ScheduledListResponse,
    ScheduleRequest,
    VoteRequest,
)
from app.common.services.post_service import PostService, max_bytes_for, to_utc_naive
from app.core.dependencies import (
    get_current_admin,
    get_current_user,
    get_db,
    get_optional_current_user,
)

router = APIRouter(prefix="/posts", tags=["Posts"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


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
    media: Optional[UploadFile] = File(None),
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

    return PostService.create_post(
        db=db,
        user=current_user,
        post_type=post_type,
        content=content,
        media_bytes=media_bytes,
        gif_url=gif_url,
        poll_options=PostService.parse_poll_options(poll_options),
        scheduled_at=when,
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


@router.get("/{post_id:int}/media")
def get_post_media(
    post_id: int,
    request: Request,
    viewer: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Public for published posts (<img>/<video> tags cannot send a token).

    Media of a scheduled post is only served to a logged-in admin.
    """
    info = PostService.media_info(db, post_id, viewer)
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

    body = PostService.media_bytes(db, post_id, start, end - start + 1)
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(content=body, status_code=206, media_type=mime, headers=headers)
    return Response(content=body, media_type=mime, headers=headers)