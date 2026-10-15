"""Owner analytics: activity, viewers, likers and totals."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.common.models.story import (
    Story,
    StoryLike,
    StoryReply,
    StoryShare,
    StoryView,
)
from app.common.models.user import User
from app.common.schemas.story import (
    ActivityLiker,
    ActivityViewer,
    StoryActivityResponse,
)

from app.common.services.story.story_helpers import (
    format_iso,
    make_naive,
    utc_now,
)

logger = logging.getLogger(__name__)


class StoryAnalyticsService:
    @staticmethod
    def get_story_activity(story_id: int, current_user: User, db: Session) -> StoryActivityResponse:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story author can view viewer activity.")

        likes = db.query(StoryLike).options(joinedload(StoryLike.user)).filter(StoryLike.story_id == story_id).order_by(desc(StoryLike.liked_at)).all()
        likers_list: List[ActivityLiker] = []
        liked_user_ids = set()
        liked_by_me = False
        for l in likes:
            if l.user_id == current_user.id:
                liked_by_me = True
            if l.user_id not in liked_user_ids:
                liked_user_ids.add(l.user_id)
                u = l.user
                liker_name = l.likes_by or (u.username if u else (l.user_name or f"user_{l.user_id}"))
                likers_list.append(
                    ActivityLiker(
                        user_id=l.user_id,
                        username=liker_name,
                        avatar_url=u.avatar_url if u else None,
                        full_name=u.full_name if u else (liker_name or f"User {l.user_id}"),
                    )
                )

        views = (
            db.query(StoryView)
            .options(joinedload(StoryView.user))
            .filter(StoryView.story_id == story_id)
            .order_by(StoryView.viewed_at.asc())
            .all()
        )
        viewers_list: List[ActivityViewer] = []
        seen_viewers = set()
        for v in views:
            if v.user_id not in seen_viewers:
                seen_viewers.add(v.user_id)
                u = v.user
                is_liked = v.user_id in liked_user_ids
                viewer_name = v.viewed_by or (u.username if u else f"user_{v.user_id}")
                viewers_list.append(
                    ActivityViewer(
                        user_id=v.user_id,
                        username=viewer_name,
                        avatar_url=u.avatar_url if u else None,
                        full_name=u.full_name if u else (viewer_name or f"User {v.user_id}"),
                        viewed_at=format_iso(v.viewed_at) or utc_now().isoformat(),
                        liked=is_liked,
                    )
                )

        for l in likes:
            if l.user_id not in seen_viewers:
                seen_viewers.add(l.user_id)
                u = l.user
                viewers_list.append(
                    ActivityViewer(
                        user_id=l.user_id,
                        username=u.username if u else (l.user_name or f"user_{l.user_id}"),
                        avatar_url=u.avatar_url if u else None,
                        full_name=u.full_name if u else (l.user_name or f"User {l.user_id}"),
                        viewed_at=format_iso(l.liked_at) or utc_now().isoformat(),
                        liked=True,
                    )
                )

        viewers_list.sort(key=lambda x: (0 if x.liked else 1))

        return StoryActivityResponse(
            story_id=story_id,
            total_views=len(seen_viewers),
            total_likes=len(likers_list),
            liked_by_me=liked_by_me,
            viewers=viewers_list,
            likers=likers_list,
        )

    @staticmethod
    def get_story_viewers(
        story_id: int,
        current_user: User,
        db: Session,
        page: int = 1,
        page_size: int = 20,
    ):
        from app.common.schemas.story import PaginatedViewerResponse, StoryViewerItem

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story owner can see viewers.")

        total = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id == story_id).scalar() or 0
        offset = (page - 1) * page_size
        rows = (
            db.query(StoryView)
            .options(joinedload(StoryView.user))
            .filter(StoryView.story_id == story_id)
            .order_by(desc(StoryView.viewed_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        items = [
            StoryViewerItem(
                user_id=v.user_id,
                viewed_by=v.viewed_by or (v.user.username if v.user else f"user_{v.user_id}"),
                username=v.viewed_by or (v.user.username if v.user else f"user_{v.user_id}"),
                story_sender=v.story_sender,
                full_name=v.user.full_name if v.user else None,
                avatar_url=v.user.avatar_url if v.user else None,
                viewed_at=format_iso(v.viewed_at) or utc_now().isoformat(),
            )
            for v in rows
        ]
        return PaginatedViewerResponse(
            story_id=story_id,
            total_views=total,
            page=page,
            page_size=page_size,
            viewers=items,
        )

    @staticmethod
    def get_story_likers(
        story_id: int,
        current_user: User,
        db: Session,
        page: int = 1,
        page_size: int = 20,
    ):
        from app.common.schemas.story import PaginatedLikerResponse, StoryLikerItem

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only the story owner can see likers.")

        total = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == story_id).scalar() or 0
        offset = (page - 1) * page_size
        rows = (
            db.query(StoryLike)
            .options(joinedload(StoryLike.user))
            .filter(StoryLike.story_id == story_id)
            .order_by(desc(StoryLike.liked_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )
        items = [
            StoryLikerItem(
                user_id=lk.user_id,
                liked_by=lk.likes_by or (lk.user.username if lk.user else (lk.user_name or f"user_{lk.user_id}")),
                likes_by=lk.likes_by or (lk.user.username if lk.user else (lk.user_name or f"user_{lk.user_id}")),
                username=lk.likes_by or (lk.user.username if lk.user else (lk.user_name or f"user_{lk.user_id}")),
                full_name=lk.user.full_name if lk.user else None,
                avatar_url=lk.user.avatar_url if lk.user else None,
                liked_at=format_iso(lk.liked_at) or utc_now().isoformat(),
            )
            for lk in rows
        ]
        return PaginatedLikerResponse(
            story_id=story_id,
            total_likes=total,
            page=page,
            page_size=page_size,
            likers=items,
        )

    @staticmethod
    def get_my_story_stats(current_user: User, db: Session):
        from app.common.schemas.story import StoryStatsResponse

        now_naive = make_naive(utc_now())

        story_ids_rows = db.query(Story.story_id).filter(Story.user_id == current_user.id).all()
        story_ids = [r[0] for r in story_ids_rows]
        total_stories = len(story_ids)

        if not story_ids:
            return StoryStatsResponse(
                user_id=current_user.id,
                total_stories=0,
                total_views=0,
                total_likes=0,
                total_replies=0,
                total_shares=0,
                active_stories=0,
                expired_stories=0,
            )

        total_views = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id.in_(story_ids)).scalar() or 0
        total_likes = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id.in_(story_ids)).scalar() or 0
        total_replies = db.query(func.count(StoryReply.reply_id)).filter(StoryReply.story_id.in_(story_ids)).scalar() or 0
        total_shares = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id.in_(story_ids)).scalar() or 0

        active_stories = db.query(func.count(Story.story_id)).filter(
            Story.user_id == current_user.id,
            or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
        ).scalar() or 0
        expired_stories = total_stories - active_stories

        return StoryStatsResponse(
            user_id=current_user.id,
            total_stories=total_stories,
            total_views=total_views,
            total_likes=total_likes,
            total_replies=total_replies,
            total_shares=total_shares,
            active_stories=active_stories,
            expired_stories=expired_stories,
        )

    @staticmethod
    def get_my_story_analytics(current_user: User, db: Session) -> Dict[str, Any]:
        now_naive = make_naive(utc_now())

        stories: List[Story] = (
            db.query(Story)
            .options(
                selectinload(Story.views).selectinload(StoryView.user),
                selectinload(Story.likes).selectinload(StoryLike.user),
                selectinload(Story.replies).selectinload(StoryReply.user),
            )
            .filter(
                Story.user_id == current_user.user_id,
                or_(Story.expires_at.is_(None), Story.expires_at > now_naive),
            )
            .order_by(desc(Story.created_at))
            .all()
        )

        def format_user_dict(u: Optional[User]) -> Optional[Dict[str, Any]]:
            if not u:
                return None
            return {
                "id": u.user_id,
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "full_name": u.full_name,
            }

        stories_data: List[Dict[str, Any]] = []
        total_views_count = 0
        total_likes_count = 0
        total_replies_count = 0

        for story in stories:
            viewers_list = [
                {
                    "view_id": v.view_id,
                    "viewed_at": format_iso(v.viewed_at),
                    "user": format_user_dict(v.user),
                }
                for v in story.views
            ]

            likers_list = [
                {
                    "like_id": lk.story_likes_id,
                    "liked_at": format_iso(lk.liked_at),
                    "user": format_user_dict(lk.user),
                }
                for lk in story.likes
            ]

            replies_list = [
                {
                    "reply_id": r.reply_id,
                    "text": r.text,
                    "created_at": format_iso(r.created_at),
                    "user": format_user_dict(r.user),
                }
                for r in story.replies
            ]

            v_count = len(viewers_list)
            l_count = len(likers_list)
            r_count = len(replies_list)

            total_views_count += v_count
            total_likes_count += l_count
            total_replies_count += r_count

            stories_data.append({
                "story_id": story.story_id,
                "media_url": story.media_url,
                "media_type": story.media_type or "image",
                "caption": story.caption,
                "created_at": format_iso(story.created_at),
                "expires_at": format_iso(story.expires_at),
                "total_views": v_count,
                "total_likes": l_count,
                "total_replies": r_count,
                "viewers": viewers_list,
                "likers": likers_list,
                "replies": replies_list,
            })

        return {
            "summary": {
                "total_active_stories": len(stories_data),
                "total_views": total_views_count,
                "total_likes": total_likes_count,
                "total_replies": total_replies_count,
            },
            "stories": stories_data,
        }
