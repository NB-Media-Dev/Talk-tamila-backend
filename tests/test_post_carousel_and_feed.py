from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.models import Follow, Post, PostMedia
from app.common.models.post import _utc_now
from app.core.database import Base
from app.utils.seed import seed_db_data, seed_demo_posts

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _create(client, headers, files=None, **data):
    return client.post("/api/v1/posts", data=data, files=files, headers=headers)


def test_carousel_post_has_every_slide(client: TestClient, admin_auth_headers):
    r = _create(
        client,
        admin_auth_headers,
        post_type="image",
        content="three slides",
        files=[
            ("media", ("a.png", PNG, "image/png")),
            ("more_media", ("b.jpg", JPG, "image/jpeg")),
            ("more_media", ("c.webp", WEBP, "image/webp")),
        ],
    )
    assert r.status_code == 201, r.text
    post = r.json()["items"][0]
    assert post["media_url"].endswith("/media")
    assert len(post["media_urls"]) == 3
    assert post["media_urls"][1].endswith("/media/1") and post["media_urls"][2].endswith("/media/2")

    expected = [("image/png", PNG), ("image/jpeg", JPG), ("image/webp", WEBP)]
    for url, (mime, data) in zip(post["media_urls"], expected):
        m = client.get(url)
        assert m.status_code == 200
        assert m.headers["content-type"] == mime
        assert m.content == data

    assert client.get(f"/api/v1/posts/{post['post_id']}/media/3").status_code == 404


def test_single_photo_still_has_one_url(client: TestClient, admin_auth_headers):
    r = _create(client, admin_auth_headers, post_type="image", files={"media": ("a.png", PNG, "image/png")})
    post = r.json()["items"][0]
    assert post["media_urls"] == [post["media_url"]]


def test_text_post_has_no_media_urls(client: TestClient, admin_auth_headers):
    r = _create(client, admin_auth_headers, post_type="text", content="hello")
    assert r.json()["items"][0]["media_urls"] == []


def test_carousel_limit_is_ten(client: TestClient, admin_auth_headers):
    files = [("media", ("a.png", PNG, "image/png"))] + [
        ("more_media", (f"{i}.png", PNG, "image/png")) for i in range(10)
    ]
    assert _create(client, admin_auth_headers, post_type="image", files=files).status_code == 400
    ok = [("media", ("a.png", PNG, "image/png"))] + [
        ("more_media", (f"{i}.png", PNG, "image/png")) for i in range(9)
    ]
    r = _create(client, admin_auth_headers, post_type="image", files=ok)
    assert r.status_code == 201, r.text
    assert len(r.json()["items"][0]["media_urls"]) == 10


def test_carousel_only_for_photos(client: TestClient, admin_auth_headers):
    r = _create(
        client, admin_auth_headers, post_type="video",
        files=[("media", ("a.mp4", MP4, "video/mp4")), ("more_media", ("b.png", PNG, "image/png"))],
    )
    assert r.status_code == 400
    r = _create(
        client, admin_auth_headers, post_type="image",
        files=[("media", ("a.png", PNG, "image/png")), ("more_media", ("b.mp4", MP4, "video/mp4"))],
    )
    assert r.status_code == 400


def test_deleting_a_carousel_removes_its_slides(client: TestClient, admin_auth_headers, db_session):
    r = _create(
        client, admin_auth_headers, post_type="image",
        files=[("media", ("a.png", PNG, "image/png")), ("more_media", ("b.png", PNG, "image/png"))],
    )
    pid = r.json()["items"][0]["post_id"]
    assert db_session.execute(select(func.count(PostMedia.media_id)).where(PostMedia.post_id == pid)).scalar() == 1
    assert client.delete(f"/api/v1/posts/{pid}", headers=admin_auth_headers).status_code == 200
    db_session.expire_all()
    assert db_session.execute(select(func.count(PostMedia.media_id)).where(PostMedia.post_id == pid)).scalar() == 0


def test_new_post_goes_to_the_top(client: TestClient, admin_auth_headers):
    first = _create(client, admin_auth_headers, post_type="text", content="older one").json()["items"][0]
    second = _create(client, admin_auth_headers, post_type="text", content="newest one").json()["items"][0]
    feed = client.get("/api/v1/posts", headers=admin_auth_headers).json()["items"]
    ids = [p["post_id"] for p in feed]
    assert ids.index(second["post_id"]) < ids.index(first["post_id"])
    assert ids[0] == second["post_id"]


def test_feed_keeps_followed_people_even_when_old_and_hides_old_strangers(
    client: TestClient, admin_auth_headers, influencer_auth_headers, db_session
):
    old = _utc_now() - timedelta(days=60)
    followed_old = Post(user_id=1, post_type="text", content="old but followed", status="published",
                        created_at=old, published_at=old)
    stranger_old = Post(user_id=2, post_type="text", content="old stranger", status="published",
                        created_at=old, published_at=old)
    follow = Follow(follower_id=3, following_id=1)
    db_session.add_all([followed_old, stranger_old, follow])
    db_session.commit()
    try:
        # something recent so the feed is not empty
        _create(client, admin_auth_headers, post_type="text", content="fresh post")

        feed = client.get("/api/v1/posts?limit=30", headers=influencer_auth_headers).json()["items"]
        ids = {p["post_id"] for p in feed}
        assert followed_old.post_id in ids
        assert stranger_old.post_id not in ids
        assert any(p["content"] == "fresh post" for p in feed)
    finally:
        # Leave the shared test database as we found it.
        db_session.delete(follow)
        db_session.delete(followed_old)
        db_session.delete(stranger_old)
        db_session.commit()


def test_demo_posts_are_added_once_and_include_carousels():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        seed_db_data(db)
        added = seed_demo_posts(db)
        assert added >= 6
        assert seed_demo_posts(db) == 0  # never twice
        posts = db.execute(select(Post).order_by(Post.published_at.desc())).scalars().all()
        assert posts[0].published_at >= posts[-1].published_at
        assert any(len(p.extra_media) >= 2 for p in posts)
        assert any(p.post_type == "poll" and len(p.poll_options) >= 2 for p in posts)
        assert any(p.post_type == "text" for p in posts)
        assert all(p.media_data[:8] == b"\x89PNG\r\n\x1a\n" for p in posts if p.media_mime)