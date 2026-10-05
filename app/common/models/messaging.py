from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# What a DirectMessage represents. Plain chat is "text"; the story kinds are created
# automatically when someone replies to / reacts to a story, and link back via story_id.
# "call" is a log entry created by the calls WebSocket when a call ends - its `body`
# is a small JSON blob: {"media": "audio"|"video", "outcome": "...", "seconds": n}.
MESSAGE_KIND_TEXT = "text"
MESSAGE_KIND_STORY_REPLY = "story_reply"
MESSAGE_KIND_STORY_REACTION = "story_reaction"
MESSAGE_KIND_CALL = "call"


class DirectMessage(Base):
    """One 1:1 chat message. A "conversation" is just the pair (sender, receiver)."""

    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("ix_dm_sender_receiver_id", "sender_id", "receiver_id", "id"),
        Index("ix_dm_receiver_unread", "receiver_id", "read_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(20), default=MESSAGE_KIND_TEXT, server_default=MESSAGE_KIND_TEXT, nullable=False
    )
    # Set for story_reply / story_reaction messages. The story may expire or be deleted
    # later; SET NULL keeps the chat message and the API reports the story as unavailable.
    story_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stories.story_id", ondelete="SET NULL"), nullable=True
    )
    # Stored as naive UTC; the API adds a "Z" so browsers show the user's local time.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class MessageReaction(Base):
    """An emoji reaction to a direct message. One reaction per person per message:
    reacting again with a different emoji replaces the old one."""

    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_reactions_message_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("direct_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    emoji: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class ChatState(Base):
    """Per-viewer state for a 1:1 chat - Instagram-style "delete chat" and "mark as
    unread" without ever touching the other person's copy of the conversation.

    This is a brand-new table, so it's created automatically by
    Base.metadata.create_all() on startup - no ALTER TABLE migration needed.
    """

    __tablename__ = "chat_state"
    __table_args__ = (
        UniqueConstraint("user_id", "partner_id", name="uq_chat_state_user_partner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    # "Delete chat": hides every message with id <= this value, for user_id only.
    # The other person's inbox/thread is completely unaffected.
    cleared_before_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # "Mark as unread" from the 3-dot menu: forces this row to look unread again in
    # the inbox, without changing any message's real read_at (so the sender's "Seen"
    # status doesn't change - same behavior as Instagram). Cleared when the thread
    # is opened again.
    manually_unread: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class MessageRequestAccept(Base):
    """Instagram-style "message requests".

    Two people who follow each other chat directly. When someone who is NOT a mutual
    follow messages you, the chat lands in your Requests tab. Tapping Accept adds one
    row here (user_id = you, partner_id = them) and the chat moves to your main inbox.

    This is a brand-new table, so Base.metadata.create_all() creates it on startup -
    no ALTER TABLE migration needed.
    """

    __tablename__ = "message_request_accepts"
    __table_args__ = (
        UniqueConstraint("user_id", "partner_id", name="uq_message_request_accepts_user_partner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The person who accepted (the receiver of the request).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    # The person whose request was accepted (the sender).
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class PushSubscription(Base):
    """One browser/phone that agreed to receive message notifications for a user.

    Instagram-style notifications: when someone sends you a message, the server pushes
    a small notification to every device listed here, even if the website is closed.

    `endpoint` is a long private URL the browser's push service gave us; it is unique
    per browser. If a different person logs in on the same browser, the row simply
    moves to them (see PushService.subscribe).

    This is a brand-new table, so Base.metadata.create_all() creates it on startup -
    no ALTER TABLE migration needed.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
        Index("ix_push_subscriptions_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(750), nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)