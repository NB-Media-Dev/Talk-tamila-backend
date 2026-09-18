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
    """Fetch free songs, artwork, and audio preview clips from open public iTunes Search API.
    - 100% Free & Open (No API keys required)
    - Full global catalog (All Tamil, Indian, International tracks)
    - High-quality 30-second audio stream and high-res cover artwork
    """
    params = {
        "term": term,
        "media": "music",
        "entity": "song",
        "limit": min(limit, 30),
    }
    encoded_url = f"{OPEN_ITUNES_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        encoded_url,
        headers={"User-Agent": "TalkTamila/2.0 (Story Music Engine)"},
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
                    # Upgrade thumbnail to high resolution 600x600 artwork
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
        logger.warning("Open music fetch note for term '%s': %s", term, e)
        return []


class MusicService:
    @staticmethod
    def get_trending(db: Session, limit: int = 15) -> List[MusicTrackResponse]:
        """Fetch trending songs dynamically:
        1. Query open live trending tracks (Tamil Top Hits / Trending Hits)
        2. Query songs used most frequently in recent stories (live creator rankings)
        3. Query curated tracks from MusicTrack database table
        4. Merge and deduplicate dynamically
        """
        results: List[MusicTrackResponse] = []
        seen_keys = set()

        # 1. Fetch live trending hits from open music API
        live_hits = fetch_from_open_itunes("Tamil Top Hits", limit=limit)
        for t in live_hits:
            key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(t)

        # 2. Fetch live trending songs from active story usages
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

        # 3. Fetch tracks from MusicTrack database table
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
        """Search songs in real time across the complete open music library + database + stories."""
        q = query.strip()
        if not q:
            return MusicService.get_trending(db, limit)

        results: List[MusicTrackResponse] = []
        seen_keys = set()

        # 1. Search live in open global music library
        # Also append Tamil keyword if searching generic titles to prioritize regional tracks
        live_matches = fetch_from_open_itunes(f"{q} Tamil", limit=limit)
        if not live_matches:
            live_matches = fetch_from_open_itunes(q, limit=limit)

        for t in live_matches:
            key = f"{t.title.strip().lower()}::{t.artist.strip().lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                results.append(t)

        pattern = f"%{q}%"

        # 2. Search in MusicTrack database table
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

        # 3. Search in story tracks
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
        """Ensures a music track exists in the `music_tracks` table before attaching to a story.
        Prevents foreign key constraint errors (`fk_stories_music`) when users select songs
        from live open search or external sources.
        """
        if not music_id and not (music_title and music_url):
            return None

        # 1. Check if track already exists by track_id
        if music_id is not None:
            try:
                existing = db.query(MusicTrack).filter(MusicTrack.track_id == int(music_id)).first()
                if existing:
                    return existing.track_id
            except Exception:
                pass

        # 2. Check if track already exists by exact title & artist
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

        # 3. Insert new track into music_tracks table
        if music_title and (music_url or music_id):
            try:
                # Use a nested transaction / savepoint so any error doesn't abort the outer transaction
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
                logger.warning("Auto-save music_track note: %s", e)
                # Fallback: check if track was created or return None
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
