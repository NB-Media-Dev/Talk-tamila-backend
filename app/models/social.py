from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class Story(Base):
    __tablename__ = "stories"

    story_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    media_url = Column(Text, nullable=False)
    media_type = Column(Enum("image", "video"), nullable=False, default="image")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    reply = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    audience = Column(String(50), nullable=False, default="public")

    # Song / Audio Track attachments (up to 1 minute max duration)
    music_id = Column(BigInteger, ForeignKey("music_tracks.track_id", ondelete="SET NULL"), nullable=True)
    music_title = Column(String(255), nullable=True)
    music_artist = Column(String(255), nullable=True)
    music_url = Column(Text, nullable=True)
    music_thumbnail = Column(Text, nullable=True)
    music_start_time = Column(Float, nullable=True, default=0.0)
    music_duration = Column(Float, nullable=True, default=60.0)

    user = relationship("User", back_populates="stories")
    music_track = relationship("MusicTrack", back_populates="stories")
    likes = relationship("StoryLike", back_populates="story", cascade="all, delete-orphan")
    replies = relationship("StoryReply", back_populates="story", cascade="all, delete-orphan")


class StoryLike(Base):
    __tablename__ = "story_likes"
    __table_args__ = (
        UniqueConstraint("story_id", "user_id", name="uq_story_likes_story_user"),
    )

    like_id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    story = relationship("Story", back_populates="likes")
    user = relationship("User")


class StoryReply(Base):
    __tablename__ = "story_replies"

    reply_id = Column(Integer, primary_key=True, autoincrement=True)
    story_id = Column(Integer, ForeignKey("stories.story_id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    story = relationship("Story", back_populates="replies")
    user = relationship("User")
