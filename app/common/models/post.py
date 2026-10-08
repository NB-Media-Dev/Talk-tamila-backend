from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

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
        index=True,
    )
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), default="image", nullable=False) 
    media_url: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    aspect_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    platforms: Mapped[str | None] = mapped_column(Text, nullable=True) 
    tags: Mapped[str | None] = mapped_column(Text, nullable=True) 
    poll_data: Mapped[str | None] = mapped_column(Text, nullable=True) 
    audience: Mapped[str] = mapped_column(String(50), default="PUBLIC", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="published", nullable=False)  # published, scheduled, draft, archived
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    views_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    likes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # published | scheduled. Scheduled posts are invisible to everyone but admins.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PUBLISHED, server_default=STATUS_PUBLISHED
    )
    # When a scheduled post should go live (naive UTC). Kept after publishing for history.
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When the post became visible (naive UTC). NULL while it is still scheduled.
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    @property
    def id(self) -> int:
        return self.post_id

    @property
    def author_id(self) -> int:
        return self.user_id


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (
        Index("idx_posts_user_id", "user_id"),
        Index("idx_posts_created_at", "created_at"),
        Index("idx_posts_status_scheduled", "status", "scheduled_at"),
        Index("idx_posts_published_at", "published_at", "post_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    post: Mapped["Post"] = relationship("Post", back_populates="likes")
    user: Mapped["User"] = relationship("User")


class PostComment(Base):
    __tablename__ = "post_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=False)
    parent_comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("post_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    post: Mapped["Post"] = relationship("Post", back_populates="comments")
    user: Mapped["User"] = relationship("User")


class PostShare(Base):
    __tablename__ = "post_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    post: Mapped["Post"] = relationship("Post", back_populates="shares")
    user: Mapped["User"] = relationship("User")


class PostSave(Base):
    __tablename__ = "post_saves"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_poll_votes_post_user"),
        Index("idx_ppv_option_id", "option_id"),
    )