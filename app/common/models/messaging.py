from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


MESSAGE_KIND_TEXT = "text"
MESSAGE_KIND_STORY_REPLY = "story_reply"
MESSAGE_KIND_STORY_REACTION = "story_reaction"
MESSAGE_KIND_CALL = "call"


class DirectMessage(Base):

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

    story_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stories.story_id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class MessageReaction(Base):

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

    cleared_before_id: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    manually_unread: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class MessageRequestAccept(Base):

    __tablename__ = "message_request_accepts"
    __table_args__ = (
        UniqueConstraint("user_id", "partner_id", name="uq_message_request_accepts_user_partner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
   
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class PushSubscription(Base):

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