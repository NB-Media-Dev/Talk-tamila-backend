import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.common.models.moderation import UserBlock
from app.common.models.post import (
    STATUS_ARCHIVED,
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
)
from app.common.models.social import Follow, Notification, Profile
from app.common.models.user import User
from app.common.schemas.post import (
    CommentDeleteResult,
    CommentLikeState,
    CommentListResponse,
    CommentOut,
    InsightsDay,
    InsightsOut,
    LikersResponse,
    LikeState,
    LikerPreview,
    PostAuthor,
    PostUserOut,
    SaveState,
    ShareState,
)

logger = logging.getLogger("talktamila.post_engagement")

MSG_POST_NOT_FOUND = "Post not found."
MSG_COMMENT_NOT_FOUND = "Comment not found."


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _err(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _missing() -> HTTPException:
    return _err(status.HTTP_404_NOT_FOUND, MSG_POST_NOT_FOUND)


def _count(db: Session, column, *conditions) -> int:
    return db.execute(select(func.count(column)).where(*conditions)).scalar() or 0


def _count_by(db: Session, group_col, count_col, ids: List[int]) -> Dict[int, int]:
    return dict(
        db.execute(
            select(group_col, func.count(count_col)).where(group_col.in_(ids)).group_by(group_col)
        ).all()
    )


def _ghost_author(user_id: int) -> PostAuthor:
    return PostAuthor(user_id=user_id, name=f"User {user_id}", username=f"user_{user_id}", role="user")


class PostEngagementService:
   
    @staticmethod
    def blocked_ids(db: Session, user_id: int) -> Set[int]:
        """All user IDs blocked by or blocking this user."""
        if not user_id:
            return set()
        by_me = db.execute(select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id)).scalars()
        of_me = db.execute(select(UserBlock.blocker_id).where(UserBlock.blocked_id == user_id)).scalars()
        return set(by_me.all()) | set(of_me.all())

    @staticmethod
    def blocked_between(db: Session, u1_id: int, u2_id: int) -> bool:
        if not u1_id or not u2_id or u1_id == u2_id:
            return False
        return (
            db.execute(
                select(UserBlock.id)
                .where(
                    or_(
                        and_(UserBlock.blocker_id == u1_id, UserBlock.blocked_id == u2_id),
                        and_(UserBlock.blocker_id == u2_id, UserBlock.blocked_id == u1_id),
                    )
                )
                .limit(1)
            ).scalar()
            is not None
        )

   
    @staticmethod
    def _can_see(db: Session, user: User, post: Post) -> bool:
        if post.status == STATUS_PUBLISHED:
            if post.user_id == user.user_id:
                return True
            owner = db.get(User, post.user_id)
            return bool(owner and owner.is_active) and not PostEngagementService.blocked_between(
                db, user.user_id, post.user_id
            )
        if post.status == STATUS_ARCHIVED:
            return post.user_id == user.user_id or bool(user.is_admin)
        return bool(user.is_admin)  

    @staticmethod
    def _get_post(db: Session, user: User, post_id: int, strict: bool = True) -> Post:
        """Load a post. With strict=True the viewer must also be allowed to see it."""
        post = db.get(Post, post_id)
        if post is None or post.is_deleted:
            raise _missing()
        if strict and not PostEngagementService._can_see(db, user, post):
            raise _missing()
        return post

    @staticmethod
    def _get_comment(db: Session, post_id: int, comment_id: int) -> PostComment:
        comment = db.execute(
            select(PostComment).where(
                PostComment.comment_id == comment_id, PostComment.post_id == post_id
            )
        ).scalar_one_or_none()
        if comment is None:
            raise _err(status.HTTP_404_NOT_FOUND, MSG_COMMENT_NOT_FOUND)
        return comment

    @staticmethod
    def _notify(db: Session, actor: User, to_user_id: int, kind: str, post_id: int, text: str) -> None:
        if to_user_id != actor.user_id:
            db.add(
                Notification(
                    user_id=to_user_id,
                    type=kind,
                    reference_id=post_id,
                    message=f"{actor.username} {text}",
                )
            )

    @staticmethod
    def _commit_ignoring_duplicates(db: Session) -> None:
        """Commit; a unique-constraint race (double tap) is treated as success."""
        try:
            db.commit()
        except IntegrityError:
            db.rollback()

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
    def _build_comment_out(
        comment: PostComment,
        post: Post,
        current_user: User,
        author: PostAuthor,
        like_count: int,
        liked_by_me: bool,
        reply_count: int,
    ) -> CommentOut:
        return CommentOut(
            comment_id=comment.comment_id,
            post_id=comment.post_id,
            parent_id=comment.parent_id,
            body=comment.body,
            created_at=_iso(comment.created_at) or "",
            author=author,
            like_count=like_count,
            liked_by_me=liked_by_me,
            reply_count=reply_count,
            can_delete=bool(
                current_user.is_admin
                or comment.user_id == current_user.user_id
                or post.user_id == current_user.user_id
            ),
            by_post_owner=comment.user_id == post.user_id,
        )

    
    @staticmethod
    def snapshot(db: Session, post_ids: List[int], viewer_id: int, author_ids: List[int]) -> dict:
        empty = {
            "likes": {},
            "comments": {},
            "shares": {},
            "liked": set(),
            "saved": set(),
            "shared": set(),
            "preview": {},
            "following": set(),
        }
        if not post_ids:
            return empty

        liked = set(
            db.execute(
                select(PostLike.post_id).where(
                    PostLike.post_id.in_(post_ids), PostLike.user_id == viewer_id
                )
            ).scalars()
        )
        saved = set(
            db.execute(
                select(PostSave.post_id).where(
                    PostSave.post_id.in_(post_ids), PostSave.user_id == viewer_id
                )
            ).scalars()
        )
        shared = set(
            db.execute(
                select(PostShare.post_id).where(
                    PostShare.post_id.in_(post_ids), PostShare.user_id == viewer_id
                )
            ).scalars()
        )
        following = set()
        if author_ids:
            following = set(
                db.execute(
                    select(Follow.following_id).where(
                        Follow.follower_id == viewer_id, Follow.following_id.in_(author_ids)
                    )
                ).scalars()
            )

        
        preview: Dict[int, LikerPreview] = {}
        rows = db.execute(
            select(PostLike.post_id, User.user_id, User.username)
            .join(User, User.user_id == PostLike.user_id)
            .join(
                Follow,
                and_(Follow.following_id == PostLike.user_id, Follow.follower_id == viewer_id),
            )
            .where(PostLike.post_id.in_(post_ids))
            .order_by(PostLike.like_id.desc())
        ).all()
        for pid, uid, uname in rows:
            preview.setdefault(pid, LikerPreview(user_id=uid, username=uname))

        return {
            "likes": _count_by(db, PostLike.post_id, PostLike.like_id, post_ids),
            "comments": _count_by(db, PostComment.post_id, PostComment.comment_id, post_ids),
            "shares": _count_by(db, PostShare.post_id, PostShare.share_id, post_ids),
            "liked": liked,
            "saved": saved,
            "shared": shared,
            "preview": preview,
            "following": following,
        }

    
    @staticmethod
    def _like_state(db: Session, user: User, post: Post, liked: bool) -> LikeState:
        total = _count(db, PostLike.like_id, PostLike.post_id == post.post_id)
        hidden = bool(post.hide_like_count) and post.user_id != user.user_id
        return LikeState(liked=liked, like_count=None if hidden else total)

    @staticmethod
    def like_post(db: Session, current_user: User, post_id: int) -> LikeState:
        post = PostEngagementService._get_post(db, current_user, post_id)
        exists = db.execute(
            select(PostLike.like_id).where(
                PostLike.post_id == post_id, PostLike.user_id == current_user.user_id
            )
        ).first()
        if not exists:
            db.add(PostLike(post_id=post_id, user_id=current_user.user_id))
            PostEngagementService._notify(
                db, current_user, post.user_id, "post_like", post_id, "liked your post"
            )
            PostEngagementService._commit_ignoring_duplicates(db)
        return PostEngagementService._like_state(db, current_user, post, True)

    @staticmethod
    def unlike_post(db: Session, current_user: User, post_id: int) -> LikeState:
        post = PostEngagementService._get_post(db, current_user, post_id, strict=False)
        existing = db.execute(
            select(PostLike).where(
                PostLike.post_id == post_id, PostLike.user_id == current_user.user_id
            )
        ).scalar_one_or_none()
        if existing:
            db.delete(existing)
            db.query(Notification).filter(
                Notification.user_id == post.user_id,
                Notification.type == "post_like",
                Notification.reference_id == post_id,
                Notification.message == f"{current_user.username} liked your post",
            ).delete(synchronize_session=False)
            db.commit()
        return PostEngagementService._like_state(db, current_user, post, False)

    @staticmethod
    def list_post_likers(
        db: Session, current_user: User, post_id: int, limit: int = 50, offset: int = 0
    ) -> LikersResponse:
        PostEngagementService._get_post(db, current_user, post_id)
        blocked = PostEngagementService.blocked_ids(db, current_user.user_id)

        query = (
            select(User, Profile)
            .join(PostLike, PostLike.user_id == User.user_id)
            .outerjoin(Profile, Profile.user_id == User.user_id)
            .where(PostLike.post_id == post_id)
        )
        total_q = select(func.count(PostLike.like_id)).where(PostLike.post_id == post_id)
        if blocked:
            query = query.where(User.user_id.not_in(blocked))
            total_q = total_q.where(PostLike.user_id.not_in(blocked))

        rows = db.execute(
            query.order_by(PostLike.created_at.desc(), PostLike.like_id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        items = [
            PostUserOut(
                user_id=u.user_id,
                username=u.username,
                name=u.full_name or u.username,
                avatar_url=p.profile_pic_url if p else None,
                role=u.role,
            )
            for u, p in rows
        ]
        return LikersResponse(items=items, total=db.execute(total_q).scalar() or 0)

    
    @staticmethod
    def save_post(db: Session, current_user: User, post_id: int) -> SaveState:
        PostEngagementService._get_post(db, current_user, post_id)
        exists = db.execute(
            select(PostSave.save_id).where(
                PostSave.post_id == post_id, PostSave.user_id == current_user.user_id
            )
        ).first()
        if not exists:
            db.add(PostSave(post_id=post_id, user_id=current_user.user_id))
            PostEngagementService._commit_ignoring_duplicates(db)
        return SaveState(saved=True)

    @staticmethod
    def unsave_post(db: Session, current_user: User, post_id: int) -> SaveState:
        PostEngagementService._get_post(db, current_user, post_id, strict=False)
        existing = db.execute(
            select(PostSave).where(
                PostSave.post_id == post_id, PostSave.user_id == current_user.user_id
            )
        ).scalar_one_or_none()
        if existing:
            db.delete(existing)
            db.commit()
        return SaveState(saved=False)

    
    @staticmethod
    def share_post(
        db: Session,
        current_user: User,
        post_id: int,
        channel: str = "link",
        recipients: int = 1,
    ) -> ShareState:
        post = PostEngagementService._get_post(db, current_user, post_id)
        existing = db.execute(
            select(PostShare.share_id).where(
                PostShare.post_id == post_id,
                PostShare.user_id == current_user.user_id,
            ).limit(1)
        ).first()

        if not existing:
            db.add(
                PostShare(
                    post_id=post_id,
                    user_id=current_user.user_id,
                    channel=channel,
                )
            )
            PostEngagementService._notify(
                db,
                current_user,
                post.user_id,
                "post_share",
                post_id,
                "shared your post",
            )
        PostEngagementService._commit_ignoring_duplicates(db)
        total=_count(
            db,PostShare.share_id,
            PostShare.post_id==post_id
        )
        return ShareState(share_count=total)

    #db.add_all(
           # PostShare(post_id=post_id, user_id=current_user.user_id, channel=channel)
           # for _ in range(max(1, min(int(recipients or 1), 50)))
       # )
       # PostEngagementService._notify(
     #       db, current_user, post.user_id, "post_share", post_id, "shared your post"
      #  )
      #  db.commit()
       # return ShareState(share_count=_count(db, PostShare.share_id, PostShare.post_id == post_id))

    @staticmethod
    def view_post(db: Session, current_user: User, post_id: int) -> dict:
        post = PostEngagementService._get_post(db, current_user, post_id)
        if post.user_id != current_user.user_id:
            exists = db.execute(
                select(PostView.view_id).where(
                    PostView.post_id == post_id, PostView.user_id == current_user.user_id
                )
            ).first()
            if not exists:
                db.add(PostView(post_id=post_id, user_id=current_user.user_id))
                PostEngagementService._commit_ignoring_duplicates(db)
        return {"success": True}

    @staticmethod
    def report_post(db: Session, current_user: User, post_id: int, reason: str) -> dict:
        PostEngagementService._get_post(db, current_user, post_id)
        exists = db.execute(
            select(PostReport.report_id).where(
                PostReport.post_id == post_id, PostReport.reporter_id == current_user.user_id
            )
        ).first()
        if not exists:
            db.add(
                PostReport(
                    post_id=post_id, reporter_id=current_user.user_id, reason=(reason or "")[:50]
                )
            )
            PostEngagementService._commit_ignoring_duplicates(db)
        return {"success": True, "message": "Report submitted."}



   
    @staticmethod
    def _daily_counts(db: Session, model, post_id: int, since: datetime) -> Dict[str, int]:
        day = func.date(model.created_at)
        rows = db.execute(
            select(day, func.count())
            .where(model.post_id == post_id, model.created_at >= since)
            .group_by(day)
        ).all()
        return {str(d): int(n) for d, n in rows}

    @staticmethod
    def get_post_insights(db: Session, current_user: User, post_id: int) -> InsightsOut:
        post = PostEngagementService._get_post(db, current_user, post_id, strict=False)
        if not current_user.is_admin and post.user_id != current_user.user_id:
            raise _err(
                status.HTTP_403_FORBIDDEN,
                "You do not have permission to view insights for this post.",
            )

        reach = _count(db, PostView.view_id, PostView.post_id == post_id)
        followers_reach = _count(
            db,
            PostView.view_id,
            PostView.post_id == post_id,
            PostView.user_id.in_(select(Follow.follower_id).where(Follow.following_id == post.user_id)),
        )
        likes = _count(db, PostLike.like_id, PostLike.post_id == post_id)
        comments = _count(db, PostComment.comment_id, PostComment.post_id == post_id)
        shares = _count(db, PostShare.share_id, PostShare.post_id == post_id)
        saves = _count(db, PostSave.save_id, PostSave.post_id == post_id)

        engagements = likes + comments + shares + saves
        poll_votes = (
            _count(db, PostPollVote.vote_id, PostPollVote.post_id == post_id)
            if post.post_type == "poll"
            else None
        )

        today = datetime.utcnow().date()
        days = [today - timedelta(days=n) for n in range(6, -1, -1)]
        since = datetime.combine(days[0], datetime.min.time())
        like_by_day = PostEngagementService._daily_counts(db, PostLike, post_id, since)
        comment_by_day = PostEngagementService._daily_counts(db, PostComment, post_id, since)
        daily = [
            InsightsDay(
                date=d.isoformat(),
                likes=like_by_day.get(d.isoformat(), 0),
                comments=comment_by_day.get(d.isoformat(), 0),
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
            engagement_rate=round(engagements / reach * 100.0, 2) if reach > 0 else None,
            poll_votes=poll_votes,
            daily=daily,
        )

    
    @staticmethod
    def _comment_items(
        db: Session, user: User, post: Post, rows: List[PostComment], with_reply_counts: bool
    ) -> List[CommentOut]:
        if not rows:
            return []
        ids = [c.comment_id for c in rows]
        authors = PostEngagementService._load_authors(db, list({c.user_id for c in rows}))
        likes = _count_by(db, PostCommentLike.comment_id, PostCommentLike.id, ids)
        mine = set(
            db.execute(
                select(PostCommentLike.comment_id).where(
                    PostCommentLike.comment_id.in_(ids), PostCommentLike.user_id == user.user_id
                )
            ).scalars()
        )
        replies = (
            _count_by(db, PostComment.parent_id, PostComment.comment_id, ids)
            if with_reply_counts
            else {}
        )
        return [
            PostEngagementService._build_comment_out(
                c,
                post,
                user,
                authors.get(c.user_id) or _ghost_author(c.user_id),
                likes.get(c.comment_id, 0),
                c.comment_id in mine,
                replies.get(c.comment_id, 0),
            )
            for c in rows
        ]

    @staticmethod
    def _comment_page(
        db: Session, user: User, post: Post, stmt, limit: int, total: int, top_level: bool
    ) -> CommentListResponse:
        rows = list(db.execute(stmt.limit(limit + 1)).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        return CommentListResponse(
            items=PostEngagementService._comment_items(db, user, post, rows, top_level),
            total=total,
            has_more=has_more,
            next_cursor=rows[-1].comment_id if has_more and rows else None,
            comments_disabled=bool(post.comments_disabled),
        )

    @staticmethod
    def list_post_comments(
        db: Session,
        current_user: User,
        post_id: int,
        limit: int = 20,
        before_id: Optional[int] = None,
    ) -> CommentListResponse:
        post = PostEngagementService._get_post(db, current_user, post_id)
        if post.comments_disabled:
            return CommentListResponse(items=[], total=0, comments_disabled=True)

        blocked = PostEngagementService.blocked_ids(db, current_user.user_id)
        stmt = select(PostComment).where(
            PostComment.post_id == post_id, PostComment.parent_id.is_(None)
        )
        if blocked:
            stmt = stmt.where(PostComment.user_id.not_in(blocked))
        if before_id:
            stmt = stmt.where(PostComment.comment_id < before_id)

        total = _count(db, PostComment.comment_id, PostComment.post_id == post_id)
        return PostEngagementService._comment_page(
            db, current_user, post, stmt.order_by(PostComment.comment_id.desc()), limit, total, True
        )

    @staticmethod
    def list_comment_replies(
        db: Session,
        current_user: User,
        post_id: int,
        comment_id: int,
        limit: int = 20,
        after_id: Optional[int] = None,
    ) -> CommentListResponse:
        post = PostEngagementService._get_post(db, current_user, post_id)
        PostEngagementService._get_comment(db, post_id, comment_id)

        blocked = PostEngagementService.blocked_ids(db, current_user.user_id)
        stmt = select(PostComment).where(
            PostComment.post_id == post_id, PostComment.parent_id == comment_id
        )
        if blocked:
            stmt = stmt.where(PostComment.user_id.not_in(blocked))
        if after_id:
            stmt = stmt.where(PostComment.comment_id > after_id)

        total = _count(
            db,
            PostComment.comment_id,
            PostComment.post_id == post_id,
            PostComment.parent_id == comment_id,
        )
        return PostEngagementService._comment_page(
            db, current_user, post, stmt.order_by(PostComment.comment_id.asc()), limit, total, False
        )

    @staticmethod
    def add_post_comment(
        db: Session,
        current_user: User,
        post_id: int,
        body: str,
        parent_id: Optional[int] = None,
    ) -> CommentOut:
        post = PostEngagementService._get_post(db, current_user, post_id)
        if post.comments_disabled:
            raise _err(status.HTTP_400_BAD_REQUEST, "Comments are disabled for this post.")

        text = (body or "").strip()
        if not text:
            raise _err(status.HTTP_400_BAD_REQUEST, "Comment cannot be empty.")
        if len(text) > 1000:
            raise _err(status.HTTP_400_BAD_REQUEST, "Comment must be 1000 characters or fewer.")

        parent_comment = None
        if parent_id is not None:
            parent_comment = db.execute(
                select(PostComment).where(
                    PostComment.comment_id == parent_id, PostComment.post_id == post_id
                )
            ).scalar_one_or_none()
            if parent_comment is None:
                raise _err(status.HTTP_404_NOT_FOUND, "Parent comment not found.")
            if parent_comment.parent_id is not None:  
                parent_id = parent_comment.parent_id

        comment = PostComment(
            post_id=post_id, user_id=current_user.user_id, parent_id=parent_id, body=text
        )
        db.add(comment)

        notify = PostEngagementService._notify
        if parent_comment:
            notify(db, current_user, parent_comment.user_id, "post_comment_reply", post_id,
                   "replied to your comment")
        if not parent_comment or parent_comment.user_id != post.user_id:
            notify(db, current_user, post.user_id, "post_comment", post_id,
                   "commented on your post")
        db.commit()
        db.refresh(comment)

        author = PostEngagementService._load_authors(db, [current_user.user_id]).get(
            current_user.user_id
        ) or PostAuthor(
            user_id=current_user.user_id,
            name=current_user.full_name or current_user.username,
            username=current_user.username,
            role=current_user.role,
            avatar_url=current_user.avatar_url,
        )
        return PostEngagementService._build_comment_out(comment, post, current_user, author, 0, False, 0)

    @staticmethod
    def delete_post_comment(
        db: Session, current_user: User, post_id: int, comment_id: int
    ) -> CommentDeleteResult:
        post = PostEngagementService._get_post(db, current_user, post_id, strict=False)
        comment = PostEngagementService._get_comment(db, post_id, comment_id)
        if not (
            current_user.is_admin
            or comment.user_id == current_user.user_id
            or post.user_id == current_user.user_id
        ):
            raise _err(
                status.HTTP_403_FORBIDDEN, "You do not have permission to delete this comment."
            )

        db.query(PostComment).filter(PostComment.parent_id == comment_id).delete(
            synchronize_session=False
        )
        db.delete(comment)
        db.commit()
        return CommentDeleteResult(
            success=True,
            comment_id=comment_id,
            comment_count=_count(db, PostComment.comment_id, PostComment.post_id == post_id),
        )

    @staticmethod
    def _comment_like_total(db: Session, comment_id: int) -> int:
        return _count(db, PostCommentLike.id, PostCommentLike.comment_id == comment_id)

    @staticmethod
    def like_post_comment(
        db: Session, current_user: User, post_id: int, comment_id: int
    ) -> CommentLikeState:
        PostEngagementService._get_post(db, current_user, post_id)
        comment = PostEngagementService._get_comment(db, post_id, comment_id)
        exists = db.execute(
            select(PostCommentLike.id).where(
                PostCommentLike.comment_id == comment_id,
                PostCommentLike.user_id == current_user.user_id,
            )
        ).first()
        if not exists:
            db.add(PostCommentLike(comment_id=comment_id, user_id=current_user.user_id))
            PostEngagementService._notify(
                db, current_user, comment.user_id, "comment_like", post_id, "liked your comment"
            )
            PostEngagementService._commit_ignoring_duplicates(db)
        return CommentLikeState(
            liked=True, like_count=PostEngagementService._comment_like_total(db, comment_id)
        )

    @staticmethod
    def unlike_post_comment(
        db: Session, current_user: User, post_id: int, comment_id: int
    ) -> CommentLikeState:
        PostEngagementService._get_post(db, current_user, post_id, strict=False)
        PostEngagementService._get_comment(db, post_id, comment_id)
        existing = db.execute(
            select(PostCommentLike).where(
                PostCommentLike.comment_id == comment_id,
                PostCommentLike.user_id == current_user.user_id,
            )
        ).scalar_one_or_none()
        if existing:
            db.delete(existing)
            db.commit()
        return CommentLikeState(
            liked=False, like_count=PostEngagementService._comment_like_total(db, comment_id)
        )

  