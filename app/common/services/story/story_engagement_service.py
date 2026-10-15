"""Viewer actions on a story: view, like, react, reply, share, save, report."""

import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.common.models.social import Notification
from app.common.models.story import (
    Story,
    StoryLike,
    StoryReply,
    StoryReport,
    StorySave,
    StoryShare,
    StoryView,
)
from app.common.models.user import User
from app.common.models.messaging import DirectMessage, MESSAGE_KIND_STORY_REACTION, MESSAGE_KIND_STORY_REPLY
from app.common.services.message_service import MessageService
from app.common.schemas.story import (
    StoryReplyResponse,
    StoryShareResponse,
)

from app.common.services.story.story_helpers import (
    format_iso,
    make_naive,
    utc_now,
)

logger = logging.getLogger(__name__)


class StoryEngagementService:
    @staticmethod
    def record_story_view(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = (
            db.query(StoryView)
            .filter(StoryView.story_id == story_id, StoryView.user_id == current_user.id)
            .first()
        )
      
        sender_name = None
        if story.user_id:
            story_owner = db.get(User, story.user_id)
            if story_owner:
                sender_name = story_owner.username
        if not sender_name:
            sender_name = getattr(story, "username", None) or (story.owner.username if story.owner else None)

        if not existing:
            view = StoryView(
                story_id=story_id,
                user_id=current_user.id,
                story_sender=sender_name,
                viewed_by=current_user.username,
                viewed_at=make_naive(utc_now()),
            )
            db.add(view)
            db.commit()
        else:
            updated = False
            if (not existing.story_sender or existing.story_sender != sender_name) and sender_name:
                existing.story_sender = sender_name
                updated = True
            if not existing.viewed_by or existing.viewed_by != current_user.username:
                existing.viewed_by = current_user.username
                updated = True
            if updated:
                db.commit()

        views_count = (
            db.query(func.count(func.distinct(StoryView.user_id)))
            .filter(StoryView.story_id == story_id)
            .scalar() or 0
        )
        return {"success": True, "message": "Story viewed", "story_id": story_id, "views_count": views_count}

    @staticmethod
    def like_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot like your own story.")

      
        owner_name = None
        if story.user_id:
            story_owner = db.get(User, story.user_id)
            if story_owner:
                owner_name = story_owner.username
        if not owner_name:
            owner_name = getattr(story, "username", None) or (story.owner.username if story.owner else None)

        existing = (
            db.query(StoryLike)
            .filter(StoryLike.story_id == story_id, StoryLike.user_id == current_user.id)
            .first()
        )
        if not existing:
            like = StoryLike(
                story_id=story_id,
                user_id=current_user.id,
                user_name=owner_name,
                liked_by=current_user.username,
                liked_at=make_naive(utc_now()),
            )
            db.add(like)
            db.commit()

            if story.user_id != current_user.id:
              
                StoryEngagementService._notify_story_owner(
                    db, story, "story_like", f"{current_user.username} liked your story"
                )
                StoryEngagementService._send_story_message(
                    db, current_user.id, story, MESSAGE_KIND_STORY_REACTION, "\u2764\ufe0f"
                )
        else:
            updated = False
            if (not existing.user_name or existing.user_name != owner_name) and owner_name:
                existing.user_name = owner_name
                updated = True
            if not existing.liked_by or existing.liked_by != current_user.username:
                existing.liked_by = current_user.username
                updated = True
            if updated:
                db.commit()

        likes_count = (
            db.query(func.count(func.distinct(StoryLike.user_id)))
            .filter(StoryLike.story_id == story_id)
            .scalar() or 0
        )
        return {"story_id": story_id, "likes_count": likes_count, "liked_by_me": True, "success": True}

    @staticmethod
    def unlike_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = (
            db.query(StoryLike)
            .filter(StoryLike.story_id == story_id, StoryLike.user_id == current_user.id)
            .first()
        )
        if existing:
            db.delete(existing)
          
            if story.user_id != current_user.id:
                try:
                    db.query(Notification).filter(
                        Notification.user_id == story.user_id,
                        Notification.type == "story_like",
                        Notification.reference_id == story_id,
                        Notification.message.like(f"{current_user.username}%"),
                    ).delete(synchronize_session=False)

                   
                    db.query(DirectMessage).filter(
                        DirectMessage.sender_id == current_user.id,
                        DirectMessage.receiver_id == story.user_id,
                        DirectMessage.story_id == story_id,
                        DirectMessage.kind == MESSAGE_KIND_STORY_REACTION,
                        DirectMessage.body == "\u2764\ufe0f",
                    ).delete(synchronize_session=False)
                except Exception:
                    logger.exception("Error cleaning up story_like notification or DM on unlike")

            db.commit()

        likes_count = (
            db.query(func.count(func.distinct(StoryLike.user_id)))
            .filter(StoryLike.story_id == story_id)
            .scalar() or 0
        )
        return {"story_id": story_id, "likes_count": likes_count, "liked_by_me": False, "success": True}

    @staticmethod
    def pause_story(
        story_id: int,
        action: str,
        progress_ms: Optional[int],
        slide_index: Optional[int],
        current_user: User,
        db: Session,
    ) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        logger.info(
            "User %s %s story %s (slide: %s, progress: %sms)",
            current_user.id,
            action,
            story_id,
            slide_index,
            progress_ms,
        )
        return {
            "success": True,
            "action": action,
            "story_id": story_id,
            "slide_index": slide_index,
            "progress_ms": progress_ms,
            "user_id": current_user.id,
        }

    @staticmethod
    def _send_story_message(db: Session, sender_id: int, story: Story, kind: str, body: str):
        try:
            return MessageService.send_story_message(
                db, sender_id, story.user_id, story.story_id, kind, body
            )
        except Exception:
            db.rollback()
            logger.exception("Could not send story %s as a message (story_id=%s)", kind, story.story_id)
            return None

    @staticmethod
    def _notify_story_owner(db: Session, story: Story, notif_type: str, message: str) -> None:
        try:
            db.add(
                Notification(
                    user_id=story.user_id,
                    type=notif_type,
                    message=message,
                    reference_id=story.story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not create %s notification (story_id=%s)", notif_type, story.story_id)

    @staticmethod
    def reply_to_story(story_id: int, text: str, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
        if story.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot reply to your own story.")

        receiver_name = None
        if story.user_id:
            story_owner = db.get(User, story.user_id)
            if story_owner:
                receiver_name = story_owner.username
        if not receiver_name:
            receiver_name = getattr(story, "username", None) or (story.owner.username if story.owner else None)

        sender_name = current_user.username

        reply = StoryReply(
            story_id=story_id,
            user_id=current_user.id,
            sender_name=sender_name,
            receiver_name=receiver_name,
            text=text,
            created_at=make_naive(utc_now()),
        )
        db.add(reply)
        db.commit()
        db.refresh(reply)

        if story.user_id != current_user.id:
            try:
                notif = Notification(
                    user_id=story.user_id,
                    type="story_reply",
                    message=f"{current_user.username} replied to your story: {text[:50]}",
                    reference_id=story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
                db.add(notif)
                db.commit()
            except Exception:
                db.rollback()

           
            StoryEngagementService._send_story_message(
                db, current_user.id, story, MESSAGE_KIND_STORY_REPLY, text
            )

        return {
            "success": True,
            "message": "Reply sent successfully",
            "reply_id": reply.reply_id,
            "sender_name": reply.sender_name,
            "receiver_name": reply.receiver_name,
            "text": reply.text,
            "created_at": format_iso(reply.created_at) or utc_now().isoformat(),
        }

    @staticmethod
    def get_story_comments(story_id: int, db: Session) -> List[StoryReplyResponse]:
        replies = (
            db.query(StoryReply)
            .options(joinedload(StoryReply.user))
            .filter(StoryReply.story_id == story_id)
            .order_by(desc(StoryReply.created_at))
            .all()
        )
        return [
            StoryReplyResponse(
                reply_id=r.reply_id,
                story_id=r.story_id,
                user_id=r.user_id,
                text=r.text,
                created_at=format_iso(r.created_at) or utc_now().isoformat(),
                username=r.sender_name or (r.user.username if r.user else f"user_{r.user_id}"),
                sender_name=r.sender_name or (r.user.username if r.user else f"user_{r.user_id}"),
                receiver_name=r.receiver_name,
                avatar_url=r.user.avatar_url if r.user else None,
            )
            for r in replies
        ]

    @staticmethod
    def share_story(
        story_id: int,
        platform: str,
        current_user: User,
        db: Session,
        target_user_id: Optional[int] = None,
    ) -> StoryShareResponse:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        share = StoryShare(
            story_id=story_id,
            user_id=current_user.id,
            platform=platform or "copy_link",
            created_at=make_naive(utc_now()),
        )
        db.add(share)

        if target_user_id and target_user_id != current_user.id:
            try:
                notif = Notification(
                    user_id=target_user_id,
                    type="story_share",
                    message=f"{current_user.username} shared a story with you",
                    reference_id=story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
                db.add(notif)
            except Exception:
                pass

        db.commit()
        total_shares = db.query(func.count(StoryShare.share_id)).filter(StoryShare.story_id == story_id).scalar() or 0
        share_url = f"/stories/{story_id}"

        return StoryShareResponse(
            success=True,
            message="Story shared successfully",
            story_id=story_id,
            shares_count=total_shares,
            share_url=share_url,
        )

    @staticmethod
    def save_story(story_id: int, current_user: User, db: Session) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = db.query(StorySave).filter(
            StorySave.story_id == story_id,
            StorySave.user_id == current_user.id,
        ).first()

        if not existing:
            save_entry = StorySave(
                story_id=story_id,
                user_id=current_user.id,
                saved_at=make_naive(utc_now()),
            )
            db.add(save_entry)
            db.commit()

        return {
            "success": True,
            "message": "Story saved successfully",
            "story_id": story_id,
            "is_saved": True,
        }

    @staticmethod
    def unsave_story(story_id: int, current_user: User, db: Session) -> dict:
        existing = db.query(StorySave).filter(
            StorySave.story_id == story_id,
            StorySave.user_id == current_user.id,
        ).first()

        if existing:
            db.delete(existing)
            db.commit()

        return {
            "success": True,
            "message": "Story removed from saved",
            "story_id": story_id,
            "is_saved": False,
        }

    @staticmethod
    def react_to_story(story_id: int, emoji: str, current_user: User, db: Session) -> dict:
        from app.common.schemas.story import StoryReactResponse

        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        
        owner_name = None
        if story.user_id:
            story_owner = db.get(User, story.user_id)
            if story_owner:
                owner_name = story_owner.username
        if not owner_name:
            owner_name = getattr(story, "username", None) or (story.owner.username if story.owner else None)

        existing = (
            db.query(StoryLike)
            .filter(
                StoryLike.story_id == story_id,
                StoryLike.user_id == current_user.id,
            )
            .first()
        )
        if not existing:
            db.add(
                StoryLike(
                    story_id=story_id,
                    user_id=current_user.id,
                    user_name=owner_name,
                    liked_by=current_user.username,
                    liked_at=make_naive(utc_now()),
                )
            )
        else:
            if owner_name and existing.user_name != owner_name:
                existing.user_name = owner_name
            if existing.liked_by != current_user.username:
                existing.liked_by = current_user.username
        db.commit()

        if story.user_id != current_user.id:
            sent = StoryEngagementService._send_story_message(
                db, current_user.id, story, MESSAGE_KIND_STORY_REACTION, emoji
            )
          
            if sent:
                StoryEngagementService._notify_story_owner(
                    db,
                    story,
                    "story_react",
                    f"{current_user.username} reacted {emoji} to your story",
                )

        return StoryReactResponse(
            success=True,
            story_id=story_id,
            emoji=emoji,
            message=f"Reacted with {emoji}",
        )

    @staticmethod
    def report_story(story_id: int, reason: str, current_user: User, db: Session, details: Optional[str] = None) -> dict:
        story = db.get(Story, story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        existing = db.query(StoryReport).filter(
            StoryReport.story_id == story_id,
            StoryReport.user_id == current_user.id,
        ).first()
        if existing:
            return {"success": True, "message": "You've already reported this story.", "story_id": story_id}

        report = StoryReport(
            story_id=story_id,
            user_id=current_user.id,
            reason=reason[:255] if reason else "Inappropriate content",
            details=details,
            created_at=make_naive(utc_now()),
        )
        db.add(report)

        # Notify all admins about the new story report
        admin_users = db.query(User).filter(User.role == "admin").all()
        for admin in admin_users:
            db.add(
                Notification(
                    user_id=admin.user_id,
                    type="story_report",
                    message=f"@{current_user.username} reported story #{story_id}: {reason[:100]}",
                    reference_id=story_id,
                    is_read=False,
                    created_at=make_naive(utc_now()),
                )
            )

        db.commit()
        return {"success": True, "message": "Thank you. Your report has been submitted.", "story_id": story_id}
