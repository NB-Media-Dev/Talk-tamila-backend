import json
import logging
import urllib.parse
import urllib.request
from typing import List, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.common.models.music import MusicTrack
from app.common.models.story import Story
from app.common.schemas.music import MusicTrackResponse

logger = logging.getLogger("talktamila.music_service")

OPEN_ITUNES_API_URL = "https://itunes.apple.com/search"


def fetch_from_open_itunes(term: str, limit: int = 15) -> List[MusicTrackResponse]:
    params = {
        "term": term,
        "media": "music",
        "entity": "song",
        "limit": min(limit, 30),
    }
    encoded_url = f"{OPEN_ITUNES_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        encoded_url,
        headers={"User-Agent": "TalkTamila/2.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status != 200:
                return []
            raw_data = response.read()
            data = json.loads(raw_data.decode("utf-8"))
            results = data.get("results", [])

            parsed_tracks: List[MusicTrackResponse] = []
            for item in results:
                track_id = item.get("trackId")
                title = item.get("trackName")
                artist = item.get("artistName")
                audio_url = item.get("previewUrl")

                if not track_id or not title or not audio_url:
                    continue

                artwork_url = item.get("artworkUrl100")
                if artwork_url:
                    artwork_url = artwork_url.replace("100x100bb", "600x600bb")

                duration_ms = item.get("trackTimeMillis")
                duration_sec = round(duration_ms / 1000.0, 1) if duration_ms else 30.0

                parsed_tracks.append(
                    MusicTrackResponse(
                        track_id=track_id,
                        title=title,
                        artist=artist or "Artist",
                        album=item.get("collectionName"),
                        duration_seconds=duration_sec,
                        audio_url=audio_url,
                        cover_url=artwork_url,
                        genre=item.get("primaryGenreName") or "Tamil",
                        language="Tamil",
                        is_trending=True,
                    )
                )

            return parsed_tracks
    except Exception as e:
        logger.warning("Error fetching music for term '%s': %s", term, e)
        return []


class MusicService:
    @staticmethod
    def get_trending(db: Session, limit: int = 15) -> List[MusicTrackResponse]:
        results: List[MusicTrackResponse] = []
        seen_keys = set()

        live_hits = fetch_from_open_itunes("Tamil Top Hits", limit=limit)
        for t in live_hits:
            key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(t)

        try:
            story_tracks = (
                db.query(
                    Story.music_title,
                    Story.music_artist,
                    func.max(Story.music_url).label("audio_url"),
                    func.max(Story.music_thumbnail).label("cover_url"),
                    func.max(Story.music_duration).label("duration_seconds"),
                    func.count(Story.story_id).label("usage_count"),
                )
                .filter(
                    Story.music_title.isnot(None),
                    Story.music_title != "",
                )
                .group_by(Story.music_title, Story.music_artist)
                .order_by(desc("usage_count"), desc(func.max(Story.created_at)))
                .limit(limit)
                .all()
            )

            for idx, st in enumerate(story_tracks, start=5000):
                title = (st.music_title or "").strip()
                artist = (st.music_artist or "Tamil Artist").strip()
                key = f"{title.lower()}::{artist.lower()}"
                if key not in seen_keys and title:
                    seen_keys.add(key)
                    results.append(
                        MusicTrackResponse(
                            track_id=idx,
                            title=title,
                            artist=artist,
                            album=None,
                            duration_seconds=float(st.duration_seconds or 60.0),
                            audio_url=st.audio_url or "",
                            cover_url=st.cover_url,
                            genre="Tamil",
                            language="Tamil",
                            is_trending=True,
                        )
                    )
        except Exception:
            pass

        try:
            db_tracks = (
                db.query(MusicTrack)
                .filter(MusicTrack.is_trending == True)
                .order_by(desc(MusicTrack.track_id))
                .limit(limit)
                .all()
            )

            for t in db_tracks:
                key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(
                        MusicTrackResponse(
                            track_id=t.track_id,
                            title=t.title,
                            artist=t.artist,
                            album=t.album,
                            duration_seconds=t.duration_seconds or 60.0,
                            audio_url=t.audio_url,
                            cover_url=t.cover_url,
                            genre=t.genre or "Tamil",
                            language=t.language or "Tamil",
                            is_trending=t.is_trending,
                        )
                    )
        except Exception:
            pass

        return results[:limit]

    @staticmethod
    def search(db: Session, query: str = "", limit: int = 15) -> List[MusicTrackResponse]:
        q = query.strip()
        if not q:
            return MusicService.get_trending(db, limit)

        results: List[MusicTrackResponse] = []
        seen_keys = set()

        live_matches = fetch_from_open_itunes(f"{q} Tamil", limit=limit)
        if not live_matches:
            live_matches = fetch_from_open_itunes(q, limit=limit)

        for t in live_matches:
            key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(t)

        pattern = f"%{q}%"

        try:
            db_tracks = (
                db.query(MusicTrack)
                .filter(
                    or_(
                        MusicTrack.title.ilike(pattern),
                        MusicTrack.artist.ilike(pattern),
                        MusicTrack.album.ilike(pattern),
                    )
                )
                .order_by(desc(MusicTrack.is_trending), desc(MusicTrack.track_id))
                .limit(limit)
                .all()
            )

            for t in db_tracks:
                key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(
                        MusicTrackResponse(
                            track_id=t.track_id,
                            title=t.title,
                            artist=t.artist,
                            album=t.album,
                            duration_seconds=t.duration_seconds or 60.0,
                            audio_url=t.audio_url,
                            cover_url=t.cover_url,
                            genre=t.genre or "Tamil",
                            language=t.language or "Tamil",
                            is_trending=t.is_trending,
                        )
                    )
        except Exception:
            pass

        try:
            story_tracks = (
                db.query(
                    Story.music_title,
                    Story.music_artist,
                    func.max(Story.music_url).label("audio_url"),
                    func.max(Story.music_thumbnail).label("cover_url"),
                    func.max(Story.music_duration).label("duration_seconds"),
                    func.count(Story.story_id).label("usage_count"),
                )
                .filter(
                    Story.music_title.isnot(None),
                    or_(
                        Story.music_title.ilike(pattern),
                        Story.music_artist.ilike(pattern),
                    ),
                )
                .group_by(Story.music_title, Story.music_artist)
                .order_by(desc("usage_count"), desc(func.max(Story.created_at)))
                .limit(limit)
                .all()
            )

            for idx, st in enumerate(story_tracks, start=8000):
                title = (st.music_title or "").strip()
                artist = (st.music_artist or "Tamil Artist").strip()
                key = f"{title.lower()}::{artist.lower()}"
                if key not in seen_keys and title:
                    seen_keys.add(key)
                    results.append(
                        MusicTrackResponse(
                            track_id=idx,
                            title=title,
                            artist=artist,
                            album=None,
                            duration_seconds=float(st.duration_seconds or 60.0),
                            audio_url=st.audio_url or "",
                            cover_url=st.cover_url,
                            genre="Tamil",
                            language="Tamil",
                            is_trending=True,
                        )
                    )
        except Exception:
            pass

        return results[:limit]

    @staticmethod
    def resolve_or_create_music_track(
        db: Session,
        music_id: Optional[int] = None,
        music_title: Optional[str] = None,
        music_artist: Optional[str] = None,
        music_url: Optional[str] = None,
        music_thumbnail: Optional[str] = None,
        music_duration: Optional[float] = None,
    ) -> Optional[int]:
        if not music_id and not (music_title and music_url):
            return None

        if music_id is not None:
            try:
                existing = db.query(MusicTrack).filter(MusicTrack.track_id == int(music_id)).first()
                if existing:
                    return existing.track_id
            except Exception:
                pass

        if music_title:
            try:
                existing_name = (
                    db.query(MusicTrack)
                    .filter(
                        MusicTrack.title == music_title,
                        MusicTrack.artist == (music_artist or "Artist"),
                    )
                    .first()
                )
                if existing_name:
                    return existing_name.track_id
            except Exception:
                pass

        if music_title and (music_url or music_id):
            try:
                with db.begin_nested():
                    new_track = MusicTrack(
                        track_id=int(music_id) if music_id and int(music_id) < 2147483647 else None,
                        title=music_title[:250],
                        artist=(music_artist or "Artist")[:250],
                        audio_url=(music_url or "")[:490],
                        cover_url=music_thumbnail[:490] if music_thumbnail else None,
                        duration_seconds=float(music_duration or 30.0),
                        genre="Tamil",
                        language="Tamil",
                        is_trending=True,
                    )
                    db.add(new_track)
                    db.flush()
                    return new_track.track_id
            except Exception as e:
                logger.warning("Auto-save music_track error: %s", e)
                try:
                    existing_name = (
                        db.query(MusicTrack)
                        .filter(MusicTrack.title == music_title)
                        .first()
                    )
                    if existing_name:
                        return existing_name.track_id
                except Exception:
                    pass

        return None
