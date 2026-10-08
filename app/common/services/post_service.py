import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.common.models.post import (
    Post,
    PostComment,
    PostLike,
    PostSave,
    PostShare,
    PostView,
)
from app.common.models.user import User
from app.common.schemas.post import (
    PostAuthorInfo,
    PostCommentRequest,
    PostCommentResponse,
    PostCreateRequest,
    PostFeedResponse,
    PostItemResponse,
    PostPlatformStats,
    PostUpdateRequest,
)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _format_iso(dt: Optional[datetime]) -> str:
    if not dt:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def _format_human_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "just now"
    now = _utc_now_naive()
    diff = now - (dt.replace(tzinfo=None) if dt.tzinfo else dt)
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return f"{max(1, seconds)}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 7:
        return f"{days}d"
    weeks = days // 7
    if weeks < 4:
        return f"{weeks}w"
    return dt.strftime("%b %d")


def _parse_json_list(val: Optional[str]) -> List[str]:
    if not val:
        return []
    try:
        res = json.loads(val)
        if isinstance(res, list):
            return [str(x) for x in res]
        return [str(res)]
    except Exception:
        return [s.strip() for s in val.split(",") if s.strip()]


def _parse_json_dict(val: Optional[str]) -> Optional[Dict[str, Any]]:
    if not val:
        return None
    try:
        res = json.loads(val)
        if isinstance(res, dict):
            return res
        return None
    except Exception:
        return None


def _format_post_response(
    post: Post,
    is_liked: bool = False,
    is_saved: bool = False,
    extra_analytics: Optional[Dict[str, Any]] = None,
) -> PostItemResponse:
    owner = post.owner
    author_info = PostAuthorInfo(
        user_id=post.user_id,
        username=post.username or (owner.username if owner else "admin"),
        first_name=owner.first_name if owner else "Talk Tamila",
        last_name=owner.last_name if owner else "Admin",
        full_name=owner.full_name if owner else "Talk Tamila Official",
        role=owner.role if owner else "admin",
        avatar_url=owner.avatar_url if owner else "/Images/avatar4.png",
        location=owner.location if owner else post.location or "Tamil Nadu, India",
    )

    platforms = _parse_json_list(post.platforms)
    tags = _parse_json_list(post.tags)
    poll_data = _parse_json_dict(post.poll_data)

    # Generated or stored analytics for rich UI display
    analytics = extra_analytics or {
        "views": f"{post.views_count:,}" if post.views_count > 0 else "1.2K",
        "likes": f"{post.likes_count:,}" if post.likes_count > 0 else "0",
        "comments": f"{post.comments_count:,}" if post.comments_count > 0 else "0",
        "shares": f"{post.shares_count:,}" if post.shares_count > 0 else "0",
        "saves": f"{post.saves_count:,}" if post.saves_count > 0 else "0",
        "aiPerformanceScore": "94",
        "aiPerformanceLabel": "High Performing",
        "trendingProb": "High",
    }

    return PostItemResponse(
        id=post.post_id,
        post_id=post.post_id,
        user_id=post.user_id,
        author_id=post.user_id,
        username=post.username or (owner.username if owner else "admin"),
        title=post.title,
        caption=post.caption,
        content=post.caption,
        media_type=post.media_type or "image",
        media_url=post.media_url,
        thumbnail_url=post.thumbnail_url,
        aspect_ratio=post.aspect_ratio,
        platforms=platforms if platforms else ["Talk Tamila"],
        tags=tags,
        poll_data=poll_data,
        audience=post.audience or "PUBLIC",
        status=post.status or "published",
        location=post.location or (owner.location if owner else None),
        scheduled_at=_format_iso(post.scheduled_at) if post.scheduled_at else None,
        views_count=post.views_count,
        likes_count=post.likes_count,
        comments_count=post.comments_count,
        shares_count=post.shares_count,
        saves_count=post.saves_count,
        is_liked=is_liked,
        is_saved=is_saved,
        created_at=_format_iso(post.created_at),
        created_at_human=_format_human_time(post.created_at),
        author=author_info,
        analytics=analytics,
    )


