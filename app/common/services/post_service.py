import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.models.post import (
    STATUS_PUBLISHED,
    STATUS_SCHEDULED,
    Post,
    PostPollOption,
    PostPollVote,
    _utc_now,
)
from app.common.models.social import Profile
from app.common.models.user import User
from app.common.schemas.post import (
    FeedResponse,
    PollOptionOut,
    PollOut,
    PostAuthor,
    PostOut,
    ScheduledListResponse,
)

logger = logging.getLogger("talktamila.posts")

# ---------------------------------------------------------------------------
# WHO CAN POST
# Add "influencer" and/or "freelancer" here to let them post. Nothing else
# needs to change. Managing scheduled posts always stays admin-only.
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

# Scheduling window: at least 1 minute ahead, at most 365 days ahead.
SCHEDULE_MIN_LEAD = timedelta(minutes=1)
SCHEDULE_MAX_LEAD = timedelta(days=365)
PUBLISH_BATCH_SIZE = 100
MAX_BATCHES_PER_RUN = 10

IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
VIDEO_MIMES = {"video/mp4", "video/webm", "video/quicktime"}

MSG_POST_NOT_FOUND = "Post not found."


def max_bytes_for(post_type: str) -> int:
    return MAX_VIDEO_BYTES if post_type == "video" else MAX_IMAGE_BYTES


