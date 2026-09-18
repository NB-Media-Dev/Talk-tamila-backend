from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Story(Base):
    __tablename__ = "stories"

    story_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    media_url: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=False)
    media_type: Mapped[str] = mapped_column(
        Enum("image", "video", native_enum=False, length=10),
        default="image",
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str | None] = mapped_column(String(50), default="public", nullable=True)
    music_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    music_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_thumbnail: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_start_time: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)
    music_duration: Mapped[float | None] = mapped_column(Float, default=60.0, nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="stories")
    views: Mapped[list["StoryView"]] = relationship("StoryView", back_populates="story", cascade="all, delete-orphan")
    likes: Mapped[list["StoryLike"]] = relationship("StoryLike", back_populates="story", cascade="all, delete-orphan")
    replies: Mapped[list["StoryReply"]] = relationship("StoryReply", back_populates="story", cascade="all, delete-orphan")
    shares: Mapped[list["StoryShare"]] = relationship("StoryShare", back_populates="story", cascade="all, delete-orphan")
    saves: Mapped[list["StorySave"]] = relationship("StorySave", back_populates="story", cascade="all, delete-orphan")

    @property
    def id(self) -> int:
        return self.story_id

    @property
    def has_active_story(self) -> bool:
        return True


class StoryView(Base):
    __tablename__ = "story_views"

    view_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="views")
    user: Mapped["User"] = relationship("User")


class StoryLike(Base):
    __tablename__ = "story_likes"

    story_likes_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    liked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="likes")
    user: Mapped["User"] = relationship("User")


class StoryReply(Base):
    __tablename__ = "story_replies"

    reply_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="replies")
    user: Mapped["User"] = relationship("User")


class StoryShare(Base):
    __tablename__ = "story_shares"

    share_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), default="copy_link", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="shares")
    user: Mapped["User"] = relationship("User")


class StoryReport(Base):
    __tablename__ = "story_reports"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StoryMute(Base):
    __tablename__ = "story_mutes"

    mute_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    muted_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StorySave(Base):
    __tablename__ = "story_saves"

    save_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="saves")
    user: Mapped["User"] = relationship("User")

