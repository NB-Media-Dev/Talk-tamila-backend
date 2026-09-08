import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.stories import get_db, get_current_user
from app.db.database import Base
from app.main import app
from app.models import MusicTrack, Story, User
from app.services.music_service import seed_music_tracks

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    
    user = User(user_id=1, username="thavam_user", email="thavam@example.com")
    db.add(user)
    db.commit()
    seed_music_tracks(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user():
    db = TestingSessionLocal()
    try:
        return db.query(User).first()
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user

client = TestClient(app)


def test_search_music():
    # 1. Search for Anirudh songs live from server
    response = client.get("/api/stories/music/search?q=anirudh")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert any("anirudh" in item["artist"].lower() for item in data)
    # Check that each track has live streamable audio and cover artwork
    assert data[0]["audio_url"].startswith("http")
    assert data[0]["cover_url"].startswith("http")

    # 2. Search for Leo live from server
    response = client.get("/api/stories/music/search?q=Leo")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert any("leo" in (item.get("album") or "").lower() or "leo" in item.get("title").lower() for item in data)


def test_trending_music():
    response = client.get("/api/stories/music/trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["audio_url"].startswith("http")
    assert data[0]["title"] is not None



def test_single_story_with_music():
    payload = {
        "media_url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e",
        "media_type": "image",
        "caption": "Enjoying the beach vibes with Anirudh song",
        "music_id": 1,
        "music_title": "Naa Ready",
        "music_artist": "Anirudh Ravichander",
        "music_url": "https://commondatastorage.googleapis.com/codeskulptor-assets/Epoq-Lepidoptera.ogg",
        "music_thumbnail": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819",
        "music_start_time": 5.0,
        "music_duration": 15.0,
    }
    response = client.post("/api/stories", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["caption"] == payload["caption"]
    assert data["music_title"] == "Naa Ready"
    assert data["music_artist"] == "Anirudh Ravichander"
    assert data["music_start_time"] == 5.0


def test_batch_story_creation():
    payload = {
        "shared_music": {
            "music_title": "Hukum - Thalaivar Alappara",
            "music_artist": "Anirudh Ravichander",
            "music_url": "https://commondatastorage.googleapis.com/codeskulptor-assets/sounddogs/soundtrack.mp3",
            "music_thumbnail": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745",
            "music_start_time": 0.0,
            "music_duration": 15.0,
        },
        "items": [
            {
                "media_url": "https://images.unsplash.com/photo-1506744038136-46273834b3fb",
                "media_type": "image",
                "caption": "Photo 1 - Mountains",
            },
            {
                "media_url": "https://images.unsplash.com/photo-1469474968028-56623f02e42e",
                "media_type": "image",
                "caption": "Photo 2 - Forest",
            },
            {
                "media_url": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
                "media_type": "video",
                "caption": "Video 3 - Sunset clip",
            },
        ],
    }
    response = client.post("/api/stories/batch", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["total_published"] == 3
    assert len(data["stories"]) == 3

    for story in data["stories"]:
        assert story["music_title"] == "Hukum - Thalaivar Alappara"
        assert story["user_id"] == 1


def test_upload_multiple_story_files():
    image1_bytes = b"fake_image_content_1"
    image2_bytes = b"fake_image_content_2"
    video_bytes = b"fake_video_content_mp4"

    files = [
        ("files", ("slide1.jpg", io.BytesIO(image1_bytes), "image/jpeg")),
        ("files", ("slide2.png", io.BytesIO(image2_bytes), "image/png")),
        ("files", ("clip.mp4", io.BytesIO(video_bytes), "video/mp4")),
    ]

    music_data = '{"music_title": "Kaavaalaa", "music_artist": "Anirudh", "music_url": "https://example.com/audio.mp3"}'
    captions = '["Sunset vibes", "Coffee break", "Driving home"]'

    response = client.post(
        "/api/stories/upload-multiple",
        files=files,
        data={"music_data": music_data, "captions": captions},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["total_published"] == 3

    stories = data["stories"]
    assert stories[0]["media_type"] == "image"
    assert stories[0]["caption"] == "Sunset vibes"
    assert stories[0]["music_title"] == "Kaavaalaa"

    assert stories[1]["media_type"] == "image"
    assert stories[1]["caption"] == "Coffee break"

    assert stories[2]["media_type"] == "video"
    assert stories[2]["caption"] == "Driving home"


def test_upload_single_story_from_device():
    file = ("file", ("gallery_photo.jpg", io.BytesIO(b"binary_device_photo"), "image/jpeg"))
    music_data = '{"music_title": "Naa Ready", "music_artist": "Anirudh", "music_duration": 45.0}'
    response = client.post(
        "/api/stories/upload",
        files=[file],
        data={"caption": "From my device gallery", "audience": "followers", "music_data": music_data},
    )
    assert response.status_code == 201
    story = response.json()
    assert story["caption"] == "From my device gallery"
    assert story["audience"] == "followers"
    assert story["media_type"] == "image"
    assert "/uploads/stories/" in story["media_url"]
    assert story["music_title"] == "Naa Ready"
    assert story["music_duration"] == 45.0



def test_grouped_story_feed():
    response = client.get("/api/stories/feed")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    first_group = data[0]
    assert "user" in first_group
    assert "stories" in first_group
    assert first_group["stories_count"] == len(first_group["stories"])
    assert first_group["stories_count"] >= 7


def test_audience_options_influencer_and_freelancer():
    # Test influencer user
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "influencer"
    db.commit()
    db.close()

    response = client.get("/api/stories/audience-options")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "influencer"
    option_ids = [opt["id"] for opt in data["allowed_audiences"]]
    assert "public" in option_ids
    assert "followers" in option_ids
    assert "close_friends" in option_ids

    # Test freelancer user
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "freelancer"
    db.commit()
    db.close()

    response = client.get("/api/stories/audience-options")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "freelancer"
    option_ids = [opt["id"] for opt in data["allowed_audiences"]]
    assert len(option_ids) == 3


def test_audience_options_admin():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "admin"
    db.commit()
    db.close()

    response = client.get("/api/stories/audience-options")
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin"
    option_ids = [opt["id"] for opt in data["allowed_audiences"]]
    # Admin only has 'public'
    assert option_ids == ["public"]


def test_influencer_can_post_with_different_audiences():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "influencer"
    db.commit()
    db.close()

    # Followers audience
    resp1 = client.post("/api/stories", json={
        "media_url": "https://example.com/followers_only.jpg",
        "caption": "For my followers only!",
        "audience": "followers",
    })
    assert resp1.status_code == 201
    assert resp1.json()["audience"] == "followers"

    # Close Friends (Close Circle alias)
    resp2 = client.post("/api/stories", json={
        "media_url": "https://example.com/close_circle.jpg",
        "caption": "Close circle story",
        "audience": "close_circle",
    })
    assert resp2.status_code == 201
    assert resp2.json()["audience"] == "close_friends"


def test_admin_restricted_to_public_only():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "admin"
    db.commit()
    db.close()

    # Admin posting with explicit public succeeds as public
    resp_ok = client.post("/api/stories", json={
        "media_url": "https://example.com/admin_announcement.jpg",
        "caption": "Platform update for everyone",
        "audience": "public",
    })
    assert resp_ok.status_code == 201
    assert resp_ok.json()["audience"] == "public"

    # Admin posting with no audience specified defaults and uploads as public
    resp_default = client.post("/api/stories", json={
        "media_url": "https://example.com/admin_default.jpg",
        "caption": "Admin default story",
    })
    assert resp_default.status_code == 201
    assert resp_default.json()["audience"] == "public"

    # Admin story batch upload automatically defaults and uploads as public
    resp_batch = client.post("/api/stories/batch", json={
        "items": [
            {"media_url": "https://example.com/admin_slide1.jpg", "caption": "Admin slide 1"},
            {"media_url": "https://example.com/admin_slide2.jpg", "caption": "Admin slide 2"},
        ]
    })
    assert resp_batch.status_code == 201
    assert all(s["audience"] == "public" for s in resp_batch.json()["stories"])

    # Admin uploading multiple files via multipart form defaults and uploads strictly as public
    files = [
        ("files", ("admin1.png", b"\x89PNG\r\n\x1a\nfakeimagecontent1", "image/png")),
        ("files", ("admin2.png", b"\x89PNG\r\n\x1a\nfakeimagecontent2", "image/png")),
    ]
    resp_upload = client.post("/api/stories/upload-multiple", files=files)
    assert resp_upload.status_code == 201
    assert all(s["audience"] == "public" for s in resp_upload.json()["stories"])



def test_song_duration_limit_one_minute():
    db = TestingSessionLocal()
    user = db.query(User).filter(User.user_id == 1).first()
    user.role = "influencer"
    db.commit()
    db.close()

    # 1. Post with default duration (should be 60.0 seconds / 1 min)
    resp1 = client.post("/api/stories", json={
        "media_url": "https://example.com/song_test1.jpg",
        "caption": "Full 1 min track",
        "music_title": "Arabic Kuthu",
        "music_url": "https://example.com/audio.mp3",
    })
    assert resp1.status_code == 201
    assert resp1.json()["music_duration"] == 60.0

    # 2. Post with valid 45s duration
    resp2 = client.post("/api/stories", json={
        "media_url": "https://example.com/song_test2.jpg",
        "caption": "45s track clip",
        "music_title": "Hukum",
        "music_url": "https://example.com/audio.mp3",
        "music_duration": 45.0,
    })
    assert resp2.status_code == 201
    assert resp2.json()["music_duration"] == 45.0

    # 3. Post exceeding 60s (e.g. 90s or 120s) should be rejected or capped
    resp_exceed = client.post("/api/stories", json={
        "media_url": "https://example.com/song_test3.jpg",
        "caption": "Too long track",
        "music_title": "Long Song",
        "music_url": "https://example.com/audio.mp3",
        "music_duration": 90.0,
    })
    # Field validation enforces le=60.0 -> returns 422 Unprocessable Entity
    assert resp_exceed.status_code == 422


