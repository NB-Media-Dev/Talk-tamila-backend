"""Likes, comments, saves, shares, views, reports and insights for posts.

Kept apart from PostService so the two files stay readable. This file never imports
PostService, so PostService can import it without a loop.
"""
import logging
from datetime import timedelta
from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.models.moderation import UserBlock
from app.common.models.post import (
    STATUS_PUBLISHED,
    Post,
    PostComment,
    PostCommentLike,
    PostLike,
    PostPollVote,
    PostReport,
    PostSave,
    PostShare,
    PostView,
    _utc_now,
)
from app.common.models.social import Follow, Notification
from app.common.models.user import User
from app.common.schemas.post import (
    CommentDeleteResult,
    CommentLikeState,
    CommentListResponse,
    CommentOut,
    InsightsDay,
    InsightsOut,
    LikeState,
    LikerPreview,
    LikersResponse,
    PostAuthor,
    PostUserOut,
    SaveState,
    ShareState,
)

logger = logging.getLogger("talktamila.post_engagement")

MAX_COMMENT_LENGTH = 1000
COMMENT_FLOOD_LIMIT = 20  # comments per person per minute
MAX_SHARE_RECIPIENTS = 50
REPORT_REASONS = {
    "spam",
    "scam",
    "nudity",
    "hate",
    "violence",
    "self_harm",
    "false_info",
    "bullying",
    "other",
}

MSG_POST_NOT_FOUND = "Post not found."


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _not_found(detail: str = MSG_POST_NOT_FOUND) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


