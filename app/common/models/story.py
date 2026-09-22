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
    UniqueConstraint,
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
        index=True,
    )
    media_url: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=False)
    media_type: Mapped[str] = mapped_column(
        String(20),
        default="image",
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    audience: Mapped[str] = mapped_column(String(50), default="PUBLIC", nullable=False, index=True)
    music_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    music_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_artist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_thumbnail: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_start_time: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)
    music_duration: Mapped[float | None] = mapped_column(Float, default=60.0, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    def author_id(self) -> int:
        return self.user_id

    @author_id.setter
    def author_id(self, value: int) -> None:
        self.user_id = value

    @property
    def content(self) -> Optional[str]:
        return self.caption

    @content.setter
    def content(self, value: Optional[str]) -> None:
        self.caption = value

    @property
    def has_active_story(self) -> bool:
        return not self.is_deleted



class StoryView(Base):
    __tablename__ = "story_views"
    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_views_story_user"),
    )

    view_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="views")
    user: Mapped["User"] = relationship("User")

    @property
    def id(self) -> int:
        return self.view_id

    @property
    def slide_id(self) -> int:
        return self.story_id

    @slide_id.setter
    def slide_id(self, value: int) -> None:
        self.story_id = value

    @property
    def viewer_id(self) -> int:
        return self.user_id

    @viewer_id.setter
    def viewer_id(self, value: int) -> None:
        self.user_id = value



class StoryLike(Base):
    __tablename__ = "story_likes"
    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_likes_story_user"),
    )

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
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_saves_story_user"),
    )

    save_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    story: Mapped["Story"] = relationship("Story", back_populates="saves")
    user: Mapped["User"] = relationship("User")