def sniff_mime(data: bytes) -> Optional[str]:
    """Detect the real file type from its first bytes (never trust the client's label)."""
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


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def to_utc_naive(value: datetime) -> datetime:
    """Convert a timezone-aware datetime to naive UTC. Rejects naive input."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise _bad(
            "The time must include a timezone, e.g. 2026-10-10T18:30:00+05:30 or 2026-10-10T13:00:00Z."
        )
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def validate_schedule_window(when_utc: datetime) -> datetime:
    now = _utc_now()
    if when_utc < now + SCHEDULE_MIN_LEAD:
        raise _bad("Schedule the post at least 1 minute from now.")
    if when_utc > now + SCHEDULE_MAX_LEAD:
        raise _bad("Posts can be scheduled at most 365 days ahead.")
    return when_utc


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
            raise _bad("Poll options must be a JSON list.") from None
        if not isinstance(data, list):
            raise _bad("Poll options must be a JSON list.")
        return [str(x).strip() for x in data if str(x).strip()]

    @staticmethod
    def parse_scheduled_at(raw: Optional[str]) -> Optional[datetime]:
        """Turn the form field into naive UTC and check the allowed window.

        Returns None when the field is empty, which means "publish now".
        """
        text = (raw or "").strip()
        if not text:
            return None
        if text[-1] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise _bad(
                "scheduled_at must be an ISO-8601 time, e.g. 2026-10-10T18:30:00+05:30."
            ) from None
        return validate_schedule_window(to_utc_naive(parsed))

    # ------------------------------------------------------ content validation
    @staticmethod
    def _apply_media(post: Post, post_type: str, media_bytes: Optional[bytes]) -> None:
        if not media_bytes:
            raise _bad(f"Please choose a {post_type} to post.")
        mime = sniff_mime(media_bytes)
        allowed = IMAGE_MIMES if post_type == "image" else VIDEO_MIMES
        if mime not in allowed:
            kinds = "JPG, PNG, WEBP or GIF" if post_type == "image" else "MP4, WEBM or MOV"
            raise _bad(f"That file is not a supported {post_type}. Use {kinds}.")
        limit = max_bytes_for(post_type)
        if len(media_bytes) > limit:
            raise _bad(f"That {post_type} is too large. Maximum size is {limit // (1024 * 1024)} MB.")
        post.media_type = post_type
        post.media_mime = mime
        post.media_size = len(media_bytes)
        post.media_data = media_bytes

    @staticmethod
    def _apply_gif(post: Post, gif_url: Optional[str]) -> None:
        url = (gif_url or "").strip()
        host = (urlparse(url).hostname or "").lower()
        ok_host = any(host == s or host.endswith("." + s) for s in ALLOWED_GIF_HOST_SUFFIXES)
        if not url.startswith("https://") or not ok_host or len(url) > 1000:
            raise _bad("That GIF link is not allowed.")
        post.gif_url = url

    @staticmethod
    def _apply_poll(post: Post, question: str, poll_options: List[str]) -> None:
        if not question:
            raise _bad("Write the poll question first.")
        seen = set()
        for opt in poll_options:
            if len(opt) > POLL_OPTION_MAX_LENGTH:
                raise _bad(f"Poll options can be at most {POLL_OPTION_MAX_LENGTH} characters.")
            if opt.lower() in seen:
                raise _bad("Poll options must be different from each other.")
            seen.add(opt.lower())
        if len(poll_options) < POLL_MIN_OPTIONS:
            raise _bad(f"A poll needs at least {POLL_MIN_OPTIONS} options.")
        if len(poll_options) > POLL_MAX_OPTIONS:
            raise _bad(f"A poll can have at most {POLL_MAX_OPTIONS} options.")
        post.poll_options = [PostPollOption(text=t, position=i) for i, t in enumerate(poll_options)]

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
        scheduled_at: Optional[datetime] = None,
    ) -> FeedResponse:
        """Create a post. `scheduled_at` must be naive UTC (see parse_scheduled_at)."""
        PostService.assert_can_create(user)

        post_type = (post_type or "").strip().lower()
        if post_type not in POST_TYPES:
            raise _bad("Unknown post type.")

        text = (content or "").strip()
        if len(text) > MAX_CONTENT_LENGTH:
            raise _bad(f"Posts can be at most {MAX_CONTENT_LENGTH} characters.")

        post = Post(user_id=user.user_id, post_type=post_type, content=text or None)

        if post_type == "text" and not text:
            raise _bad("Write something before posting.")
        if post_type in ("image", "video"):
            PostService._apply_media(post, post_type, media_bytes)
        elif post_type == "gif":
            PostService._apply_gif(post, gif_url)
        elif post_type == "poll":
            PostService._apply_poll(post, text, poll_options)

        if scheduled_at is not None:
            post.status = STATUS_SCHEDULED
            post.scheduled_at = validate_schedule_window(scheduled_at)
            post.published_at = None
            db.add(post)
        else:
            post.status = STATUS_PUBLISHED
            post.published_at = _utc_now()
            db.add(post)
            profile = user._ensure_profile()
            profile.posts_count = (profile.posts_count or 0) + 1

        db.commit()
        db.refresh(post)
        return PostService._build_feed(db, [post], user, has_more=False)

    # ------------------------------------------------------------------- read
    @staticmethod
    def get_feed(db: Session, viewer: User, limit: int, before_id: Optional[int]) -> FeedResponse:
        """Published posts, newest first by publish time. Scheduled posts never appear."""
        stmt = (
            select(Post)
            .join(User, User.user_id == Post.user_id)
            .where(User.is_active.is_(True), Post.status == STATUS_PUBLISHED)
            .order_by(Post.published_at.desc(), Post.post_id.desc())
            .limit(limit + 1)
        )
        if before_id:
            cursor = db.execute(
                select(Post.published_at, Post.post_id).where(
                    Post.post_id == before_id, Post.status == STATUS_PUBLISHED
                )
            ).first()
            if cursor and cursor[0] is not None:
                stmt = stmt.where(
                    or_(
                        Post.published_at < cursor[0],
                        and_(Post.published_at == cursor[0], Post.post_id < cursor[1]),
                    )
                )
            else:
                stmt = stmt.where(Post.post_id < before_id)
        rows = list(db.execute(stmt).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return PostService._build_feed(db, rows, viewer, has_more=has_more)

    @staticmethod
    def list_scheduled(
        db: Session,
        viewer: User,
        limit: int,
        offset: int,
        from_at: Optional[datetime],
        to_at: Optional[datetime],
    ) -> ScheduledListResponse:
        """Scheduled posts for admins, soonest first. `from_at`/`to_at` are naive UTC."""
        conditions = [Post.status == STATUS_SCHEDULED]
        if from_at is not None:
            conditions.append(Post.scheduled_at >= from_at)
        if to_at is not None:
            conditions.append(Post.scheduled_at <= to_at)

        total = db.execute(select(func.count(Post.post_id)).where(*conditions)).scalar() or 0
        rows = list(
            db.execute(
                select(Post)
                .where(*conditions)
                .order_by(Post.scheduled_at.asc(), Post.post_id.asc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        feed = PostService._build_feed(db, rows, viewer, has_more=False)
        return ScheduledListResponse(
            items=feed.items, authors=feed.authors, total=int(total), limit=limit, offset=offset
        )

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
    def _load_authors(db: Session, author_ids: List[int]) -> Dict[int, PostAuthor]:
        if not author_ids:
            return {}
        users = (
            db.execute(
                select(User).options(joinedload(User.profile)).where(User.user_id.in_(author_ids))
            )
            .unique()
            .scalars()
            .all()
        )
        return {
            u.user_id: PostAuthor(
                user_id=u.user_id,
                name=u.full_name or u.username,
                username=u.username,
                role=u.role,
                avatar_url=u.avatar_url,
            )
            for u in users
        }

    @staticmethod
    def _to_out(
        post: Post, viewer: User, counts: Dict[int, int], mine: Dict[int, int]
    ) -> PostOut:
        is_published = post.status == STATUS_PUBLISHED
        return PostOut(
            post_id=post.post_id,
            author_id=post.user_id,
            post_type=post.post_type,
            status=post.status,
            content=post.content,
            media_type=post.media_type,
            media_url=f"/api/v1/posts/{post.post_id}/media" if post.media_mime else None,
            gif_url=post.gif_url,
            poll=(
                PostService._poll_out(post, counts, mine.get(post.post_id))
                if post.post_type == "poll"
                else None
            ),
            created_at=_iso(post.created_at) or "",
            scheduled_at=_iso(post.scheduled_at),
            published_at=_iso(post.published_at),
            can_delete=(viewer.is_admin or (is_published and post.user_id == viewer.user_id)),
        )

    @staticmethod
    def _build_feed(db: Session, posts: List[Post], viewer: User, has_more: bool) -> FeedResponse:
        poll_ids = [p.post_id for p in posts if p.post_type == "poll"]
        counts, mine = PostService._poll_data(db, poll_ids, viewer.user_id)
        authors = PostService._load_authors(db, sorted({p.user_id for p in posts}))
        items = [PostService._to_out(p, viewer, counts, mine) for p in posts]
        return FeedResponse(
            items=items,
            authors=authors,
            has_more=has_more,
            next_before_id=(items[-1].post_id if has_more and items else None),
        )

    # ------------------------------------------------------------- scheduling
    @staticmethod
    def _adjust_posts_count(db: Session, user_id: int, delta: int) -> None:
        """Change a user's post counter in SQL so concurrent changes cannot overwrite each other."""
        if delta >= 0:
            new_value = Profile.posts_count + delta
        else:
            new_value = case((Profile.posts_count > -delta, Profile.posts_count + delta), else_=0)
        db.execute(update(Profile).where(Profile.user_id == user_id).values(posts_count=new_value))

    @staticmethod
    def _publish_post(db: Session, post_id: int, now: datetime) -> bool:
        """Move one scheduled post to published. Safe to call from several workers at once.

        The UPDATE only matches rows that are still "scheduled", so exactly one caller wins.
        """
        result = db.execute(
            update(Post)
            .where(Post.post_id == post_id, Post.status == STATUS_SCHEDULED)
            .values(status=STATUS_PUBLISHED, published_at=now)
        )
        if result.rowcount != 1:
            db.rollback()
            return False
        owner_id = db.execute(select(Post.user_id).where(Post.post_id == post_id)).scalar()
        if owner_id is not None:
            PostService._adjust_posts_count(db, owner_id, 1)
        db.commit()
        return True

    @staticmethod
    def publish_due_posts(db: Session, now: Optional[datetime] = None) -> int:
        """Publish every scheduled post whose time has come. Returns how many went live.

        Posts that fell due while the server was down are caught up on the next run.
        """
        now = now or _utc_now()
        published = 0
        for _ in range(MAX_BATCHES_PER_RUN):
            due_ids = list(
                db.execute(
                    select(Post.post_id)
                    .where(Post.status == STATUS_SCHEDULED, Post.scheduled_at <= now)
                    .order_by(Post.scheduled_at.asc(), Post.post_id.asc())
                    .limit(PUBLISH_BATCH_SIZE)
                )
                .scalars()
                .all()
            )
            for post_id in due_ids:
                try:
                    if PostService._publish_post(db, post_id, now):
                        published += 1
                except Exception:
                    db.rollback()
                    logger.exception("Could not publish scheduled post %s", post_id)
            if len(due_ids) < PUBLISH_BATCH_SIZE:
                break
        return published

    @staticmethod
    def _get_scheduled_or_error(db: Session, post_id: int) -> Post:
        post = db.get(Post, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MSG_POST_NOT_FOUND)
        if post.status != STATUS_SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This post is already published."
            )
        return post

    @staticmethod
    def reschedule(db: Session, user: User, post_id: int, new_time: datetime) -> FeedResponse:
        """Change the publish time of a scheduled post. `new_time` must be timezone-aware."""
        when = validate_schedule_window(to_utc_naive(new_time))
        PostService._get_scheduled_or_error(db, post_id)
        result = db.execute(
            update(Post)
            .where(Post.post_id == post_id, Post.status == STATUS_SCHEDULED)
            .values(scheduled_at=when)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This post is already published."
            )
        db.commit()
        return PostService._single(db, user, post_id)

    @staticmethod
    def publish_now(db: Session, user: User, post_id: int) -> FeedResponse:
        PostService._get_scheduled_or_error(db, post_id)
        if not PostService._publish_post(db, post_id, _utc_now()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="This post is already published."
            )
        return PostService._single(db, user, post_id)

    @staticmethod
    def _single(db: Session, user: User, post_id: int) -> FeedResponse:
        post = db.get(Post, post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MSG_POST_NOT_FOUND)
        db.refresh(post)
        return PostService._build_feed(db, [post], user, has_more=False)

    # ----------------------------------------------------------------- delete
    @staticmethod
    def delete_post(db: Session, user: User, post_id: int) -> dict:
        """Delete a published post, or cancel a scheduled one."""
        post = db.get(Post, post_id)
        # Scheduled posts are hidden from non-admins, so they get a plain 404.
        if not post or (post.status == STATUS_SCHEDULED and not user.is_admin):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=MSG_POST_NOT_FOUND)
        if post.user_id != user.user_id and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own posts."
            )
        was_published = post.status == STATUS_PUBLISHED
        owner_id = post.user_id
        db.delete(post)
        db.flush()
        if was_published:
            PostService._adjust_posts_count(db, owner_id, -1)
        db.commit()
        return {"success": True, "post_id": post_id}

    # ------------------------------------------------------------------- vote
    @staticmethod
    def vote(db: Session, user: User, post_id: int, option_id: int) -> PollOut:
        post = db.get(Post, post_id)
        if (
            not post
            or post.post_type != "poll"
            or post.status != STATUS_PUBLISHED
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Poll not found.")
        if option_id not in {o.option_id for o in post.poll_options}:
            raise _bad("That option does not belong to this poll.")
        already = db.execute(
            select(PostPollVote.vote_id).where(
                PostPollVote.post_id == post_id, PostPollVote.user_id == user.user_id
            )
        ).first()
        if already:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="You already voted in this poll."
            )
        db.add(PostPollVote(post_id=post_id, option_id=option_id, user_id=user.user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="You already voted in this poll."
            ) from None
        counts, mine = PostService._poll_data(db, [post_id], user.user_id)
        return PostService._poll_out(post, counts, mine.get(post_id))

    # ------------------------------------------------------------------ media
    @staticmethod
    def media_info(
        db: Session, post_id: int, viewer: Optional[User] = None
    ) -> Optional[Tuple[str, int, str]]:
        """Return (mime, size, status), or None when the viewer must not see this media."""
        row = db.execute(
            select(Post.media_mime, Post.media_size, Post.status).where(
                Post.post_id == post_id, Post.media_mime.is_not(None)
            )
        ).first()
        if not row or not row[1]:
            return None
        if row[2] != STATUS_PUBLISHED and not (viewer is not None and viewer.is_admin):
            return None
        return row[0], int(row[1]), row[2]

    @staticmethod
    def media_bytes(db: Session, post_id: int, start: int, length: int) -> bytes:
        data = db.execute(
            select(func.substr(Post.media_data, start + 1, length)).where(Post.post_id == post_id)
        ).scalar()
        return bytes(data or b"")