class PostEngagementService:
    # ------------------------------------------------------------ blocking
    @staticmethod
    def blocked_between(db: Session, a_id: int, b_id: int) -> bool:
        if a_id == b_id:
            return False
        row = db.execute(
            select(UserBlock.id).where(
                or_(
                    and_(UserBlock.blocker_id == a_id, UserBlock.blocked_id == b_id),
                    and_(UserBlock.blocker_id == b_id, UserBlock.blocked_id == a_id),
                )
            )
        ).first()
        return row is not None

    @staticmethod
    def blocked_ids(db: Session, me_id: int) -> Set[int]:
        """Everyone who blocked me or whom I blocked."""
        rows = db.execute(
            select(UserBlock.blocker_id, UserBlock.blocked_id).where(
                or_(UserBlock.blocker_id == me_id, UserBlock.blocked_id == me_id)
            )
        ).all()
        out: Set[int] = set()
        for blocker, blocked in rows:
            out.add(blocked if blocker == me_id else blocker)
        return out

    @staticmethod
    def get_interactable_post(db: Session, user: User, post_id: int) -> Post:
        """A published post the viewer is allowed to react to. Anything else is a 404."""
        post = db.get(Post, post_id)
        if post is None or post.status != STATUS_PUBLISHED:
            raise _not_found()
        owner = db.get(User, post.user_id)
        if owner is None or not owner.is_active:
            raise _not_found()
        if PostEngagementService.blocked_between(db, user.user_id, post.user_id):
            raise _not_found()
        return post

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _notify(
        db: Session, recipient_id: int, actor: User, kind: str, text: str, reference_id: int
    ) -> None:
        """Best effort. A notification must never make the real action fail."""
        if recipient_id == actor.user_id:
            return
        try:
            exists = db.execute(
                select(Notification.id).where(
                    Notification.user_id == recipient_id,
                    Notification.type == kind,
                    Notification.reference_id == reference_id,
                    Notification.message == text[:255],
                )
            ).first()
            if exists:
                return
            db.add(
                Notification(
                    user_id=recipient_id,
                    type=kind,
                    message=text[:255],
                    reference_id=reference_id,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not create %s notification", kind)

    @staticmethod
    def _drop_notification(
        db: Session, recipient_id: int, kind: str, text: str, reference_id: int
    ) -> None:
        try:
            db.execute(
                delete(Notification).where(
                    Notification.user_id == recipient_id,
                    Notification.type == kind,
                    Notification.reference_id == reference_id,
                    Notification.message == text[:255],
                )
            )
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def _load_users(db: Session, ids: List[int]) -> Dict[int, User]:
        if not ids:
            return {}
        users = (
            db.execute(select(User).options(joinedload(User.profile)).where(User.user_id.in_(ids)))
            .unique()
            .scalars()
            .all()
        )
        return {u.user_id: u for u in users}

    @staticmethod
    def _author(u: User) -> PostAuthor:
        return PostAuthor(
            user_id=u.user_id,
            name=u.full_name or u.username,
            username=u.username,
            role=u.role,
            avatar_url=u.avatar_url,
        )

    # ------------------------------------------------- numbers for the feed
    @staticmethod
    def snapshot(db: Session, post_ids: List[int], viewer_id: int, author_ids: List[int]) -> dict:
        """Everything PostService needs to fill in the engagement fields for a page of posts."""
        empty = {
            "likes": {},
            "comments": {},
            "shares": {},
            "liked": set(),
            "saved": set(),
            "preview": {},
            "following": set(),
        }
        if not post_ids:
            return empty

        likes = dict(
            db.execute(
                select(PostLike.post_id, func.count(PostLike.like_id))
                .where(PostLike.post_id.in_(post_ids))
                .group_by(PostLike.post_id)
            ).all()
        )
        comments = dict(
            db.execute(
                select(PostComment.post_id, func.count(PostComment.comment_id))
                .where(PostComment.post_id.in_(post_ids))
                .group_by(PostComment.post_id)
            ).all()
        )
        shares = dict(
            db.execute(
                select(PostShare.post_id, func.count(PostShare.share_id))
                .where(PostShare.post_id.in_(post_ids))
                .group_by(PostShare.post_id)
            ).all()
        )
        liked = set(
            db.execute(
                select(PostLike.post_id).where(
                    PostLike.post_id.in_(post_ids), PostLike.user_id == viewer_id
                )
            )
            .scalars()
            .all()
        )
        saved = set(
            db.execute(
                select(PostSave.post_id).where(
                    PostSave.post_id.in_(post_ids), PostSave.user_id == viewer_id
                )
            )
            .scalars()
            .all()
        )

        preview: Dict[int, LikerPreview] = {}
        rows = db.execute(
            select(PostLike.post_id, User.user_id, User.username)
            .join(
                Follow,
                and_(Follow.following_id == PostLike.user_id, Follow.follower_id == viewer_id),
            )
            .join(User, User.user_id == PostLike.user_id)
            .where(
                PostLike.post_id.in_(post_ids),
                User.is_active.is_(True),
                PostLike.user_id != viewer_id,
            )
            .order_by(PostLike.like_id.desc())
        ).all()
        for pid, uid, uname in rows:
            if pid not in preview:
                preview[pid] = LikerPreview(user_id=uid, username=uname)

        following: Set[int] = set()
        if author_ids:
            following = set(
                db.execute(
                    select(Follow.following_id).where(
                        Follow.follower_id == viewer_id, Follow.following_id.in_(author_ids)
                    )
                )
                .scalars()
                .all()
            )
        return {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "liked": liked,
            "saved": saved,
            "preview": preview,
            "following": following,
        }

    # --------------------------------------------------------------- likes
    @staticmethod
    def _like_state(db: Session, post: Post, viewer: User, liked: bool) -> LikeState:
        count = db.execute(
            select(func.count(PostLike.like_id)).where(PostLike.post_id == post.post_id)
        ).scalar() or 0
        hidden = post.hide_like_count and post.user_id != viewer.user_id
        return LikeState(liked=liked, like_count=None if hidden else int(count))

    @staticmethod
    def like(db: Session, user: User, post_id: int) -> LikeState:
        post = PostEngagementService.get_interactable_post(db, user, post_id)
        db.add(PostLike(post_id=post_id, user_id=user.user_id))
        created = True
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            created = False  # already liked: liking twice is fine, nothing changes
        if created:
            PostEngagementService._notify(
                db, post.user_id, user, "post_like", f"{user.username} liked your post", post_id
            )
        return PostEngagementService._like_state(db, post, user, True)

    @staticmethod
    def unlike(db: Session, user: User, post_id: int) -> LikeState:
        post = PostEngagementService.get_interactable_post(db, user, post_id)
        db.execute(
            delete(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.user_id)
        )
        db.commit()
        PostEngagementService._drop_notification(
            db, post.user_id, "post_like", f"{user.username} liked your post", post_id
        )
        return PostEngagementService._like_state(db, post, user, False)

    @staticmethod
    def list_likers(
        db: Session, viewer: User, post_id: int, limit: int = 50, offset: int = 0
    ) -> LikersResponse:
        post = db.get(Post, post_id)
        if post is None:
            raise _not_found()
        is_owner = post.user_id == viewer.user_id
        if post.status != STATUS_PUBLISHED and not (is_owner or viewer.is_admin):
            raise _not_found()
        if PostEngagementService.blocked_between(db, viewer.user_id, post.user_id):
            raise _not_found()
        if post.hide_like_count and not (is_owner or viewer.is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The owner hid the likes on this post.",
            )
        limit = max(1, min(int(limit or 50), 100))
        offset = max(0, int(offset or 0))
        total = db.execute(
            select(func.count(PostLike.like_id)).where(PostLike.post_id == post_id)
        ).scalar() or 0
        ids = list(
            db.execute(
                select(PostLike.user_id)
                .where(PostLike.post_id == post_id)
                .order_by(PostLike.like_id.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        users = PostEngagementService._load_users(db, ids)
        items = [
            PostUserOut(
                user_id=u.user_id,
                username=u.username,
                name=u.full_name or u.username,
                avatar_url=u.avatar_url,
                role=u.role,
            )
            for uid in ids
            if (u := users.get(uid)) is not None and u.is_active
        ]
        return LikersResponse(items=items, total=int(total))

    # --------------------------------------------------------------- saves
    @staticmethod
    def save(db: Session, user: User, post_id: int) -> SaveState:
        PostEngagementService.get_interactable_post(db, user, post_id)
        db.add(PostSave(post_id=post_id, user_id=user.user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return SaveState(saved=True)

    @staticmethod
    def unsave(db: Session, user: User, post_id: int) -> SaveState:
        # No visibility check: people must always be able to drop something they saved.
        db.execute(
            delete(PostSave).where(PostSave.post_id == post_id, PostSave.user_id == user.user_id)
        )
        db.commit()
        return SaveState(saved=False)

    # -------------------------------------------------------------- shares
    @staticmethod
    def share(db: Session, user: User, post_id: int, channel: str, recipients: int) -> ShareState:
        PostEngagementService.get_interactable_post(db, user, post_id)
        count = 1
        if channel == "dm":
            count = max(1, min(int(recipients or 1), MAX_SHARE_RECIPIENTS))
        for _ in range(count):
            db.add(PostShare(post_id=post_id, user_id=user.user_id, channel=channel))
        db.commit()
        total = db.execute(
            select(func.count(PostShare.share_id)).where(PostShare.post_id == post_id)
        ).scalar() or 0
        return ShareState(share_count=int(total))

    # --------------------------------------------------------------- views
    @staticmethod
    def record_view(db: Session, user: User, post_id: int) -> dict:
        post = db.get(Post, post_id)
        if post is None or post.status != STATUS_PUBLISHED or post.user_id == user.user_id:
            return {"success": True}
        db.add(PostView(post_id=post_id, user_id=user.user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return {"success": True}

    # ------------------------------------------------------------- reports
    @staticmethod
    def report(db: Session, user: User, post_id: int, reason: str) -> dict:
        reason = (reason or "").strip().lower()
        if reason not in REPORT_REASONS:
            raise _bad("Choose a reason for the report.")
        post = PostEngagementService.get_interactable_post(db, user, post_id)
        if post.user_id == user.user_id:
            raise _bad("You can't report your own post.")
        db.add(PostReport(post_id=post_id, reporter_id=user.user_id, reason=reason))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # already reported: treat as done
        return {"success": True}

    # ------------------------------------------------------------ comments
    @staticmethod
    def _comment_outs(
        db: Session, comments: List[PostComment], viewer: User, post: Post
    ) -> List[CommentOut]:
        if not comments:
            return []
        ids = [c.comment_id for c in comments]
        users = PostEngagementService._load_users(db, sorted({c.user_id for c in comments}))
        like_counts = dict(
            db.execute(
                select(PostCommentLike.comment_id, func.count(PostCommentLike.id))
                .where(PostCommentLike.comment_id.in_(ids))
                .group_by(PostCommentLike.comment_id)
            ).all()
        )
        mine = set(
            db.execute(
                select(PostCommentLike.comment_id).where(
                    PostCommentLike.comment_id.in_(ids), PostCommentLike.user_id == viewer.user_id
                )
            )
            .scalars()
            .all()
        )
        reply_counts = dict(
            db.execute(
                select(PostComment.parent_id, func.count(PostComment.comment_id))
                .where(PostComment.parent_id.in_(ids))
                .group_by(PostComment.parent_id)
            ).all()
        )
        out: List[CommentOut] = []
        for c in comments:
            u = users.get(c.user_id)
            if u is None:
                continue
            out.append(
                CommentOut(
                    comment_id=c.comment_id,
                    post_id=c.post_id,
                    parent_id=c.parent_id,
                    body=c.body,
                    created_at=_iso(c.created_at) or "",
                    author=PostEngagementService._author(u),
                    like_count=int(like_counts.get(c.comment_id, 0)),
                    liked_by_me=c.comment_id in mine,
                    reply_count=int(reply_counts.get(c.comment_id, 0)),
                    can_delete=(
                        viewer.is_admin
                        or c.user_id == viewer.user_id
                        or post.user_id == viewer.user_id
                    ),
                    by_post_owner=(c.user_id == post.user_id),
                )
            )
        return out

    @staticmethod
    def _comment_total(db: Session, post_id: int) -> int:
        return int(
            db.execute(
                select(func.count(PostComment.comment_id)).where(PostComment.post_id == post_id)
            ).scalar()
            or 0
        )

    @staticmethod
    def list_comments(
        db: Session, viewer: User, post_id: int, limit: int = 20, before_id: Optional[int] = None
    ) -> CommentListResponse:
        post = PostEngagementService.get_interactable_post(db, viewer, post_id)
        if post.comments_disabled:
            return CommentListResponse(items=[], total=0, comments_disabled=True)
        limit = max(1, min(int(limit or 20), 50))
        blocked = PostEngagementService.blocked_ids(db, viewer.user_id)
        stmt = (
            select(PostComment)
            .where(PostComment.post_id == post_id, PostComment.parent_id.is_(None))
            .order_by(PostComment.comment_id.desc())
            .limit(limit + 1)
        )
        if blocked:
            stmt = stmt.where(PostComment.user_id.not_in(blocked))
        if before_id:
            stmt = stmt.where(PostComment.comment_id < before_id)
        rows = list(db.execute(stmt).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = PostEngagementService._comment_outs(db, rows, viewer, post)
        return CommentListResponse(
            items=items,
            total=PostEngagementService._comment_total(db, post_id),
            has_more=has_more,
            next_cursor=(rows[-1].comment_id if has_more and rows else None),
        )

    @staticmethod
    def list_replies(
        db: Session,
        viewer: User,
        post_id: int,
        comment_id: int,
        limit: int = 20,
        after_id: Optional[int] = None,
    ) -> CommentListResponse:
        post = PostEngagementService.get_interactable_post(db, viewer, post_id)
        if post.comments_disabled:
            return CommentListResponse(items=[], total=0, comments_disabled=True)
        parent = db.get(PostComment, comment_id)
        if parent is None or parent.post_id != post_id:
            raise _not_found("Comment not found.")
        limit = max(1, min(int(limit or 20), 50))
        blocked = PostEngagementService.blocked_ids(db, viewer.user_id)
        stmt = (
            select(PostComment)
            .where(PostComment.parent_id == comment_id)
            .order_by(PostComment.comment_id.asc())
            .limit(limit + 1)
        )
        if blocked:
            stmt = stmt.where(PostComment.user_id.not_in(blocked))
        if after_id:
            stmt = stmt.where(PostComment.comment_id > after_id)
        rows = list(db.execute(stmt).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = PostEngagementService._comment_outs(db, rows, viewer, post)
        return CommentListResponse(
            items=items,
            total=PostEngagementService._comment_total(db, post_id),
            has_more=has_more,
            next_cursor=(rows[-1].comment_id if has_more and rows else None),
        )

    @staticmethod
    def add_comment(
        db: Session, user: User, post_id: int, body: str, parent_id: Optional[int]
    ) -> CommentOut:
        post = PostEngagementService.get_interactable_post(db, user, post_id)
        if post.comments_disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Comments are turned off for this post.",
            )
        text = (body or "").strip()
        if not text:
            raise _bad("Write a comment first.")
        if len(text) > MAX_COMMENT_LENGTH:
            raise _bad(f"Comments can be at most {MAX_COMMENT_LENGTH} characters.")

        recent = db.execute(
            select(func.count(PostComment.comment_id)).where(
                PostComment.user_id == user.user_id,
                PostComment.created_at >= _utc_now() - timedelta(minutes=1),
            )
        ).scalar() or 0
        if recent >= COMMENT_FLOOD_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You're commenting too fast. Wait a moment and try again.",
            )

        parent: Optional[PostComment] = None
        if parent_id:
            parent = db.get(PostComment, parent_id)
            if parent is None or parent.post_id != post_id:
                raise _not_found("The comment you are replying to is gone.")
            if PostEngagementService.blocked_between(db, user.user_id, parent.user_id):
                raise _not_found("The comment you are replying to is gone.")
            # Replies are one level deep: a reply to a reply joins the same thread.
            root_id = parent.parent_id or parent.comment_id
        else:
            root_id = None

        comment = PostComment(post_id=post_id, user_id=user.user_id, parent_id=root_id, body=text)
        db.add(comment)
        db.commit()
        db.refresh(comment)

        snippet = text.replace("\n", " ")[:80]
        if parent is not None and parent.user_id != user.user_id:
            PostEngagementService._notify(
                db,
                parent.user_id,
                user,
                "post_comment_reply",
                f"{user.username} replied to your comment: {snippet}",
                post_id,
            )
        if post.user_id != user.user_id and (parent is None or parent.user_id != post.user_id):
            PostEngagementService._notify(
                db,
                post.user_id,
                user,
                "post_comment",
                f"{user.username} commented: {snippet}",
                post_id,
            )
        return PostEngagementService._comment_outs(db, [comment], user, post)[0]

    @staticmethod
    def delete_comment(
        db: Session, user: User, post_id: int, comment_id: int
    ) -> CommentDeleteResult:
        post = db.get(Post, post_id)
        comment = db.get(PostComment, comment_id)
        if post is None or comment is None or comment.post_id != post_id:
            raise _not_found("Comment not found.")
        allowed = user.is_admin or comment.user_id == user.user_id or post.user_id == user.user_id
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own comments.",
            )
        reply_ids = list(
            db.execute(select(PostComment.comment_id).where(PostComment.parent_id == comment_id))
            .scalars()
            .all()
        )
        all_ids = reply_ids + [comment_id]
        db.execute(delete(PostCommentLike).where(PostCommentLike.comment_id.in_(all_ids)))
        if reply_ids:
            db.execute(delete(PostComment).where(PostComment.comment_id.in_(reply_ids)))
        db.execute(delete(PostComment).where(PostComment.comment_id == comment_id))
        db.commit()
        return CommentDeleteResult(
            comment_id=comment_id, comment_count=PostEngagementService._comment_total(db, post_id)
        )

    @staticmethod
    def _comment_like_state(db: Session, comment_id: int, liked: bool) -> CommentLikeState:
        count = db.execute(
            select(func.count(PostCommentLike.id)).where(PostCommentLike.comment_id == comment_id)
        ).scalar() or 0
        return CommentLikeState(liked=liked, like_count=int(count))

    @staticmethod
    def like_comment(db: Session, user: User, post_id: int, comment_id: int) -> CommentLikeState:
        post = PostEngagementService.get_interactable_post(db, user, post_id)
        if post.comments_disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Comments are turned off for this post.",
            )
        comment = db.get(PostComment, comment_id)
        if comment is None or comment.post_id != post_id:
            raise _not_found("Comment not found.")
        db.add(PostCommentLike(comment_id=comment_id, user_id=user.user_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return PostEngagementService._comment_like_state(db, comment_id, True)

    @staticmethod
    def unlike_comment(db: Session, user: User, post_id: int, comment_id: int) -> CommentLikeState:
        comment = db.get(PostComment, comment_id)
        if comment is None or comment.post_id != post_id:
            raise _not_found("Comment not found.")
        db.execute(
            delete(PostCommentLike).where(
                PostCommentLike.comment_id == comment_id, PostCommentLike.user_id == user.user_id
            )
        )
        db.commit()
        return PostEngagementService._comment_like_state(db, comment_id, False)

    # ------------------------------------------------------------ insights
    @staticmethod
    def insights(db: Session, user: User, post_id: int) -> InsightsOut:
        post = db.get(Post, post_id)
        if post is None:
            raise _not_found()
        if post.user_id != user.user_id and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the owner can see the insights of a post.",
            )

        def count(model_col, where) -> int:
            return int(db.execute(select(func.count(model_col)).where(where)).scalar() or 0)

        reach = count(PostView.view_id, PostView.post_id == post_id)
        followers_reach = int(
            db.execute(
                select(func.count(PostView.view_id))
                .join(
                    Follow,
                    and_(
                        Follow.follower_id == PostView.user_id,
                        Follow.following_id == post.user_id,
                    ),
                )
                .where(PostView.post_id == post_id)
            ).scalar()
            or 0
        )
        likes = count(PostLike.like_id, PostLike.post_id == post_id)
        comments = count(PostComment.comment_id, PostComment.post_id == post_id)
        shares = count(PostShare.share_id, PostShare.post_id == post_id)
        saves = count(PostSave.save_id, PostSave.post_id == post_id)
        poll_votes: Optional[int] = None
        if post.post_type == "poll":
            poll_votes = count(PostPollVote.vote_id, PostPollVote.post_id == post_id)

        engagement: Optional[float] = None
        if reach > 0:
            engagement = round((likes + comments + shares + saves) / reach * 100, 1)

        # Last 7 days (UTC), oldest first
        today = _utc_now().date()
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        start = days[0]
        like_by_day = {
            str(d): int(n)
            for d, n in db.execute(
                select(func.date(PostLike.created_at), func.count(PostLike.like_id))
                .where(PostLike.post_id == post_id, func.date(PostLike.created_at) >= str(start))
                .group_by(func.date(PostLike.created_at))
            ).all()
        }
        comment_by_day = {
            str(d): int(n)
            for d, n in db.execute(
                select(func.date(PostComment.created_at), func.count(PostComment.comment_id))
                .where(
                    PostComment.post_id == post_id, func.date(PostComment.created_at) >= str(start)
                )
                .group_by(func.date(PostComment.created_at))
            ).all()
        }
        daily = [
            InsightsDay(
                date=str(d), likes=like_by_day.get(str(d), 0), comments=comment_by_day.get(str(d), 0)
            )
            for d in days
        ]
        return InsightsOut(
            post_id=post_id,
            status=post.status,
            published_at=_iso(post.published_at),
            reach=reach,
            followers_reach=followers_reach,
            non_followers_reach=max(0, reach - followers_reach),
            likes=likes,
            comments=comments,
            shares=shares,
            saves=saves,
            engagement_rate=engagement,
            poll_votes=poll_votes,
            daily=daily,
        )