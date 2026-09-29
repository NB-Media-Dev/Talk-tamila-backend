
"""Direct messaging: inbox, 1:1 threads, read receipts, reactions, people search."""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.models.messaging import (
    MESSAGE_KIND_STORY_REACTION,
    MESSAGE_KIND_STORY_REPLY,
    MESSAGE_KIND_TEXT,
    DirectMessage,
    MessageReaction,
)
from app.common.models.social import Follow
from app.common.models.story import Story
from app.common.models.user import User


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return f"{dt.isoformat()}Z" if dt else None


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _user_card(user: User, following_ids: Set[int]) -> Dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "bio": user.bio,
        "followers_count": user.followers_count or 0,
        "is_following": user.user_id in following_ids,
    }


def _message_dict(
    m: DirectMessage,
    me_id: int,
    story: Optional[Dict[str, Any]] = None,
    reactions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "receiver_id": m.receiver_id,
        "body": m.body,
        "kind": m.kind or MESSAGE_KIND_TEXT,
        "story": story,
        "reactions": reactions or [],
        "created_at": _iso(m.created_at),
        "read_at": _iso(m.read_at),
        "is_mine": m.sender_id == me_id,
    }


def _load_stories(db: Session, story_ids: Iterable[Optional[int]]) -> Dict[int, Dict[str, Any]]:
    """Small context card per story. Selects columns only - media_url can be a huge
    base64 blob and must never be pulled into a chat poll."""
    ids = {sid for sid in story_ids if sid}
    if not ids:
        return {}
    now = _utc_now_naive()
    rows = db.execute(
        select(
            Story.story_id,
            Story.media_type,
            Story.caption,
            Story.expires_at,
            Story.is_deleted,
        ).where(Story.story_id.in_(ids))
    ).all()
    cards: Dict[int, Dict[str, Any]] = {}
    for sid, media_type, caption, expires_at, is_deleted in rows:
        caption_text = (caption or "").strip()
        cards[sid] = {
            "story_id": sid,
            "media_type": media_type,
            "caption": caption_text[:80] or None,
            "available": (not is_deleted) and expires_at is not None and expires_at > now,
        }
    return cards


def _load_reactions(db: Session, message_ids: Iterable[int]) -> Dict[int, List[Dict[str, Any]]]:
    ids = list(message_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(MessageReaction.message_id, MessageReaction.user_id, MessageReaction.emoji)
        .where(MessageReaction.message_id.in_(ids))
        .order_by(MessageReaction.id.asc())
    ).all()
    out: Dict[int, List[Dict[str, Any]]] = {}
    for mid, uid, emoji in rows:
        out.setdefault(mid, []).append({"user_id": uid, "emoji": emoji})
    return out


def _serialize(db: Session, messages: List[DirectMessage], me_id: int) -> List[Dict[str, Any]]:
    stories = _load_stories(db, (m.story_id for m in messages))
    reactions = _load_reactions(db, (m.id for m in messages))
    return [
        _message_dict(
            m,
            me_id,
            story=stories.get(m.story_id) if m.story_id else None,
            reactions=reactions.get(m.id),
        )
        for m in messages
    ]


