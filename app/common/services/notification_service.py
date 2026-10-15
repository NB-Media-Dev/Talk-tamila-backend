"""
Notification service — returns active notifications merged with unread DMs.
"""
import re
from datetime import datetime, timezone
from typing import List, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, delete, or_, func
from app.common.models.messaging import DirectMessage, MESSAGE_KIND_CALL, ChatState
from app.common.models.social import Notification, Follow
from app.common.models.story import StoryLike
from app.common.models.user import User
from app.common.schemas.social import NotificationResponse


def _utc_now_iso() -> str:
    return f"{datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}Z"


def _iso(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    s = dt.isoformat()
    return s if s.endswith("Z") or ("+" in s or "-" in s[10:]) else f"{s}Z"


def _uname(msg: Optional[str]) -> Optional[str]:
    if not msg:
        return None
    m = re.match(r"^@?([A-Za-z0-9_]+)", msg.strip())
    return m.group(1).lower() if m else None


class NotificationService:
    @staticmethod
    def get_notifications(user_id: int, db: Session, limit: int = 50) -> List[NotificationResponse]:
        raw_notifs = (
            db.query(Notification)
            .filter(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit * 2)
            .all()
        )

        dm_ids: Set[int] = {n.reference_id for n in raw_notifs if n.reference_id and n.type in ("new_message", "story_reply", "story_react")}
        story_ids: Set[int] = {n.reference_id for n in raw_notifs if n.reference_id and n.type in ("story_like", "story_reply", "story_react", "story_share", "STORY_MENTION", "STORY_SHARED", "story_mention", "story_shared")}
        follower_ids: Set[int] = {n.reference_id for n in raw_notifs if n.reference_id and n.type == "follow"}
        unames: Set[str] = {_uname(n.message) for n in raw_notifs if _uname(n.message)}

        dms = {d.id: d for d in db.execute(select(DirectMessage).where(DirectMessage.id.in_(dm_ids))).scalars().all()} if dm_ids else {}
        follows = set(db.execute(select(Follow.follower_id).where(Follow.follower_id.in_(follower_ids), Follow.following_id == user_id)).scalars().all()) if follower_ids else set()

        likes: Set = set()
        if story_ids:
            for sid, lby, uid in db.execute(select(StoryLike.story_id, StoryLike.liked_by, StoryLike.user_id).where(StoryLike.story_id.in_(story_ids))).all():
                if lby: likes.add((sid, lby.lower()))
                if uid: likes.add((sid, uid))

        warning_ids: Set[int] = {
            n.reference_id for n in raw_notifs
            if n.reference_id and (
                n.type in ("story_warning", "admin_warning", "warning")
                or "admin warning" in (n.message or "").lower()
                or "warning" in (n.type or "").lower()
            )
        }

        candidate_uids = set(follower_ids)
        if warning_ids:
            candidate_uids.update(warning_ids)
        if dms:
            candidate_uids.update(d.sender_id for d in dms.values())
        if dm_ids:
            candidate_uids.update(dm_ids)

        user_filter = [func.lower(User.username).in_([un.lower() for un in unames])] if unames else []
        if candidate_uids:
            user_filter.append(User.user_id.in_(list(candidate_uids)))
        users_by_name, users_by_id = {}, {}
        if user_filter:
            for u in db.execute(select(User).where(or_(*user_filter) if len(user_filter) > 1 else user_filter[0])).scalars().all():
                if u.username: users_by_name[u.username.lower()] = u
                users_by_id[u.user_id] = u

        admin_fallback = db.execute(select(User).where(User.role == "admin").order_by(User.user_id.asc())).scalars().first()

        stale_ids, active_notifs = [], []
        for n in raw_notifs:
            un = _uname(n.message)
            u = users_by_name.get(un) if un else None
            uid = u.user_id if u else None

            active = True
            if n.type == "story_like":
               
                if un or uid:
                    active = (n.reference_id, un) in likes or (n.reference_id, uid) in likes
            elif n.type == "new_message":
                active = n.reference_id is None or n.reference_id in dms
            elif n.type == "follow":
                active = n.reference_id in follows

            if active:
                active_notifs.append((n, u))
            else:
                stale_ids.append(n.id)

        if stale_ids:
            try:
                db.execute(delete(Notification).where(Notification.id.in_(stale_ids)))
                db.commit()
            except Exception:
                db.rollback()

        covered_dm_ids = {n.reference_id for n, _ in active_notifs if n.reference_id and n.type in ("new_message", "story_reply", "story_react")}

        result: List[NotificationResponse] = []
        for n, u in active_notifs:
            dm = dms.get(n.reference_id)
            is_warning = (
                n.type in ("story_warning", "admin_warning", "warning")
                or "warning" in (n.type or "").lower()
                or "admin warning" in (n.message or "").lower()
            )
            if is_warning:
                actor = (
                    (users_by_id.get(n.reference_id) if n.reference_id in users_by_id else None)
                    or admin_fallback
                    or u
                )
            else:
                actor = (
                    (users_by_id.get(dm.sender_id) if dm else None)
                    or (users_by_id.get(n.reference_id) if (n.type in ("follow", "new_message", "message_react") and n.reference_id in users_by_id) else None)
                    or u
                )
            result.append(NotificationResponse(
                id=n.id,
                user_id=n.user_id,
                type=n.type,
                message=n.message,
                reference_id=actor.user_id if (is_warning and actor) else n.reference_id,
                is_read=n.is_read,
                created_at=_iso(n.created_at),
                actor_id=actor.user_id if actor else None,
                actor_username=actor.username if actor else None,
            ))

        unread_dms = (
            db.query(DirectMessage)
            .filter(DirectMessage.receiver_id == user_id, DirectMessage.read_at.is_(None), DirectMessage.kind != MESSAGE_KIND_CALL)
            .order_by(desc(DirectMessage.id))
            .limit(50)
            .all()
        )

        sender_ids = {m.sender_id for m in unread_dms}
        chat_states = {r.partner_id: r.cleared_before_id for r in db.execute(select(ChatState).where(ChatState.user_id == user_id, ChatState.partner_id.in_(list(sender_ids)))).scalars().all()} if sender_ids else {}
        dm_users = {u.user_id: u for u in db.execute(select(User).where(User.user_id.in_(list(sender_ids)))).scalars().all()} if sender_ids else {}

        for dm in unread_dms:
            if dm.id <= chat_states.get(dm.sender_id, 0) or dm.id in covered_dm_ids:
                continue

            sender = dm_users.get(dm.sender_id)
            sname = (sender.username or sender.full_name or f"User {dm.sender_id}") if sender else f"User {dm.sender_id}"
            snip = (dm.body or "").strip()[:80]
            kind = dm.kind or "text"

            if kind == "story_reply":
                msg_text, notif_type, ref_id = f"{sname} replied to your story: {snip}", "story_reply", dm.story_id or dm.id
            elif kind == "story_reaction":
                msg_text, notif_type, ref_id = f"{sname} reacted to your story: {snip}", "story_react", dm.story_id or dm.id
            else:
                msg_text, notif_type, ref_id = f"{sname} sent you a message: {snip}", "new_message", dm.id

            result.append(NotificationResponse(
                id=-(dm.id),
                user_id=user_id,
                type=notif_type,
                message=msg_text,
                reference_id=ref_id,
                is_read=False,
                created_at=_iso(dm.created_at) or _utc_now_iso(),
                actor_id=dm.sender_id,
                actor_username=sender.username if sender else None,
            ))

        result.sort(key=lambda n: n.created_at, reverse=True)
        return result[:limit]

    @staticmethod
    def get_unread_count(user_id: int, db: Session) -> dict:
        unread_count = (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
            .count()
        )
        return {"unread_count": unread_count}

    @staticmethod
    def _get_own_notification(user_id: int, notification_id: int, db: Session) -> Notification:
        notification = (
            db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if notification is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
        return notification

    @staticmethod
    def mark_notification_read(user_id: int, notification_id: int, db: Session) -> dict:
        notification = NotificationService._get_own_notification(user_id, notification_id, db)
        notification.is_read = True
        db.commit()
        return {"success": True}

    @staticmethod
    def mark_all_notifications_read(user_id: int, db: Session) -> dict:
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        return {"success": True}

    @staticmethod
    def delete_notification(user_id: int, notification_id: int, db: Session) -> dict:
        notification = NotificationService._get_own_notification(user_id, notification_id, db)
        db.delete(notification)
        db.commit()
        return {"success": True}
