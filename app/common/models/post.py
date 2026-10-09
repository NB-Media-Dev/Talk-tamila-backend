from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
# Archived posts are hidden from the profile and feed. Only the owner can see them.
STATUS_ARCHIVED = "archived"

MAX_PINNED_POSTS = 3


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

    # published | scheduled | archived. Scheduled posts are invisible to everyone but admins.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=STATUS_PUBLISHED, server_default=STATUS_PUBLISHED
    )
    # When a scheduled post should go live (naive UTC). Kept after publishing for history.
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When the post became visible (naive UTC). NULL while it is still scheduled.
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    # Kept so the notification service query (Post.is_deleted == False) keeps working.
    # Posts are removed for real when deleted, so this stays False.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    # Owner controls (Instagram style)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    pinned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    comments_disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    hide_like_count: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # Set when the caption was changed after posting (shows "Edited").
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Song attached to the post (same fields the stories use)
    music_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    music_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    music_artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    music_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    music_thumbnail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    music_start_time: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    music_duration: Mapped[float] = mapped_column(
        Float, nullable=False, default=30.0, server_default="30"
    )

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


class PostLike(Base):
    __tablename__ = "post_likes"

    like_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_likes_post_user"),
        Index("idx_post_likes_post", "post_id", "like_id"),
        Index("idx_post_likes_user", "user_id"),
    )


class PostComment(Base):
    __tablename__ = "post_comments"

    comment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    # NULL for a top-level comment. Replies always point at the top-level comment.
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("post_comments.comment_id", ondelete="CASCADE"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_post_comments_post", "post_id", "parent_id", "comment_id"),
        Index("idx_post_comments_user", "user_id", "created_at"),
    )


class PostCommentLike(Base):
    __tablename__ = "post_comment_likes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("post_comments.comment_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_post_comment_likes_pair"),
        Index("idx_pcl_comment", "comment_id"),
    )


class PostSave(Base):
    __tablename__ = "post_saves"

    save_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_saves_post_user"),
        Index("idx_post_saves_user", "user_id", "save_id"),
    )


class PostShare(Base):
    __tablename__ = "post_shares"

    share_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    # link | dm | other
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="link")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (Index("idx_post_shares_post", "post_id"),)


class PostView(Base):
    """One row per person who saw the post. Powers the reach number in insights."""

    __tablename__ = "post_views"

    view_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_views_post_user"),
        Index("idx_post_views_post", "post_id"),
    )


class PostReport(Base):
    __tablename__ = "post_reports"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.post_id", ondelete="CASCADE"), nullable=False
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("post_id", "reporter_id", name="uq_post_reports_pair"),
        Index("idx_post_reports_post", "post_id"),
    )