import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.models.post import Post, PostPollOption, PostPollVote
from app.common.models.user import User
from app.common.schemas.post import (
    FeedResponse,
    PollOptionOut,
    PollOut,
    PostAuthor,
    PostOut,
)

# ---------------------------------------------------------------------------
# WHO CAN POST
# this to {"admin", "influencer", "freelancer"}. Nothing else needs to change
# ---------------------------------------------------------------------------
POST_CREATOR_ROLES = {"admin"}

POST_TYPES = {"text", "image", "video", "gif", "poll"}

MAX_CONTENT_LENGTH = 5000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
POLL_MIN_OPTIONS = 2
POLL_MAX_OPTIONS = 5
POLL_OPTION_MAX_LENGTH = 80

ALLOWED_GIF_HOST_SUFFIXES = ("giphy.com", "tenor.com")


def max_bytes_for(post_type: str) -> int:
    return MAX_VIDEO_BYTES if post_type == "video" else MAX_IMAGE_BYTES


def sniff_mime(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        return "video/quicktime" if data[8:12] == b"qt  " else "video/mp4"
    if data[:4] == b"\x1aE\xdf\xa3":
        return "video/webm"
    return None


IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime"}


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class PostService:
    # ------------------------------------------------------------------ rules
    @staticmethod
    def can_create(user: User) -> bool:
        return user.role in POST_CREATOR_ROLES

    @staticmethod
    def assert_can_create(user: User) -> None:
        if not PostService.can_create(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Posting is limited to admins right now.",
            )

    @staticmethod
    def parse_poll_options(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            raise _bad("Poll options must be a JSON list.")
        if not isinstance(data, list):
            raise _bad("Poll options must be a JSON list.")
        return [str(x).strip() for x in data if str(x).strip()]

    # ----------------------------------------------------------------- create
    @staticmethod
    def create_post(
        db: Session,
        user: User,
        post_type: str,
        content: Optional[str],
        media_bytes: Optional[bytes],
        gif_url: Optional[str],
        poll_options: List[str],
    ) -> FeedResponse:
        PostService.assert_can_create(user)

        post_type = (post_type or "").strip().lower()
        if post_type not in POST_TYPES:
            raise _bad("Unknown post type.")

        text = (content or "").strip()
        if len(text) > MAX_CONTENT_LENGTH:
            raise _bad(f"Posts can be at most {MAX_CONTENT_LENGTH} characters.")

        post = Post(user_id=user.user_id, post_type=post_type, content=text or None)

        if post_type == "text":
            if not text:
                raise _bad("Write something before posting.")

        elif post_type in ("image", "video"):
            if not media_bytes:
                raise _bad(f"Please choose a {post_type} to post.")
            mime = sniff_mime(media_bytes)
            allowed = IMAGE_MIMES if post_type == "image" else VIDEO_MIMES
            if mime not in allowed:
                kinds = "JPG, PNG, WEBP or GIF" if post_type == "image" else "MP4, WEBM or MOV"
                raise _bad(f"That file is not a supported {post_type}. Use {kinds}.")
            if len(media_bytes) > max_bytes_for(post_type):
                mb = max_bytes_for(post_type) // (1024 * 1024)
                raise _bad(f"That {post_type} is too large. Maximum size is {mb} MB.")
            post.media_type = post_type
            post.media_mime = mime
            post.media_size = len(media_bytes)
            post.media_data = media_bytes

        elif post_type == "gif":
            url = (gif_url or "").strip()
            host = (urlparse(url).hostname or "").lower()
            ok_host = any(host == s or host.endswith("." + s) for s in ALLOWED_GIF_HOST_SUFFIXES)
            if not url.startswith("https://") or not ok_host or len(url) > 1000:
                raise _bad("That GIF link is not allowed.")
            post.gif_url = url

        elif post_type == "poll":
            if not text:
                raise _bad("Write the poll question first.")
            seen = set()
            clean: List[str] = []
            for opt in poll_options:
                if len(opt) > POLL_OPTION_MAX_LENGTH:
                    raise _bad(f"Poll options can be at most {POLL_OPTION_MAX_LENGTH} characters.")
                key = opt.lower()
                if key in seen:
                    raise _bad("Poll options must be different from each other.")
                seen.add(key)
                clean.append(opt)
            if len(clean) < POLL_MIN_OPTIONS:
                raise _bad(f"A poll needs at least {POLL_MIN_OPTIONS} options.")
            if len(clean) > POLL_MAX_OPTIONS:
                raise _bad(f"A poll can have at most {POLL_MAX_OPTIONS} options.")
            post.poll_options = [PostPollOption(text=t, position=i) for i, t in enumerate(clean)]

        db.add(post)
        profile = user._ensure_profile()
        profile.posts_count = (profile.posts_count or 0) + 1
        db.commit()
        db.refresh(post)
        return PostService._build_feed(db, [post], user, has_more=False)

    # ------------------------------------------------------------------- read
    @staticmethod
    def get_feed(db: Session, viewer: User, limit: int, before_id: Optional[int]) -> FeedResponse:
        stmt = (
            select(Post)
            .join(User, User.user_id == Post.user_id)
            .where(User.is_active.is_(True))
            .order_by(Post.post_id.desc())
            .limit(limit + 1)
        )
        if before_id:
            stmt = stmt.where(Post.post_id < before_id)
        rows = list(db.execute(stmt).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return PostService._build_feed(db, rows, viewer, has_more=has_more)

    @staticmethod
    def _poll_data(
        db: Session, post_ids: List[int], viewer_id: int
    ) -> Tuple[Dict[int, int], Dict[int, int]]:
        if not post_ids:
            return {}, {}
        counts = dict(
            db.execute(
                select(PostPollVote.option_id, func.count(PostPollVote.vote_id))
                .where(PostPollVote.post_id.in_(post_ids))
                .group_by(PostPollVote.option_id)
            ).all()
        )
        mine = dict(
            db.execute(
                select(PostPollVote.post_id, PostPollVote.option_id).where(
                    PostPollVote.post_id.in_(post_ids), PostPollVote.user_id == viewer_id
                )
            ).all()
        )
        return counts, mine

    @staticmethod
    def _poll_out(post: Post, counts: Dict[int, int], my_option: Optional[int]) -> PollOut:
        options = [
            PollOptionOut(option_id=o.option_id, text=o.text, votes=int(counts.get(o.option_id, 0)))
            for o in post.poll_options
        ]
        return PollOut(
            options=options,
            total_votes=sum(o.votes for o in options),
            my_vote_option_id=my_option,
        )

    @staticmethod
    def _build_feed(db: Session, posts: List[Post], viewer: User, has_more: bool) -> FeedResponse:
        poll_ids = [p.post_id for p in posts if p.post_type == "poll"]
        counts, mine = PostService._poll_data(db, poll_ids, viewer.user_id)

        author_ids = sorted({p.user_id for p in posts})
        authors: Dict[int, PostAuthor] = {}
        if author_ids:
            users = (
                db.execute(
                    select(User)
                    .options(joinedload(User.profile))
                    .where(User.user_id.in_(author_ids))
                )
                .unique()
                .scalars()
                .all()
            )
            for u in users:
                authors[u.user_id] = PostAuthor(
                    user_id=u.user_id,
                    name=u.full_name or u.username,
                    username=u.username,
                    role=u.role,
                    avatar_url=u.avatar_url,
                )

        items: List[PostOut] = []
        for p in posts:
            items.append(
                PostOut(
                    post_id=p.post_id,
                    author_id=p.user_id,
                    post_type=p.post_type,
                    content=p.content,
                    media_type=p.media_type,
                    media_url=(
                        f"/api/v1/posts/{p.post_id}/media" if p.media_mime else None
                    ),
                    gif_url=p.gif_url,
                    poll=(
                        PostService._poll_out(p, counts, mine.get(p.post_id))
                        if p.post_type == "poll"
                        else None
                    ),
                    created_at=_iso(p.created_at),
                    can_delete=(p.user_id == viewer.user_id or viewer.is_admin),
                )
            )
        return FeedResponse(
            items=items,
            authors=authors,
            has_more=has_more,
            next_before_id=(items[-1].post_id if has_more and items else None),
        )

    # ----------------------------------------------------------------- delete
    @staticmethod
    def delete_post(db: Session, user: User, post_id: int) -> dict:
        post = db.get(Post, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found.")
        if post.user_id != user.user_id and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own posts."
            )
        owner = db.get(User, post.user_id)
        db.delete(post)
        if owner is not None and owner.profile is not None:
            owner.profile.posts_count = max(0, (owner.profile.posts_count or 0) - 1)
        db.commit()
        return {"success": True, "post_id": post_id}

    # ------------------------------------------------------------------- vote
    @staticmethod
    def vote(db: Session, user: User, post_id: int, option_id: int) -> PollOut:
        post = db.get(Post, post_id)
        if not post or post.post_type != "poll":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
        if option_id not in {o.option_id for o in post.poll_options}:
            raise _bad("That option does not belong to this poll.")
        already = db.execute(
            select(PostPollVote.vote_id).where(
                PostPollVote.post_id == post_id, PostPollVote.user_id == user.user_id
            )
        ).first()
        if already:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already voted in this poll.")
        db.add(PostPollVote(post_id=post_id, option_id=option_id, user_id=user.user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You already voted in this poll.")
        counts, mine = PostService._poll_data(db, [post_id], user.user_id)
        return PostService._poll_out(post, counts, mine.get(post_id))

    # ------------------------------------------------------------------ media
    @staticmethod
    def media_info(db: Session, post_id: int) -> Optional[Tuple[str, int]]:
        row = db.execute(
            select(Post.media_mime, Post.media_size).where(
                Post.post_id == post_id, Post.media_mime.is_not(None)
            )
        ).first()
        if not row or not row[1]:
            return None
        return row[0], int(row[1])

    @staticmethod
    def media_bytes(db: Session, post_id: int, start: int, length: int) -> bytes:
        data = db.execute(
            select(func.substr(Post.media_data, start + 1, length)).where(Post.post_id == post_id)
        ).scalar()
        return bytes(data or b"")

