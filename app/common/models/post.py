from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.common.models.user import User

STATUS_PUBLISHED = "published"
STATUS_SCHEDULED = "scheduled"


def _utc_now() -> datetime:
    """Current UTC time as a naive datetime (the database stores naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    # text | image | video | gif | poll
    post_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")
    # Body text, image/video caption, or the poll question.
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    media_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    media_mime: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    media_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    media_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary().with_variant(LONGBLOB(), "mysql"), nullable=True, deferred=True
    )

    gif_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # published | scheduled. Scheduled posts are invisible to everyone but admins.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PUBLISHED, server_default=STATUS_PUBLISHED
    )
    # When a scheduled post should go live (naive UTC). Kept after publishing for history.
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When the post became visible (naive UTC). NULL while it is still scheduled.
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    owner: Mapped["User"] = relationship("User", back_populates="posts", foreign_keys=[user_id])
    poll_options: Mapped[list["PostPollOption"]] = relationship(
        "PostPollOption",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostPollOption.position",
    )

    __table_args__ = (
        Index("idx_posts_user_id", "user_id"),
        Index("idx_posts_created_at", "created_at"),
        Index("idx_posts_status_scheduled", "status", "scheduled_at"),
        Index("idx_posts_published_at", "published_at", "post_id"),
    )

    @property
    def id(self) -> int:
        return self.post_id

    @property
    def author_id(self) -> int:
        return self.user_id


class PostPollOption(Base):
    __tablename__ = "post_poll_options"

    option_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    post: Mapped["Post"] = relationship("Post", back_populates="poll_options")

    __table_args__ = (Index("idx_ppo_post_id", "post_id"),)


class PostPollVote(Base):
    __tablename__ = "post_poll_votes"

    vote_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    option_id: Mapped[int] = mapped_column(
        ForeignKey("post_poll_options.option_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_poll_votes_post_user"),
        Index("idx_ppv_option_id", "option_id"),
    )