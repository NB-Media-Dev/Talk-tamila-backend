from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship
from app.db.database import Base


class MusicTrack(Base):
    __tablename__ = "music_tracks"

    track_id = Column(BigInteger, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    artist = Column(String(255), nullable=False, index=True)
    album = Column(String(255), nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=False, default=30)
    audio_url = Column(Text, nullable=False)
    cover_url = Column(Text, nullable=True)
    genre = Column(String(100), nullable=True, index=True)
    language = Column(String(50), nullable=False, default="Tamil", index=True)
    is_trending = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    stories = relationship("Story", back_populates="music_track")
