
"""Direct messaging: inbox, 1:1 threads, read receipts, reactions, unsend, delete
chat, mark read/unread, call logging, and people search."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.models.messaging import (
    MESSAGE_KIND_CALL,
    MESSAGE_KIND_STORY_REACTION,
    MESSAGE_KIND_STORY_REPLY,
    MESSAGE_KIND_TEXT,
    ChatState,
    DirectMessage,
    MessageReaction,
    MessageRequestAccept,
)
from app.common.models.moderation import ChatMute, UserBlock, UserReport
from app.common.models.social import Follow, Notification
from app.common.models.story import Story, StoryReply
from app.common.models.user import User


# How many messages someone can send to a person who has NOT accepted their request
# (Instagram allows 1). Change this number if you want to allow more.
MAX_REQUEST_MESSAGES = 1


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

    # ---------- message requests (Instagram-style) ----------
    @staticmethod
    def _request_partner_ids(db: Session, me_id: int, partner_ids: Iterable[int]) -> Set[int]:
        """Which of `partner_ids` are a *message request* from MY point of view.

        A chat is a normal chat for me when ANY of these is true:
          - we follow each other (mutual follow)
          - I accepted their request
          - I have sent them a message myself (replying counts as accepting)
        Otherwise everything they send me sits in my Requests tab.
        """
        ids = list({int(p) for p in partner_ids if p and p != me_id})
        if not ids:
            return set()

        i_follow = set(
            db.execute(
                select(Follow.following_id).where(
                    Follow.follower_id == me_id, Follow.following_id.in_(ids)
                )
            ).scalars().all()
        )
        follow_me = set(
            db.execute(
                select(Follow.follower_id).where(
                    Follow.following_id == me_id, Follow.follower_id.in_(ids)
                )
            ).scalars().all()
        )
        mutual = i_follow & follow_me

        accepted = set(
            db.execute(
                select(MessageRequestAccept.partner_id).where(
                    MessageRequestAccept.user_id == me_id,
                    MessageRequestAccept.partner_id.in_(ids),
                )
            ).scalars().all()
        )
        i_sent = set(
            db.execute(
                select(DirectMessage.receiver_id)
                .where(
                    DirectMessage.sender_id == me_id,
                    DirectMessage.receiver_id.in_(ids),
                    DirectMessage.kind != MESSAGE_KIND_CALL,
                )
                .distinct()
            ).scalars().all()
        )
        return {pid for pid in ids if pid not in mutual and pid not in accepted and pid not in i_sent}

    @staticmethod
    def request_state(db: Session, me_id: int, other_id: int) -> Dict[str, Any]:
        """Small block sent with every thread response so the chat screen knows whether
        to show the Accept / Delete / Block bar, or the "request sent" notice.

        is_request   - THEY are asking to message ME and I have not accepted yet.
        request_sent - I am messaging someone who has not accepted me yet.
        can_send     - False once I used up my allowed messages while waiting.
        """
        is_request = other_id in MessageService._request_partner_ids(db, me_id, [other_id])
        request_sent = me_id in MessageService._request_partner_ids(db, other_id, [me_id])
        can_send = True
        if request_sent:
            # Only count messages I can still see. If I used "Delete chat", those old
            # messages are hidden from me, so they must not lock me out of a chat that
            # now looks empty.
            my_state = MessageService._get_chat_state(db, me_id, other_id)
            cleared_before_id = my_state.cleared_before_id if my_state else 0
            sent = db.execute(
                select(func.count(DirectMessage.id)).where(
                    DirectMessage.sender_id == me_id,
                    DirectMessage.receiver_id == other_id,
                    DirectMessage.kind != MESSAGE_KIND_CALL,
                    DirectMessage.id > cleared_before_id,
                )
            ).scalar() or 0
            can_send = sent < MAX_REQUEST_MESSAGES
        return {"is_request": is_request, "request_sent": request_sent, "can_send": can_send}

    @staticmethod
    def accept_request(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        """Accept a message request: the chat moves from Requests to the main inbox."""
        MessageService._get_partner(db, me, other_id)
        exists = db.execute(
            select(MessageRequestAccept.id).where(
                MessageRequestAccept.user_id == me.user_id,
                MessageRequestAccept.partner_id == other_id,
            )
        ).first()
        if exists is None:
            db.add(MessageRequestAccept(user_id=me.user_id, partner_id=other_id))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # accepted twice at the same moment - already accepted
        return {"success": True, "accepted": True}

    @staticmethod
    def _get_partner(db: Session, me: User, other_id: int) -> User:
        if other_id == me.user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot message yourself")
        other = db.get(User, other_id)
        if other is None or not other.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        return other

    # ---------- block / mute helpers ----------
    @staticmethod
    def _block_state(db: Session, me_id: int, other_id: int) -> Dict[str, bool]:
        """blocked_by_me: I blocked them. blocked_me: they blocked me."""
        rows = db.execute(
            select(UserBlock.blocker_id).where(
                or_(
                    and_(UserBlock.blocker_id == me_id, UserBlock.blocked_id == other_id),
                    and_(UserBlock.blocker_id == other_id, UserBlock.blocked_id == me_id),
                )
            )
        ).scalars().all()
        return {"blocked_by_me": me_id in rows, "blocked_me": other_id in rows}

    @staticmethod
    def is_blocked_between(db: Session, a_id: int, b_id: int) -> bool:
        state = MessageService._block_state(db, a_id, b_id)
        return state["blocked_by_me"] or state["blocked_me"]

    @staticmethod
    def _is_muted(db: Session, me_id: int, other_id: int) -> bool:
        return (
            db.execute(
                select(ChatMute.id).where(
                    ChatMute.user_id == me_id, ChatMute.partner_id == other_id
                )
            ).first()
            is not None
        )

    # ---------- per-viewer chat state (delete chat / mark unread) ----------
    @staticmethod
    def _chat_state_map(db: Session, me_id: int, partner_ids: List[int]) -> Dict[int, ChatState]:
        if not partner_ids:
            return {}
        rows = db.execute(
            select(ChatState).where(
                ChatState.user_id == me_id, ChatState.partner_id.in_(partner_ids)
            )
        ).scalars().all()
        return {r.partner_id: r for r in rows}

    @staticmethod
    def _get_chat_state(db: Session, me_id: int, partner_id: int) -> Optional[ChatState]:
        return db.execute(
            select(ChatState).where(
                ChatState.user_id == me_id, ChatState.partner_id == partner_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def _get_or_create_chat_state(db: Session, me_id: int, partner_id: int) -> ChatState:
        state = MessageService._get_chat_state(db, me_id, partner_id)
        if state is None:
            state = ChatState(user_id=me_id, partner_id=partner_id, cleared_before_id=0, manually_unread=False)
            db.add(state)
            db.commit()
            db.refresh(state)
        return state

    # ---------- cheap poll target ----------
    @staticmethod
    def summary(db: Session, me: User) -> Dict[str, int]:
        latest = db.execute(
            select(func.max(DirectMessage.id)).where(
                or_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == me.user_id)
            )
        ).scalar()
        muted_ids = select(ChatMute.partner_id).where(ChatMute.user_id == me.user_id)
        unread_rows = db.execute(
            select(DirectMessage.sender_id, DirectMessage.id).where(
                DirectMessage.receiver_id == me.user_id,
                DirectMessage.read_at.is_(None),
                DirectMessage.sender_id.not_in(muted_ids),
            )
        ).all()

        # Ignore anything hidden by "delete chat".
        senders = list({sid for sid, _ in unread_rows})
        states = MessageService._chat_state_map(db, me.user_id, senders)
        unread_senders = {
            sid
            for sid, mid in unread_rows
            if mid > (states[sid].cleared_before_id if sid in states else 0)
        }

        # Requests are counted separately so they don't inflate the navbar badge.
        request_ids = MessageService._request_partner_ids(db, me.user_id, unread_senders)
        return {
            "latest_message_id": int(latest or 0),
            "unread_conversations": len(unread_senders - request_ids),
            "request_unread": len(request_ids),
        }

    # ---------- inbox ----------
    @staticmethod
    def conversations(db: Session, me: User, limit: int = 100) -> List[Dict[str, Any]]:
        partner_id_expr = case(
            (DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id),
            else_=DirectMessage.sender_id,
        )
        latest = (
            select(func.max(DirectMessage.id).label("mid"))
            .where(or_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == me.user_id))
            .group_by(partner_id_expr)
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

        partner_ids = [
            m.receiver_id if m.sender_id == me.user_id else m.sender_id for m in last_messages
        ]
        chat_states = MessageService._chat_state_map(db, me.user_id, partner_ids)

        # Count unread messages per partner, ignoring anything hidden by "delete chat".
        unread_id_rows = db.execute(
            select(DirectMessage.sender_id, DirectMessage.id).where(
                DirectMessage.receiver_id == me.user_id, DirectMessage.read_at.is_(None)
            )
        ).all()
        unread_counts: Dict[int, int] = {}
        for sender_id, mid in unread_id_rows:
            threshold = chat_states[sender_id].cleared_before_id if sender_id in chat_states else 0
            if mid > threshold:
                unread_counts[sender_id] = unread_counts.get(sender_id, 0) + 1

        users = {
            u.user_id: u
            for u in db.execute(select(User).where(User.user_id.in_(partner_ids))).scalars().all()
        }
        following = MessageService._following_ids(db, me.user_id, partner_ids)
        request_ids = MessageService._request_partner_ids(db, me.user_id, partner_ids)

        result: List[Dict[str, Any]] = []
        for m, pid in zip(last_messages, partner_ids):
            partner = users.get(pid)
            if partner is None or not partner.is_active:
                continue

            state = chat_states.get(pid)
            cleared_before_id = state.cleared_before_id if state else 0
            if m.id <= cleared_before_id:
                continue  # this conversation was deleted-for-me and nothing new has arrived since

            unread_count = unread_counts.get(pid, 0)
            manually_unread = bool(state.manually_unread) if state else False

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
                    "unread_count": unread_count,
                    "is_unread": unread_count > 0 or manually_unread,
                    # True = not a mutual follow and not accepted yet -> shown in Requests.
                    "is_request": pid in request_ids,
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

        # "Delete chat" only hides history for the person who deleted it.
        state = MessageService._get_chat_state(db, me.user_id, other_id)
        cleared_before_id = state.cleared_before_id if state else 0
        if cleared_before_id:
            pair = and_(pair, DirectMessage.id > cleared_before_id)

        # Opening the full thread (not a "load older"/poll request) clears any
        # "mark as unread" flag, same as Instagram.
        if after_id is None and before_id is None and state is not None and state.manually_unread:
            state.manually_unread = False
            db.commit()

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

        request = MessageService.request_state(db, me.user_id, other_id)

        # Opening/polling the thread marks the other person's messages as seen - except
        # for a pending request: like Instagram, they can't tell you looked until you accept.
        marked = 0
        if not request["is_request"]:
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
            partner_card.update(MessageService._block_state(db, me.user_id, other_id))
            partner_card["muted"] = MessageService._is_muted(db, me.user_id, other_id)

        reactions_sync: Optional[Dict[int, List[Dict[str, Any]]]] = None
        existing_ids: Optional[List[int]] = None
        if sync_from_id is not None:
            in_range = db.execute(
                select(DirectMessage.id).where(pair, DirectMessage.id >= sync_from_id)
            ).scalars().all()
            # Lets the client drop messages that were unsent since its last poll.
            existing_ids = [int(mid) for mid in in_range]
            found = _load_reactions(db, in_range)
            # Every message in range gets an entry (possibly empty) so removals propagate.
            reactions_sync = {mid: found.get(mid, []) for mid in in_range}

        return {
            "partner": partner_card,
            "messages": _serialize(db, rows, me.user_id),
            "has_more": has_more,
            "last_read_by_other_id": int(last_read) if last_read else None,
            "reactions_sync": reactions_sync,
            "existing_ids": existing_ids,
            "request": request,
        }

    # ---------- send ----------
    @staticmethod
    def send(db: Session, me: User, other_id: int, body: str) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        state = MessageService._block_state(db, me.user_id, other_id)
        if state["blocked_by_me"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You blocked this user. Unblock them to send a message.")
        if state["blocked_me"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't send messages to this user.")

        # Message requests: if they don't follow me back (and haven't accepted me), my
        # message goes to THEIR Requests tab, and I only get a few until they accept.
        req = MessageService.request_state(db, me.user_id, other_id)
        if req["request_sent"] and not req["can_send"]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Your message request is waiting. You can send more once they accept it.",
            )

        msg = DirectMessage(sender_id=me.user_id, receiver_id=other_id, body=body)
        db.add(msg)
        db.commit()
        db.refresh(msg)

        # Create a notification so the receiver sees it in the bell panel.
        try:
            snippet = (body or "").strip()[:80]
            sender_name = me.username or me.full_name or f"User {me.user_id}"
            notif = Notification(
                user_id=other_id,
                type="new_message",
                message=f"{sender_name} sent you a message: {snippet}",
                reference_id=msg.id,
                is_read=False,
                created_at=_utc_now_naive(),
            )
            db.add(notif)
            db.commit()
        except Exception:
            db.rollback()  # notification failure must never break the message

        return _message_dict(msg, me.user_id)

    # ---------- unsend ----------
    @staticmethod
    def unsend(db: Session, me: User, message_id: int) -> Dict[str, Any]:
        """Delete a message I sent, for both people (Instagram-style Unsend)."""
        msg = db.get(DirectMessage, message_id)
        # 404 (not 403) for messages outside my own chats, so ids can't be probed.
        if msg is None or me.user_id not in (msg.sender_id, msg.receiver_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
        if msg.sender_id != me.user_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only unsend your own messages")

        # Reactions are removed explicitly so this also works if the DB foreign key
        # was created without ON DELETE CASCADE.
        db.execute(delete(MessageReaction).where(MessageReaction.message_id == message_id))

        # Delete any notifications tied directly to this message
        db.execute(
            delete(Notification).where(
                Notification.reference_id == message_id,
                Notification.type.in_(["new_message", "story_reply", "story_react", "message_react"])
            )
        )

        # If this message was a story reply or story reaction, also clean up story-level notifications
        if msg.story_id:
            username = me.username or ""
            if username:
                db.execute(
                    delete(Notification).where(
                        Notification.user_id == msg.receiver_id,
                        Notification.reference_id == msg.story_id,
                        Notification.type.in_(["story_reply", "story_react"]),
                        Notification.message.like(f"{username}%")
                    )
                )
            if msg.kind == MESSAGE_KIND_STORY_REPLY:
                db.execute(
                    delete(StoryReply).where(
                        StoryReply.story_id == msg.story_id,
                        StoryReply.user_id == me.user_id,
                        StoryReply.text == msg.body
                    )
                )

        db.delete(msg)
        db.commit()
        return {"success": True, "message_id": message_id}

    # ---------- delete chat (for me only) ----------
    @staticmethod
    def delete_chat(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        """Instagram-style "Delete chat": clears the conversation out of my inbox
        and thread history. The other person's copy is completely untouched, and if
        they (or I) send a new message later, the chat simply reappears with just
        the messages from that point on."""
        MessageService._get_partner(db, me, other_id)
        pair = or_(
            and_(DirectMessage.sender_id == me.user_id, DirectMessage.receiver_id == other_id),
            and_(DirectMessage.sender_id == other_id, DirectMessage.receiver_id == me.user_id),
        )
        latest_id = db.execute(select(func.max(DirectMessage.id)).where(pair)).scalar() or 0

        state = MessageService._get_or_create_chat_state(db, me.user_id, other_id)
        state.cleared_before_id = max(state.cleared_before_id, latest_id)
        state.manually_unread = False
        db.commit()
        return {"success": True}

    # ---------- block / unblock / mute / report (chat header 3-dot menu) ----------
    @staticmethod
    def block(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        exists = db.execute(
            select(UserBlock.id).where(
                UserBlock.blocker_id == me.user_id, UserBlock.blocked_id == other_id
            )
        ).first()
        if exists is None:
            db.add(UserBlock(blocker_id=me.user_id, blocked_id=other_id))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # blocked twice at the same moment - already blocked
        return {"success": True, "blocked": True}

    @staticmethod
    def unblock(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        db.execute(
            delete(UserBlock).where(
                UserBlock.blocker_id == me.user_id, UserBlock.blocked_id == other_id
            )
        )
        db.commit()
        return {"success": True, "blocked": False}

    @staticmethod
    def mute(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        if not MessageService._is_muted(db, me.user_id, other_id):
            db.add(ChatMute(user_id=me.user_id, partner_id=other_id))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        return {"success": True, "muted": True}

    @staticmethod
    def unmute(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        db.execute(
            delete(ChatMute).where(ChatMute.user_id == me.user_id, ChatMute.partner_id == other_id)
        )
        db.commit()
        return {"success": True, "muted": False}

    @staticmethod
    def report(db: Session, me: User, other_id: int, reason: str) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        db.add(UserReport(reporter_id=me.user_id, reported_id=other_id, reason=(reason or "").strip()[:500]))
        db.commit()
        return {"success": True}

    # ---------- mark read / unread (3-dot menu on the inbox row) ----------
    @staticmethod
    def mark_read(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        MessageService._get_partner(db, me, other_id)
        db.execute(
            update(DirectMessage)
            .where(
                DirectMessage.sender_id == other_id,
                DirectMessage.receiver_id == me.user_id,
                DirectMessage.read_at.is_(None),
            )
            .values(read_at=_utc_now_naive())
        )
        state = MessageService._get_or_create_chat_state(db, me.user_id, other_id)
        state.manually_unread = False
        db.commit()
        return {"success": True}

    @staticmethod
    def mark_unread(db: Session, me: User, other_id: int) -> Dict[str, Any]:
        """Flags the inbox row as unread without touching real read receipts, so the
        other person's "Seen" status is not affected - matches Instagram's behavior."""
        MessageService._get_partner(db, me, other_id)
        state = MessageService._get_or_create_chat_state(db, me.user_id, other_id)
        state.manually_unread = True
        db.commit()
        return {"success": True}

    # ---------- call log entries (written by the calls WebSocket) ----------
    @staticmethod
    def log_call(
        db: Session, caller_id: int, callee_id: int, media: str, outcome: str, seconds: int
    ) -> Dict[str, Any]:
        """Drop a call record into the chat as a message, same as Instagram's call
        bubbles ("Missed video call", "Call ended · 3:12", etc)."""
        body = json.dumps({"media": media, "outcome": outcome, "seconds": seconds})
        msg = DirectMessage(
            sender_id=caller_id, receiver_id=callee_id, body=body, kind=MESSAGE_KIND_CALL
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return _message_dict(msg, caller_id)

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