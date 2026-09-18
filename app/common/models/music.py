from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MusicTrack(Base):
    __tablename__ = "music_tracks"

    track_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    album: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    audio_url: Mapped[str] = mapped_column(String(500), nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(50), default="Tamil")
    language: Mapped[str | None] = mapped_column(String(50), default="Tamil")
    is_trending: Mapped[bool] = mapped_column(Boolean, default=True)
