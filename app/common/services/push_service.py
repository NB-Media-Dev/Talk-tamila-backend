import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    from pywebpush import WebPushException, webpush
except ImportError:
    webpush = None

    class WebPushException(Exception):
        pass

try:
    from py_vapid import Vapid
except ImportError:
    Vapid = None

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.models.messaging import (
    MESSAGE_KIND_CALL,
    MESSAGE_KIND_STORY_REACTION,
    MESSAGE_KIND_STORY_REPLY,
    DirectMessage,
    PushSubscription,
)
from app.common.models.moderation import ChatMute
from app.common.models.user import User
from app.common.services.message_service import MessageService
from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

_ALLOWED_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com")
_ALLOWED_SUFFIXES = (".push.apple.com", ".notify.windows.com", ".push.services.mozilla.com")

_BODY_LIMIT = 140

def is_configured() -> bool:
    return bool(webpush is not None and Vapid is not None and settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)

def is_allowed_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return host in _ALLOWED_HOSTS or host.endswith(_ALLOWED_SUFFIXES)

def _vapid_subject() -> str:
    if settings.VAPID_SUBJECT:
        return settings.VAPID_SUBJECT
    if settings.SMTP_FROM_EMAIL:
        return f"mailto:{settings.SMTP_FROM_EMAIL}"
    return "mailto:admin@talktamila.com"

def _messages_url(role: Optional[str], sender_id: int) -> str:
    """Same folders the website uses: each role has its own messages page."""
    role = str(getattr(role, "value", role) or "").lower()
    if role == "influencer":
        base = "/influencer/messages"
    elif role == "freelancer":
        base = "/freelancer/messages"
    else:
        base = "/admin/messages"
    return f"{base}?user={sender_id}"

def _preview(kind: str, body: str) -> str:
    text = " ".join((body or "").split())
    if kind == MESSAGE_KIND_STORY_REPLY:
        return ("Replied to your story: " + text)[:_BODY_LIMIT]
    if kind == MESSAGE_KIND_STORY_REACTION:
        return f"Reacted {text} to your story"[:_BODY_LIMIT]
    if len(text) > _BODY_LIMIT:
        return text[: _BODY_LIMIT - 1] + "…"
    return text

class PushService:
    @staticmethod
    def subscribe(db: Session, user: User, endpoint: str, p256dh: str, auth: str) -> None:
        """Remember this device for this user. If the same browser was used by someone
        else before, it now belongs to the person who is logged in."""
        existing = db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        ).scalar_one_or_none()
        if existing is not None:
            existing.user_id = user.user_id
            existing.p256dh = p256dh
            existing.auth = auth
            db.commit()
            return
        db.add(PushSubscription(user_id=user.user_id, endpoint=endpoint, p256dh=p256dh, auth=auth))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            row = db.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            ).scalar_one_or_none()
            if row is not None:
                row.user_id = user.user_id
                row.p256dh = p256dh
                row.auth = auth
                db.commit()

    @staticmethod
    def unsubscribe(db: Session, endpoint: str) -> bool:
        """Stop notifications for one device (used on logout)."""
        result = db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
        db.commit()
        return bool(result.rowcount)

    @staticmethod
    def notify_new_message(message_id: int, exclude_endpoint: Optional[str] = None) -> None:
        """Runs in the background right after a message was saved. Never raises: a
        notification problem must never break sending a chat message.

        `exclude_endpoint` is the sender's own browser. It is never notified about the
        sender's own message, even if that browser is registered under the receiver."""
        if not is_configured():
            logger.warning(
                "Push skipped for message %s: VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY are not set on this server",
                message_id,
            )
            return
        db = SessionLocal()
        try:
            PushService._notify(db, message_id, exclude_endpoint)
        except Exception:
            logger.exception("Could not send push notification for message %s", message_id)
        finally:
            db.close()

    @staticmethod
    def _notify(db: Session, message_id: int, exclude_endpoint: Optional[str] = None) -> None:
        msg = db.get(DirectMessage, message_id)
        if msg is None or msg.kind == MESSAGE_KIND_CALL:
            logger.warning("Push skipped for message %s: message missing or is a call entry", message_id)
            return
        sender = db.get(User, msg.sender_id)
        receiver = db.get(User, msg.receiver_id)
        if sender is None or receiver is None or not receiver.is_active:
            logger.warning("Push skipped for message %s: sender/receiver missing or receiver inactive", message_id)
            return

        if MessageService.is_blocked_between(db, sender.user_id, receiver.user_id):
            logger.warning("Push skipped for message %s: users are blocked", message_id)
            return
        muted = db.execute(
            select(ChatMute.id).where(
                ChatMute.user_id == receiver.user_id, ChatMute.partner_id == sender.user_id
            )
        ).first()
        if muted is not None:
            logger.warning("Push skipped for message %s: receiver muted this chat", message_id)
            return
        if sender.user_id in MessageService._request_partner_ids(
            db, receiver.user_id, [sender.user_id]
        ):
            logger.warning(
                "Push skipped for message %s: it is a message REQUEST for user %s "
                "(no mutual follow, not accepted, and they never replied)",
                message_id,
                receiver.user_id,
            )
            return

        subs = db.execute(
            select(PushSubscription).where(PushSubscription.user_id == receiver.user_id)
        ).scalars().all()
        if exclude_endpoint:
            before = len(subs)
            subs = [s for s in subs if s.endpoint != exclude_endpoint]
            if len(subs) < before:
                logger.warning(
                    "Push for message %s: left out the sender's own browser (it was registered under the receiver)",
                    message_id,
                )
        if not subs:
            logger.warning(
                "Push skipped for message %s: user %s has no saved browser subscription "
                "(notifications were never turned on for this account)",
                message_id,
                receiver.user_id,
            )
            return

        payload: Dict[str, Any] = {
            "title": sender.full_name or f"@{sender.username}",
            "body": _preview(msg.kind, msg.body),
            "url": _messages_url(receiver.role, sender.user_id),
            "tag": f"dm-{sender.user_id}",
            "sender_id": sender.user_id,
            "message_id": msg.id,
        }
        data = json.dumps(payload, ensure_ascii=False)
        vapid = Vapid.from_string(private_key=settings.VAPID_PRIVATE_KEY)

        dead_ids = []
        sent = 0
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=data,
                    vapid_private_key=vapid,
                    vapid_claims={"sub": _vapid_subject()},
                    ttl=24 * 60 * 60,
                    timeout=10,
                )
                sent += 1
            except WebPushException as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code in (404, 410):
                    dead_ids.append(sub.id)
                else:
                    logger.warning("Push to subscription %s failed: %s", sub.id, exc)
            except Exception:
                logger.exception("Push to subscription %s crashed", sub.id)

        logger.warning(
            "Push for message %s: sent to %s of %s device(s), %s expired",
            message_id,
            sent,
            len(subs),
            len(dead_ids),
        )

        if dead_ids:
            db.execute(delete(PushSubscription).where(PushSubscription.id.in_(dead_ids)))
            db.commit()