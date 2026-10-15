"""The reset keeps only the admin; demo content is optional and repeatable-safe.

Uses its own in-memory database so it cannot disturb the shared test data.
"""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.models import DirectMessage, Follow, Notification, Post, PostLike, Profile, Story, User
from app.core.database import Base
from app.utils.db_reset import count_rows, reset_to_admin_only
from app.utils.demo_content import (
    DEMO_CREATORS,
    DEMO_IMAGE_POSTS,
    DEMO_POSTS,
    _art_png,
    add_demo_content,
)
from app.common.services.post_service import sniff_mime
from app.utils.seed import seed_db_data


@pytest.fixture
def fresh_db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    session = sessionmaker(bind=eng)()
    seed_db_data(session)  # 11 users + stories, like a messy old database
    session.add(Notification(user_id=2, type="like", message="x"))
    session.add(Follow(follower_id=2, following_id=3, user_name="Priya"))
    session.add(DirectMessage(sender_id=2, receiver_id=3, body="hi"))
    session.commit()
    yield session
    session.close()
    eng.dispose()


def _count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar_one()


def test_reset_keeps_only_admin(fresh_db):
    kept = reset_to_admin_only(fresh_db)
    assert kept == ["admin"]
    assert _count(fresh_db, User) == 1
    assert _count(fresh_db, Profile) == 1
    for model in (Story, Post, Follow, Notification, DirectMessage):
        assert _count(fresh_db, model) == 0
    assert fresh_db.execute(select(User.role)).scalar_one() == "admin"


def test_reset_keeps_admin_password(fresh_db):
    before = fresh_db.execute(select(User.password).where(User.role == "admin")).scalar_one()
    reset_to_admin_only(fresh_db)
    after = fresh_db.execute(select(User.password).where(User.role == "admin")).scalar_one()
    assert before == after


def test_count_rows_reports_every_table(fresh_db):
    counts = count_rows(fresh_db)
    assert counts["users"] == 11
    assert counts["stories"] == 4


def test_demo_content_adds_creators_and_posts(fresh_db):
    reset_to_admin_only(fresh_db)
    made = add_demo_content(fresh_db, "Pass-1234")
    assert made["users"] == len(DEMO_CREATORS)
    assert made["posts"] == len(DEMO_POSTS) + len(DEMO_IMAGE_POSTS)
    assert _count(fresh_db, User) == len(DEMO_CREATORS) + 1  # demo creators + admin
    assert _count(fresh_db, PostLike) > 0
    # Every author's post counter matches the posts that really exist.
    for profile in fresh_db.execute(select(Profile)).scalars():
        real = _count_posts(fresh_db, profile.user_id)
        assert profile.posts_count == real


def _count_posts(db, user_id):
    return db.execute(select(func.count()).select_from(Post).where(Post.user_id == user_id)).scalar_one()


def test_demo_content_is_not_added_twice(fresh_db):
    reset_to_admin_only(fresh_db)
    assert add_demo_content(fresh_db, "Pass-1234") is not None
    assert add_demo_content(fresh_db, "Pass-1234") is None
    assert _count(fresh_db, Post) == len(DEMO_POSTS) + len(DEMO_IMAGE_POSTS)


def test_reset_after_demo_returns_to_admin_only(fresh_db):
    reset_to_admin_only(fresh_db)
    add_demo_content(fresh_db, "Pass-1234")
    reset_to_admin_only(fresh_db)
    assert _count(fresh_db, User) == 1
    assert _count(fresh_db, Post) == 0


def test_demo_image_posts_have_real_png_media(fresh_db):
    reset_to_admin_only(fresh_db)
    add_demo_content(fresh_db, "Pass-1234")
    rows = fresh_db.execute(select(Post).where(Post.post_type == "image")).scalars().all()
    assert len(rows) == len(DEMO_IMAGE_POSTS)
    for post in rows:
        assert post.media_mime == "image/png"
        assert post.media_size == len(post.media_data)
        assert sniff_mime(post.media_data) == "image/png"


def test_art_png_is_a_valid_png():
    data = _art_png((255, 0, 0), (0, 0, 255), (255, 255, 0), size=32)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
