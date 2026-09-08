import logging
from typing import List, Optional
import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.music import MusicTrack

logger = logging.getLogger("talktamila.music")

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"


def _format_itunes_item(item: dict) -> Optional[dict]:
    """Format raw live API item into clean MusicTrack dictionary with preview audio URL and 600x600 cover."""
    audio_url = item.get("previewUrl")
    if not audio_url:
        return None

    raw_cover = item.get("artworkUrl100") or ""
    cover_url = raw_cover.replace("100x100bb", "600x600bb") if raw_cover else None

    title = item.get("trackName") or item.get("collectionCensoredName") or "Unknown Song"
    artist = item.get("artistName") or "Unknown Artist"
    album = item.get("collectionName")

    track_time_ms = item.get("trackTimeMillis", 30000)
    duration_seconds = max(15, min(60, int(track_time_ms / 1000))) if track_time_ms else 30
    genre = item.get("primaryGenreName")

    text_corpus = f"{title} {album or ''} {artist} {genre or ''}".lower()
    if "tamil" in text_corpus:
        language = "Tamil"
    elif "malayalam" in text_corpus:
        language = "Malayalam"
    elif "telugu" in text_corpus:
        language = "Telugu"
    elif "hindi" in text_corpus:
        language = "Hindi"
    else:
        language = "Tamil"

    return {
        "track_id": int(item["trackId"]),
        "title": title,
        "artist": artist,
        "album": album,
        "duration_seconds": duration_seconds,
        "audio_url": audio_url,
        "cover_url": cover_url,
        "genre": genre,
        "language": language,
        "is_trending": False,
    }


def fetch_live_itunes_music(term: str, limit: int = 30, country: str = "IN") -> List[dict]:
    """Search for live music from live music servers (iTunes global API). No hardcoded tracks."""
    try:
        with httpx.Client(timeout=6.0) as client:
            resp = client.get(
                ITUNES_SEARCH_URL,
                params={
                    "term": term,
                    "media": "music",
                    "entity": "song",
                    "country": country,
                    "limit": min(limit, 50),
                },
            )
            if resp.status_code != 200:
                logger.warning("Live music search returned status %s for term '%s'", resp.status_code, term)
                return []

            raw_results = resp.json().get("results", [])
            formatted = []
            for raw in raw_results:
                track = _format_itunes_item(raw)
                if track:
                    formatted.append(track)
            return formatted
    except Exception as exc:
        logger.warning("Live music search exception for term '%s': %s", term, exc)
        return []


def fetch_live_track_by_id(track_id: int, country: str = "IN") -> Optional[dict]:
    """Lookup a specific track by its trackId live from server."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(ITUNES_LOOKUP_URL, params={"id": track_id, "country": country})
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return _format_itunes_item(results[0])
    except Exception as exc:
        logger.warning("Live track lookup exception for id %s: %s", track_id, exc)
    return None


def upsert_music_tracks(db: Session, track_dicts: List[dict]) -> List[MusicTrack]:
    """Save or update live fetched tracks in database for foreign keys."""
    if not track_dicts:
        return []

    persisted = []
    try:
        for t in track_dicts:
            existing = db.query(MusicTrack).filter(MusicTrack.track_id == t["track_id"]).first()
            if existing:
                existing.title = t["title"]
                existing.artist = t["artist"]
                existing.album = t["album"]
                existing.duration_seconds = t["duration_seconds"]
                existing.audio_url = t["audio_url"]
                existing.cover_url = t["cover_url"]
                existing.genre = t["genre"]
                existing.language = t["language"]
                persisted.append(existing)
            else:
                new_track = MusicTrack(
                    track_id=t["track_id"],
                    title=t["title"],
                    artist=t["artist"],
                    album=t["album"],
                    duration_seconds=t["duration_seconds"],
                    audio_url=t["audio_url"],
                    cover_url=t["cover_url"],
                    genre=t["genre"],
                    language=t["language"],
                    is_trending=t.get("is_trending", False),
                )
                db.add(new_track)
                persisted.append(new_track)

        db.commit()
        for p in persisted:
            db.refresh(p)
        return persisted
    except Exception as exc:
        db.rollback()
        logger.warning("Failed to upsert tracks to DB: %s", exc)
        return [
            MusicTrack(
                track_id=t["track_id"],
                title=t["title"],
                artist=t["artist"],
                album=t["album"],
                duration_seconds=t["duration_seconds"],
                audio_url=t["audio_url"],
                cover_url=t["cover_url"],
                genre=t["genre"],
                language=t["language"],
                is_trending=t.get("is_trending", False),
            )
            for t in track_dicts
        ]


def seed_music_tracks(db: Session) -> int:
    """Optional helper: fetch trending songs live from server on first run."""
    try:
        if db.query(MusicTrack).count() > 0:
            return 0
        live_trending = fetch_live_itunes_music("Tamil Hits", limit=15)
        if live_trending:
            for item in live_trending:
                item["is_trending"] = True
            upsert_music_tracks(db, live_trending)
            return len(live_trending)
    except Exception as exc:
        logger.warning("Error in seed_music_tracks: %s", exc)
    return 0


def search_music_tracks(
    db: Session,
    query: Optional[str] = None,
    genre: Optional[str] = None,
    language: Optional[str] = None,
    trending_only: bool = False,
    skip: int = 0,
    limit: int = 30,
) -> List[MusicTrack]:
    """Live song search from live server with zero hardcoded tracks."""
    live_results = []

    if trending_only or (not query and not genre and not language):
        search_term = "Tamil Hits Trending"
        live_results = fetch_live_itunes_music(search_term, limit=limit)
        for t in live_results:
            t["is_trending"] = True
    elif query and query.strip():
        search_term = query.strip()
        live_results = fetch_live_itunes_music(search_term, limit=limit)
        if len(live_results) < 3 and "tamil" not in search_term.lower():
            extra = fetch_live_itunes_music(f"{search_term} Tamil", limit=limit)
            seen_ids = {r["track_id"] for r in live_results}
            for e in extra:
                if e["track_id"] not in seen_ids:
                    live_results.append(e)
    elif genre:
        live_results = fetch_live_itunes_music(f"Tamil {genre}", limit=limit)

    if live_results:
        tracks = upsert_music_tracks(db, live_results)
        return tracks[skip : skip + limit]

    # Local fallback if network fails
    q = db.query(MusicTrack)
    if trending_only:
        q = q.filter(MusicTrack.is_trending.is_(True))
    if language:
        q = q.filter(MusicTrack.language.ilike(f"%{language}%"))
    if genre:
        q = q.filter(MusicTrack.genre.ilike(f"%{genre}%"))
    if query and query.strip():
        search_pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                MusicTrack.title.ilike(search_pattern),
                MusicTrack.artist.ilike(search_pattern),
                MusicTrack.album.ilike(search_pattern),
                MusicTrack.genre.ilike(search_pattern),
            )
        )
    return q.order_by(MusicTrack.is_trending.desc(), MusicTrack.title.asc()).offset(skip).limit(limit).all()


def get_music_track_by_id(db: Session, track_id: int) -> Optional[MusicTrack]:
    """Get track by ID. If not in DB, fetches live from API."""
    track = db.query(MusicTrack).filter(MusicTrack.track_id == track_id).first()
    if track:
        return track
    live_data = fetch_live_track_by_id(track_id)
    if live_data:
        tracks = upsert_music_tracks(db, [live_data])
        if tracks:
            return tracks[0]
    return None
