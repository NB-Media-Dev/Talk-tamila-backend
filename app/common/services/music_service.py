from typing import List
from app.common.schemas.music import MusicTrackResponse

TAMIL_MUSIC_PRESETS = [
    {
        "track_id": 1,
        "title": "Hukum - Thalaivar Alappara",
        "artist": "Anirudh Ravichander",
        "album": "Jailer",
        "duration_seconds": 60.0,
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "cover_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=300",
        "genre": "Mass",
        "language": "Tamil",
        "is_trending": True,
    },
    {
        "track_id": 2,
        "title": "Naa Ready",
        "artist": "Thalapathy Vijay, Anirudh",
        "album": "Leo",
        "duration_seconds": 60.0,
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "cover_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=300",
        "genre": "Dance",
        "language": "Tamil",
        "is_trending": True,
    },
    {
        "track_id": 3,
        "title": "Arabic Kuthu - Halamithi Habibo",
        "artist": "Anirudh Ravichander, Jonita Gandhi",
        "album": "Beast",
        "duration_seconds": 60.0,
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "cover_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300",
        "genre": "Kuthu",
        "language": "Tamil",
        "is_trending": True,
    },
    {
        "track_id": 4,
        "title": "Kadhale Kadhale",
        "artist": "Govind Vasantha, Chinmayi",
        "album": "96",
        "duration_seconds": 60.0,
        "audio_url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
        "cover_url": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=300",
        "genre": "Melody",
        "language": "Tamil",
        "is_trending": True,
    },
]


class MusicService:
    @staticmethod
    def get_trending(limit: int = 10) -> List[MusicTrackResponse]:
        return [MusicTrackResponse(**t) for t in TAMIL_MUSIC_PRESETS[:limit]]

    @staticmethod
    def search(query: str, limit: int = 10) -> List[MusicTrackResponse]:
        q = query.strip().lower()
        if not q:
            return MusicService.get_trending(limit)
        matched = [
            MusicTrackResponse(**t)
            for t in TAMIL_MUSIC_PRESETS
            if q in t["title"].lower() or q in t["artist"].lower()
        ]
        return matched[:limit]