class MessageService:
    # ---------- helpers ----------
    @staticmethod
    def _following_ids(db: Session, me_id: int, candidate_ids: List[int]) -> Set[int]:
        if not candidate_ids:
            return set()
        rows = db.execute(
            select(Follow.following_id).where(
                Follow.follower_id == me_id, Follow.following_id.in_(candidate_ids)
            )
        ).scalars().all()
        return set(rows)

    @staticmethod
    def _get_partner(db: Session, me: User, other_id: int) -> User:
        if other_id == me.user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot message yourself")
        other = db.get(User, other_id)
        if other is None or not other.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return other

    # ---------- cheap poll target ----------
    @staticmethod
    def summary(db: Session, me: User) -> Dict[str, int]:
        latest = db.execute(
            select(func.max(DirectMessage.id)).where(
                or_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == me.user_id)
            )
        ).scalar()
        unread = db.execute(
            select(func.count(func.distinct(DirectMessage.sender_id))).where(
                DirectMessage.receiver_id == me.user_id, DirectMessage.read_at.is_(None)
            )
        ).scalar()
        return {"latest_message_id": int(latest or 0), "unread_conversations": int(unread or 0)}

    # ---------- inbox ----------
    @staticmethod
    def conversations(db: Session, me: User, limit: int = 100) -> List[Dict[str, Any]]:
        partner_id = case(
            (DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id),
            else_=DirectMessage.sender_id,
        )
        latest = (
            select(func.max(DirectMessage.id).label("mid"))
            .where(or_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == me.user_id))
            .group_by(partner_id)
            .subquery()
        )
        last_messages = db.execute(
            select(DirectMessage)
            .join(latest, DirectMessage.id == latest.c.mid)
            .order_by(DirectMessage.id.desc())
            .limit(limit)
        ).scalars().all()
        if not last_messages:
            return []

        unread_rows = db.execute(
            select(DirectMessage.sender_id, func.count(DirectMessage.id))
            .where(DirectMessage.receiver_id == me.user_id, DirectMessage.read_at.is_(None))
            .group_by(DirectMessage.sender_id)
        ).all()
        unread = {sender: count for sender, count in unread_rows}

        partner_ids = [
            m.receiver_id if m.sender_id == me.user_id else m.sender_id for m in last_messages
        ]
        users = {
            u.user_id: u
            for u in db.execute(select(User).where(User.user_id.in_(partner_ids))).scalars().all()
        }
        following = MessageService._following_ids(db, me.user_id, partner_ids)

        result: List[Dict[str, Any]] = []
        for m, pid in zip(last_messages, partner_ids):
            partner = users.get(pid)
            if partner is None or not partner.is_active:
                continue
            result.append(
                {
                    "partner": _user_card(partner, following),
                    "last_message": {
                        "id": m.id,
                        "body": m.body,
                        "kind": m.kind or MESSAGE_KIND_TEXT,
                        "created_at": _iso(m.created_at),
                        "is_mine": m.sender_id == me.user_id,
                        "read_at": _iso(m.read_at),
                    },
                    "unread_count": int(unread.get(pid, 0)),
                }
            )
        return result

    # ---------- thread ----------
    @staticmethod
    def thread(
        db: Session,
        me: User,
        other_id: int,
        after_id: Optional[int] = None,
        before_id: Optional[int] = None,
        limit: int = 40,
        sync_from_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """`sync_from_id` is for polling: the client passes the oldest message id it
        holds and gets back the current reactions for every message from there on, so
        reactions added or removed on older messages show up without a reload."""
        other = MessageService._get_partner(db, me, other_id)
        pair = or_(
            and_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == other_id),
            and_(DirectMessage.sender_id == other_id, DirectMessage.receiver_id == me.user_id),
        )

        has_more = False
        if after_id is not None:
            rows = db.execute(
                select(DirectMessage)
                .where(pair, DirectMessage.id > after_id)
                .order_by(DirectMessage.id.asc())
                .limit(200)
            ).scalars().all()
        else:
            q = select(DirectMessage).where(pair)
            if before_id is not None:
                q = q.where(DirectMessage.id < before_id)
            rows = db.execute(q.order_by(DirectMessage.id.desc()).limit(limit + 1)).scalars().all()
            has_more = len(rows) > limit
            rows = list(reversed(rows[:limit]))

        # Opening/polling the thread marks the other person's messages as seen.
        marked = db.execute(
            update(DirectMessage)
            .where(
                DirectMessage.sender_id == other_id,
                DirectMessage.receiver_id == me.user_id,
                DirectMessage.read_at.is_(None),
            )
            .values(read_at=_utc_now_naive())
        ).rowcount
        if marked:
            db.commit()
            for m in rows:  # reflect the update in what we return
                if m.sender_id == other_id and m.read_at is None:
                    db.refresh(m)

        last_read = db.execute(
            select(func.max(DirectMessage.id)).where(
                DirectMessage.sender_id == me.user_id,
                DirectMessage.receiver_id == other_id,
                DirectMessage.read_at.is_not(None),
            )
        ).scalar()

        partner_card = None
        if after_id is None and before_id is None:
            partner_card = _user_card(other, MessageService._following_ids(db, me.user_id, [other_id]))

        reactions_sync: Optional[Dict[int, List[Dict[str, Any]]]] = None
        if sync_from_id is not None:
            in_range = db.execute(
                select(DirectMessage.id).where(pair, DirectMessage.id >= sync_from_id)
            ).scalars().all()
            found = _load_reactions(db, in_range)
            # Every message in range gets an entry (possibly empty) so removals propagate.
            reactions_sync = {mid: found.get(mid, []) for mid in in_range}

        return {
            "partner": partner_card,
            "messages": _serialize(db, rows, me.user_id),
            "has_more": has_more,
            "last_read_by_other_id": int(last_read) if last_read else None,
            "reactions_sync": reactions_sync,
        }

    # ---------- send ----------
    @staticmethod
    def send(db: Session, me: User, other_id: int, body: str) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        msg = DirectMessage(sender_id=me.user_id, receiver_id=other_id, body=body)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return _message_dict(msg, me.user_id)

    # ---------- story replies / reactions arrive as messages ----------
    @staticmethod
    def send_story_message(
        db: Session,
        sender_id: int,
        receiver_id: int,
        story_id: int,
        kind: str,
        body: str,
    ) -> Optional[DirectMessage]:
        """Drop a story reply/reaction into the owner's inbox. Returns the new message,
        or None when nothing was sent (own story, inactive owner, or a reaction with the
        same emoji from this person on this story already exists)."""
        if kind not in (MESSAGE_KIND_STORY_REPLY, MESSAGE_KIND_STORY_REACTION):
            raise ValueError(f"Unsupported story message kind: {kind}")
        if sender_id == receiver_id:
            return None
        receiver = db.get(User, receiver_id)
        if receiver is None or not receiver.is_active:
            return None

        if kind == MESSAGE_KIND_STORY_REACTION:
            already = db.execute(
                select(DirectMessage.id)
                .where(
                    DirectMessage.sender_id == sender_id,
                    DirectMessage.receiver_id == receiver_id,
                    DirectMessage.story_id == story_id,
                    DirectMessage.kind == kind,
                    DirectMessage.body == body,
                )
                .limit(1)
            ).first()
            if already:
                return None

        msg = DirectMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            body=body[:2000],
            kind=kind,
            story_id=story_id,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    # ---------- reactions ----------
    @staticmethod
    def _get_reactable_message(db: Session, me: User, message_id: int) -> DirectMessage:
        msg = db.get(DirectMessage, message_id)
        # 404 (not 403) for messages outside the person's own chats, so ids can't be probed.
        if msg is None or me.user_id not in (msg.sender_id, msg.receiver_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
        return msg

    @staticmethod
    def _reaction_payload(db: Session, message_id: int) -> Dict[str, Any]:
        return {
            "message_id": message_id,
            "reactions": _load_reactions(db, [message_id]).get(message_id, []),
        }

    @staticmethod
    def react(db: Session, me: User, message_id: int, emoji: str) -> Dict[str, Any]:
        """Set my reaction on a message (sent or received), replacing any previous one."""
        MessageService._get_reactable_message(db, me, message_id)

        def _apply() -> None:
            existing = db.execute(
                select(MessageReaction).where(
                    MessageReaction.message_id == message_id,
                    MessageReaction.user_id == me.user_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(MessageReaction(message_id=message_id, user_id=me.user_id, emoji=emoji))
            elif existing.emoji != emoji:
                existing.emoji = emoji
            db.commit()

        try:
            _apply()
        except IntegrityError:
            # Two taps raced past the existence check; the unique key stopped the second.
            db.rollback()
            _apply()
        return MessageService._reaction_payload(db, message_id)

    @staticmethod
    def unreact(db: Session, me: User, message_id: int) -> Dict[str, Any]:
        MessageService._get_reactable_message(db, me, message_id)
        existing = db.execute(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == me.user_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            db.delete(existing)
            db.commit()
        return MessageService._reaction_payload(db, message_id)

    # ---------- people (See all / start new chat) ----------
    @staticmethod
    def search_people(
        db: Session, me: User, q: str = "", limit: int = 30, offset: int = 0
    ) -> List[Dict[str, Any]]:
        query = db.query(User).filter(User.user_id != me.user_id, User.is_active.is_(True))
        term = q.strip().lstrip("@")
        if term:
            like = f"%{_escape_like(term)}%"
            query = query.filter(
                or_(
                    User.username.ilike(like, escape="\\"),
                    User.first_name.ilike(like, escape="\\"),
                    User.last_name.ilike(like, escape="\\"),
                    func.concat(User.first_name, " ", User.last_name).ilike(like, escape="\\"),
                )
            )
        users = (
            query.order_by(User.first_name.asc(), User.user_id.asc()).offset(offset).limit(limit).all()
        )
        following = MessageService._following_ids(db, me.user_id, [u.user_id for u in users])
        return [_user_card(u, following) for u in users]