from typing import List, Optional
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc

from app.common.models.user import User
from app.common.models.story import (
    Story,
    StoryView,
    StoryLike,
    StoryReply,
    StoryShare,
    StoryReport,
)
from app.admin.schemas import (
    AdminOverview,
    AdminPlatformStoryStats,
    AdminStoryItem,
    AdminReportItem,
)
from app.common.schemas.story import StoryUserResponse


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _format_iso(dt: Optional[datetime]) -> str:
    if not dt:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


class AdminService:
    @staticmethod
    def get_overview(db: Session) -> AdminOverview:
        now_naive = _utc_now_naive()
        total_users = db.query(func.count(User.user_id)).scalar() or 0
        total_stories = db.query(func.count(Story.story_id)).scalar() or 0
        active_stories = (
            db.query(func.count(Story.story_id))
            .filter(
                Story.is_deleted == False,
                Story.expires_at > now_naive,
            )
            .scalar()
            or 0
        )
        total_views = db.query(func.count(StoryView.view_id)).scalar() or 0
        total_likes = db.query(func.count(StoryLike.story_likes_id)).scalar() or 0
        total_reports = db.query(func.count(StoryReport.report_id)).scalar() or 0

        return AdminOverview(
            total_users=total_users,
            total_stories=total_stories,
            active_stories=active_stories,
            total_views=total_views,
            total_likes=total_likes,
            total_reports=total_reports,
        )

    @staticmethod
    def get_platform_story_stats(db: Session) -> AdminPlatformStoryStats:
        now_naive = _utc_now_naive()
        total_stories = db.query(func.count(Story.story_id)).scalar() or 0
        active_stories = (
            db.query(func.count(Story.story_id))
            .filter(
                Story.is_deleted == False,
                Story.expires_at > now_naive,
            )
            .scalar()
            or 0
        )
        expired_stories = (
            db.query(func.count(Story.story_id))
            .filter(
                Story.is_deleted == False,
                Story.expires_at <= now_naive,
            )
            .scalar()
            or 0
        )
        deleted_stories = (
            db.query(func.count(Story.story_id))
            .filter(Story.is_deleted == True)
            .scalar()
            or 0
        )

        total_views = db.query(func.count(StoryView.view_id)).scalar() or 0
        total_likes = db.query(func.count(StoryLike.story_likes_id)).scalar() or 0
        total_replies = db.query(func.count(StoryReply.reply_id)).scalar() or 0
        total_shares = db.query(func.count(StoryShare.share_id)).scalar() or 0
        total_reports = db.query(func.count(StoryReport.report_id)).scalar() or 0

        return AdminPlatformStoryStats(
            total_stories=total_stories,
            active_stories=active_stories,
            expired_stories=expired_stories,
            deleted_stories=deleted_stories,
            total_views=total_views,
            total_likes=total_likes,
            total_replies=total_replies,
            total_shares=total_shares,
            total_reports=total_reports,
        )

    @staticmethod
    def get_all_stories(
        db: Session,
        role: Optional[str] = None,
        audience: Optional[str] = None,
        is_deleted: Optional[bool] = None,
        user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AdminStoryItem]:
        now_naive = _utc_now_naive()
        query = db.query(Story).options(joinedload(Story.owner))

        if role:
            query = query.join(Story.owner).filter(User.role == role)
        if audience:
            clean_aud = audience.strip().upper()
            query = query.filter(Story.audience == clean_aud)
        if is_deleted is not None:
            query = query.filter(Story.is_deleted == is_deleted)
        if user_id:
            query = query.filter(Story.user_id == user_id)

        stories = query.order_by(desc(Story.created_at)).offset(offset).limit(limit).all()

        results: List[AdminStoryItem] = []
        for s in stories:
            owner_resp = None
            if s.owner:
                owner_resp = StoryUserResponse(
                    id=s.owner.id,
                    user_id=s.owner.id,
                    userName=s.owner.username,
                    username=s.owner.username,
                    avatar=s.owner.avatar_url,
                    avatar_url=s.owner.avatar_url,
                    full_name=s.owner.full_name,
                    role=s.owner.role,
                    verified=s.owner.role in ("influencer", "admin"),
                )

            views_c = db.query(func.count(StoryView.view_id)).filter(StoryView.story_id == s.story_id).scalar() or 0
            likes_c = db.query(func.count(StoryLike.story_likes_id)).filter(StoryLike.story_id == s.story_id).scalar() or 0
            replies_c = db.query(func.count(StoryReply.reply_id)).filter(StoryReply.story_id == s.story_id).scalar() or 0
            shares_c = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id == s.story_id).scalar() or 0
            reports_c = db.query(func.count(StoryReport.report_id)).filter(StoryReport.story_id == s.story_id).scalar() or 0

            is_act = (not s.is_deleted) and (s.expires_at is None or s.expires_at > now_naive)

            results.append(
                AdminStoryItem(
                    id=s.story_id,
                    story_id=s.story_id,
                    user_id=s.user_id,
                    author_id=s.user_id,
                    media_url=s.media_url,
                    media_type=s.media_type or "image",
                    caption=s.caption,
                    content=s.caption,
                    audience=s.audience or "PUBLIC",
                    created_at=_format_iso(s.created_at),
                    expires_at=_format_iso(s.expires_at) if s.expires_at else None,
                    is_deleted=s.is_deleted,
                    is_active=is_act,
                    views_count=views_c,
                    likes_count=likes_c,
                    replies_count=replies_c,
                    shares_count=shares_c,
                    reports_count=reports_c,
                    user=owner_resp,
                )
            )

        return results

    @staticmethod
    def get_story_reports(db: Session, limit: int = 50, offset: int = 0) -> List[AdminReportItem]:
        reports = (
            db.query(StoryReport)
            .order_by(desc(StoryReport.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        results: List[AdminReportItem] = []
        for r in reports:
            reporter = db.get(User, r.user_id)
            reporter_uname = reporter.username if reporter else None

            story_obj = db.get(Story, r.story_id)
            story_item = None
            if story_obj:
                story_item = AdminStoryItem(
                    id=story_obj.story_id,
                    story_id=story_obj.story_id,
                    user_id=story_obj.user_id,
                    author_id=story_obj.user_id,
                    media_url=story_obj.media_url,
                    media_type=story_obj.media_type or "image",
                    caption=story_obj.caption,
                    content=story_obj.caption,
                    audience=story_obj.audience or "PUBLIC",
                    created_at=_format_iso(story_obj.created_at),
                    expires_at=_format_iso(story_obj.expires_at) if story_obj.expires_at else None,
                    is_deleted=story_obj.is_deleted,
                    is_active=not story_obj.is_deleted,
                )

            results.append(
                AdminReportItem(
                    report_id=r.report_id,
                    story_id=r.story_id,
                    user_id=r.user_id,
                    reporter_username=reporter_uname,
                    reason=r.reason,
                    created_at=_format_iso(r.created_at),
                    story=story_item,
                )
            )

        return results

    @staticmethod
    def delete_story(story_id: int, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        story.is_deleted = True
        story.deleted_at = _utc_now_naive()
        db.commit()
        return {"success": True, "message": f"Story {story_id} deleted by Admin"}

    @staticmethod
    def restore_story(story_id: int, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        story.is_deleted = False
        story.deleted_at = None
        db.commit()
        return {"success": True, "message": f"Story {story_id} restored by Admin"}

