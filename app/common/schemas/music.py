from typing import Optional
from pydantic import BaseModel


class MusicTrackResponse(BaseModel):
    track_id: int
    title: str
    artist: str
    album: Optional[str] = None
    duration_seconds: float = 60.0
    audio_url: str
    cover_url: Optional[str] = None
    genre: Optional[str] = "Tamil"
    language: Optional[str] = "Tamil"
    is_trending: bool = True
