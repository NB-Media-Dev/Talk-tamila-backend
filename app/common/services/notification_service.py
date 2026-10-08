"""
Notification service — returns active notifications merged with unread DMs.
Automatically prunes stale notifications (unliked stories, unsent DMs, unfollows).
"""
import re
from datetime import datetime, timezone
from typing import List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, delete, or_, func
from app.common.models.social import Notification, Follow
from app.common.schemas.social import NotificationResponse
from app.common.models.messaging import DirectMessage, MESSAGE_KIND_CALL, ChatState
from app.common.models.story import Story, StoryLike
from app.common.models.user import User


def _utc_now_iso() -> str:
    return f"{datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}Z"


def _iso(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    s = dt.isoformat()
    return s if s.endswith("Z") or ("+" in s or "-" in s[10:]) else f"{s}Z"


def _uname(msg: Optional[str]) -> Optional[str]:
    m = re.match(r"^([A-Za-z0-9_]+)", (msg or "").strip())
    return m.group(1).lower() if m else None


class NotificationService:
    @staticmethod
    def get_user_notifications(user_id: int, db: Session, limit: int = 50) -> List[NotificationResponse]:
       
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
        stories = {s for s in db.execute(select(Story.story_id).where(Story.story_id.in_(story_ids), Story.is_deleted == False)).scalars().all()} if story_ids else set()
        follows = set(db.execute(select(Follow.follower_id).where(Follow.follower_id.in_(follower_ids), Follow.following_id == user_id)).scalars().all()) if follower_ids else set()

        likes: Set = set()
        if story_ids:
            for sid, lby, uid in db.execute(select(StoryLike.story_id, StoryLike.liked_by, StoryLike.user_id).where(StoryLike.story_id.in_(story_ids))).all():
                if lby: likes.add((sid, lby.lower()))
                if uid: likes.add((sid, uid))

        candidate_uids = set(follower_ids)
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


        stale_ids, active_notifs = [], []
        for n in raw_notifs:
            un = _uname(n.message)
            u = users_by_name.get(un) if un else None
            uid = u.user_id if u else None

            active = True
            if n.type == "story_like":
                active = n.reference_id in stories and ((n.reference_id, un) in likes or (n.reference_id, uid) in likes)
            elif n.type == "new_message":
                active = n.reference_id is None or n.reference_id in dms
            elif n.type in ("story_reply", "story_react", "story_share", "STORY_MENTION", "STORY_SHARED", "story_mention", "story_shared"):
                active = n.reference_id in stories or (n.reference_id in dms)
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
                reference_id=n.reference_id,
                is_read=n.is_read,
                created_at=_iso(n.created_at),
                actor_id=actor.user_id if actor else None,
                actor_username=actor.username if actor else None,
            ))


        result.sort(key=lambda n: n.created_at, reverse=True)
        return result[:limit]
