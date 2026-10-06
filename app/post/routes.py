import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.common.models.user import User
from app.common.schemas.post import FeedResponse, PollOut, VoteRequest
from app.common.services.post_service import PostService, max_bytes_for
from app.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/posts", tags=["Posts"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


@router.post("", response_model=FeedResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_type: str = Form(...),
    content: Optional[str] = Form(None),
    gif_url: Optional[str] = Form(None),
    poll_options: Optional[str] = Form(None, description="JSON list of option texts"),
    media: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    # Check permission before reading a potentially large upload.
    PostService.assert_can_create(current_user)

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
    )


@router.get("", response_model=FeedResponse)
def get_feed(
    limit: int = Query(default=10, ge=1, le=30),
    before_id: Optional[int] = Query(default=None, ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedResponse:
    return PostService.get_feed(db, current_user, limit, before_id)


@router.delete("/{post_id:int}")
def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return PostService.delete_post(db, current_user, post_id)


@router.post("/{post_id:int}/vote", response_model=PollOut)
def vote_in_poll(
    post_id: int,
    payload: VoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PollOut:
    return PostService.vote(db, current_user, post_id, payload.option_id)


@router.get("/{post_id:int}/media")
def get_post_media(post_id: int, request: Request, db: Session = Depends(get_db)) -> Response:
    """Public on purpose: <img> and <video> tags cannot send a login token."""
    info = PostService.media_info(db, post_id)
    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found.")
    mime, size = info

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }

    start, end, partial = 0, size - 1, False
    range_header = request.headers.get("range")
    if range_header:
        m = _RANGE_RE.match(range_header.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:  # "bytes=-500" means the last 500 bytes
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end or start >= size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            partial = True

    body = PostService.media_bytes(db, post_id, start, end - start + 1)
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(content=body, status_code=206, media_type=mime, headers=headers)
    return Response(content=body, media_type=mime, headers=headers)