class PostService:

    @staticmethod
    def create_admin_post(
        payload: PostCreateRequest,
        current_admin: User,
        db: Session,
    ) -> PostItemResponse:
        """Create a public post uploaded by an Admin user.
        Ensures the post is published publicly under the Admin's ID and profile.
        """
        if current_admin.role != "admin" and not current_admin.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin accounts are permitted to publish admin posts.",
            )

        # Extract hashtags from caption if not explicitly specified
        tags = list(payload.tags or [])
        if payload.caption:
            found_tags = re.findall(r"#\w+", payload.caption)
            for t in found_tags:
                clean_t = t.lstrip("#")
                if clean_t and clean_t not in tags:
                    tags.append(clean_t)

        platforms = payload.platforms or ["Talk Tamila"]
        if "Talk Tamila" not in platforms:
            platforms.insert(0, "Talk Tamila")

        post = Post(
            user_id=current_admin.user_id,
            username=current_admin.username,
            title=payload.title.strip() if payload.title else None,
            caption=payload.caption.strip() if payload.caption else None,
            media_type=payload.media_type or "image",
            media_url=payload.media_url,
            thumbnail_url=payload.thumbnail_url or payload.media_url,
            aspect_ratio=payload.aspect_ratio,
            platforms=json.dumps(platforms),
            tags=json.dumps(tags),
            poll_data=json.dumps(payload.poll_data) if payload.poll_data else None,
            audience="PUBLIC",
            status=payload.status or "published",
            location=payload.location or current_admin.location,
            scheduled_at=payload.scheduled_at,
            views_count=1,
            likes_count=0,
            comments_count=0,
            shares_count=0,
            saves_count=0,
            is_deleted=False,
        )

        db.add(post)

        # Increment admin profile posts count
        admin_profile = current_admin._ensure_profile()
        admin_profile.posts_count = (admin_profile.posts_count or 0) + 1

        db.commit()
        db.refresh(post)

        return _format_post_response(post, is_liked=False, is_saved=False)

    @staticmethod
    def get_feed(
        db: Session,
        current_user: Optional[User] = None,
        media_type: Optional[str] = None,
        tag: Optional[str] = None,
        user_id: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> PostFeedResponse:
        """Fetch public posts for the universal feed (visible to all users: admins, influencers, freelancers, guests)."""
        query = (
            db.query(Post)
            .options(joinedload(Post.owner))
            .filter(Post.is_deleted == False, Post.status == "published")
        )

        if media_type:
            query = query.filter(Post.media_type == media_type)

        if tag:
            clean_tag = tag.lstrip("#")
            query = query.filter(Post.tags.like(f"%{clean_tag}%"))

        if user_id:
            query = query.filter(Post.user_id == user_id)

        if search:
            search_term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Post.title.ilike(search_term),
                    Post.caption.ilike(search_term),
                    Post.username.ilike(search_term),
                )
            )

        total = query.count()
        posts = query.order_by(desc(Post.created_at)).offset(offset).limit(limit).all()

        liked_post_ids = set()
        saved_post_ids = set()
        if current_user:
            post_ids = [p.post_id for p in posts]
            if post_ids:
                likes = (
                    db.query(PostLike.post_id)
                    .filter(
                        PostLike.post_id.in_(post_ids),
                        PostLike.user_id == current_user.user_id,
                    )
                    .all()
                )
                liked_post_ids = {l[0] for l in likes}

                saves = (
                    db.query(PostSave.post_id)
                    .filter(
                        PostSave.post_id.in_(post_ids),
                        PostSave.user_id == current_user.user_id,
                    )
                    .all()
                )
                saved_post_ids = {s[0] for s in saves}

        items = [
            _format_post_response(
                p,
                is_liked=(p.post_id in liked_post_ids),
                is_saved=(p.post_id in saved_post_ids),
            )
            for p in posts
        ]

        return PostFeedResponse(items=items, total=total)

    @staticmethod
    def get_post_by_id(
        post_id: int,
        db: Session,
        current_user: Optional[User] = None,
    ) -> PostItemResponse:
        post = (
            db.query(Post)
            .options(joinedload(Post.owner))
            .filter(Post.post_id == post_id, Post.is_deleted == False)
            .first()
        )
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        is_liked = False
        is_saved = False
        if current_user:
            is_liked = (
                db.query(PostLike.id)
                .filter(PostLike.post_id == post.post_id, PostLike.user_id == current_user.user_id)
                .first()
                is not None
            )
            is_saved = (
                db.query(PostSave.id)
                .filter(PostSave.post_id == post.post_id, PostSave.user_id == current_user.user_id)
                .first()
                is not None
            )

        return _format_post_response(post, is_liked=is_liked, is_saved=is_saved)

    @staticmethod
    def get_user_posts(
        username_or_id: str,
        db: Session,
        current_user: Optional[User] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> List[PostItemResponse]:
        """Fetch all public posts by a specific user (e.g. admin or influencer) for their profile page."""
        target_user = None
        if username_or_id.isdigit():
            target_user = db.get(User, int(username_or_id))
        if not target_user:
            clean_username = username_or_id.strip().lstrip("@")
            target_user = (
                db.query(User)
                .filter(func.lower(User.username) == clean_username.lower())
                .first()
            )

        if not target_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        posts = (
            db.query(Post)
            .options(joinedload(Post.owner))
            .filter(
                Post.user_id == target_user.user_id,
                Post.is_deleted == False,
                Post.status == "published",
            )
            .order_by(desc(Post.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        liked_post_ids = set()
        saved_post_ids = set()
        if current_user:
            post_ids = [p.post_id for p in posts]
            if post_ids:
                likes = (
                    db.query(PostLike.post_id)
                    .filter(
                        PostLike.post_id.in_(post_ids),
                        PostLike.user_id == current_user.user_id,
                    )
                    .all()
                )
                liked_post_ids = {l[0] for l in likes}

                saves = (
                    db.query(PostSave.post_id)
                    .filter(
                        PostSave.post_id.in_(post_ids),
                        PostSave.user_id == current_user.user_id,
                    )
                    .all()
                )
                saved_post_ids = {s[0] for s in saves}

        return [
            _format_post_response(
                p,
                is_liked=(p.post_id in liked_post_ids),
                is_saved=(p.post_id in saved_post_ids),
            )
            for p in posts
        ]

    @staticmethod
    def update_post(
        post_id: int,
        payload: PostUpdateRequest,
        current_user: User,
        db: Session,
    ) -> PostItemResponse:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        if post.user_id != current_user.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this post.",
            )

        if payload.title is not None:
            post.title = payload.title.strip() if payload.title else None
        if payload.caption is not None:
            post.caption = payload.caption.strip() if payload.caption else None
        if payload.media_type is not None:
            post.media_type = payload.media_type
        if payload.media_url is not None:
            post.media_url = payload.media_url
        if payload.thumbnail_url is not None:
            post.thumbnail_url = payload.thumbnail_url
        if payload.aspect_ratio is not None:
            post.aspect_ratio = payload.aspect_ratio
        if payload.platforms is not None:
            post.platforms = json.dumps(payload.platforms)
        if payload.tags is not None:
            post.tags = json.dumps(payload.tags)
        if payload.status is not None:
            post.status = payload.status
        if payload.location is not None:
            post.location = payload.location

        db.commit()
        db.refresh(post)
        return _format_post_response(post)

    @staticmethod
    def delete_post(post_id: int, current_user: User, db: Session) -> dict:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        if post.user_id != current_user.user_id and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this post.",
            )

        post.is_deleted = True
        post.deleted_at = _utc_now_naive()

        # Decrement owner profile posts count
        if post.owner and post.owner.profile and post.owner.profile.posts_count > 0:
            post.owner.profile.posts_count -= 1

        db.commit()
        return {"success": True, "message": "Post removed successfully"}

    @staticmethod
    def toggle_like(post_id: int, current_user: User, db: Session) -> dict:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        existing_like = (
            db.query(PostLike)
            .filter(PostLike.post_id == post_id, PostLike.user_id == current_user.user_id)
            .first()
        )

        if existing_like:
            db.delete(existing_like)
            post.likes_count = max(0, post.likes_count - 1)
            liked = False
        else:
            new_like = PostLike(
                post_id=post_id,
                user_id=current_user.user_id,
                user_name=current_user.username,
            )
            db.add(new_like)
            post.likes_count = post.likes_count + 1
            liked = True

        db.commit()
        return {
            "success": True,
            "liked": liked,
            "likes_count": post.likes_count,
        }

    @staticmethod
    def add_comment(
        post_id: int,
        payload: PostCommentRequest,
        current_user: User,
        db: Session,
    ) -> PostCommentResponse:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        comment = PostComment(
            post_id=post_id,
            user_id=current_user.user_id,
            user_name=current_user.username,
            user_avatar=current_user.avatar_url,
            comment_text=payload.comment_text.strip(),
            parent_comment_id=payload.parent_comment_id,
        )
        db.add(comment)
        post.comments_count = post.comments_count + 1

        db.commit()
        db.refresh(comment)

        return PostCommentResponse(
            id=comment.id,
            post_id=comment.post_id,
            user_id=comment.user_id,
            user_name=comment.user_name,
            user_avatar=comment.user_avatar,
            comment_text=comment.comment_text,
            parent_comment_id=comment.parent_comment_id,
            created_at=_format_iso(comment.created_at),
            created_at_human=_format_human_time(comment.created_at),
        )

    @staticmethod
    def get_comments(
        post_id: int,
        db: Session,
        limit: int = 50,
        offset: int = 0,
    ) -> List[PostCommentResponse]:
        comments = (
            db.query(PostComment)
            .filter(PostComment.post_id == post_id)
            .order_by(PostComment.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            PostCommentResponse(
                id=c.id,
                post_id=c.post_id,
                user_id=c.user_id,
                user_name=c.user_name,
                user_avatar=c.user_avatar,
                comment_text=c.comment_text,
                parent_comment_id=c.parent_comment_id,
                created_at=_format_iso(c.created_at),
                created_at_human=_format_human_time(c.created_at),
            )
            for c in comments
        ]

    @staticmethod
    def toggle_save(post_id: int, current_user: User, db: Session) -> dict:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        existing_save = (
            db.query(PostSave)
            .filter(PostSave.post_id == post_id, PostSave.user_id == current_user.user_id)
            .first()
        )

        if existing_save:
            db.delete(existing_save)
            post.saves_count = max(0, post.saves_count - 1)
            saved = False
        else:
            new_save = PostSave(post_id=post_id, user_id=current_user.user_id)
            db.add(new_save)
            post.saves_count = post.saves_count + 1
            saved = True

        db.commit()
        return {
            "success": True,
            "saved": saved,
            "saves_count": post.saves_count,
        }

    @staticmethod
    def record_share(
        post_id: int,
        platform: Optional[str],
        current_user: User,
        db: Session,
    ) -> dict:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        share = PostShare(
            post_id=post_id,
            user_id=current_user.user_id,
            platform=platform or "Talk Tamila",
        )
        db.add(share)
        post.shares_count = post.shares_count + 1
        db.commit()

        return {
            "success": True,
            "shares_count": post.shares_count,
        }

    @staticmethod
    def record_view(
        post_id: int,
        current_user: Optional[User],
        db: Session,
    ) -> dict:
        post = db.query(Post).filter(Post.post_id == post_id, Post.is_deleted == False).first()
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

        view = PostView(
            post_id=post_id,
            user_id=current_user.user_id if current_user else None,
        )
        db.add(view)
        post.views_count = post.views_count + 1
        db.commit()

        return {
            "success": True,
            "views_count": post.views_count,
        }

    @staticmethod
    def get_platform_post_stats(db: Session) -> PostPlatformStats:
        total_posts = db.query(func.count(Post.post_id)).filter(Post.is_deleted == False).scalar() or 0
        total_views = db.query(func.sum(Post.views_count)).filter(Post.is_deleted == False).scalar() or 0
        total_likes = db.query(func.sum(Post.likes_count)).filter(Post.is_deleted == False).scalar() or 0
        total_comments = db.query(func.sum(Post.comments_count)).filter(Post.is_deleted == False).scalar() or 0
        total_shares = db.query(func.sum(Post.shares_count)).filter(Post.is_deleted == False).scalar() or 0
        total_saves = db.query(func.sum(Post.saves_count)).filter(Post.is_deleted == False).scalar() or 0

        return PostPlatformStats(
            total_posts=int(total_posts),
            total_views=int(total_views),
            total_likes=int(total_likes),
            total_comments=int(total_comments),
            total_shares=int(total_shares),
            total_saves=int(total_saves),
        )
