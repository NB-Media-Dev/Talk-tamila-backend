
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# What a DirectMessage represents. Plain chat is "text"; the other two are created
# automatically when someone replies to / reacts to a story, and link back via story_id.
MESSAGE_KIND_TEXT = "text"
MESSAGE_KIND_STORY_REPLY = "story_reply"
MESSAGE_KIND_STORY_REACTION = "story_reaction"


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