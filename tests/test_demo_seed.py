from datetime import timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.models import Post, PostComment, PostLike, PostMedia, PostPollOption, PostPollVote, Profile, User
from app.common.models.post import _utc_now
from app.core.database import Base
from app.utils.seed import DEMO_KEY_PREFIX, remove_demo_posts, seed_db_data, seed_demo_posts


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    with sessionmaker(bind=engine)() as session:
        seed_db_data(session)
        yield session


def _count(db, *where):
    return db.scalar(select(func.count(Post.post_id)).where(*where))


def _real_post(db, user, text="my own real post"):
    post = Post(user_id=user.user_id, post_type="text", content=text, status="published",
                created_at=_utc_now(), published_at=_utc_now())
    db.add(post)
    db.commit()
    return post


def test_seed_creates_variety_and_is_idempotent(db):
    first = seed_demo_posts(db)
    assert 8 <= first <= 12
    assert seed_demo_posts(db) == 0
    assert seed_demo_posts(db) == 0
    assert _count(db, Post.demo_key.like(f"{DEMO_KEY_PREFIX}%")) == first
    posts = db.execute(select(Post).where(Post.demo_key.is_not(None))).scalars().all()
    assert len({p.demo_key for p in posts}) == first
    assert {"text", "image", "poll"} <= {p.post_type for p in posts}
    assert any(len(p.extra_media) >= 2 for p in posts)                      # carousel
    assert any(p.post_type == "poll" and len(p.poll_options) >= 2 for p in posts)
    assert all(p.status == "published" and p.published_at is not None for p in posts)
    assert all(p.media_data[:8] == b"\x89PNG\r\n\x1a\n" for p in posts if p.media_mime)
    assert any(any("\u0b80" <= ch <= "\u0bff" for ch in p.content) for p in posts)  # Tamil
    assert any("Marina sunset vibes" in p.content for p in posts)                    # English
    # inside the feed's 14-day discover window
    assert all(p.published_at >= _utc_now() - timedelta(days=13) for p in posts)
    assert db.scalar(select(func.count(PostLike.like_id))) > 0
    assert db.scalar(select(func.count(PostComment.comment_id))) > 0
    assert db.scalar(select(func.count(PostPollVote.vote_id))) > 0


def test_posts_count_matches_real_rows_and_does_not_double_count(db):
    seed_demo_posts(db)
    seed_demo_posts(db)
    for profile in db.execute(select(Profile)).scalars():
        actual = _count(db, Post.user_id == profile.user_id)
        assert profile.posts_count == actual


def test_partial_run_is_completed_on_retry(db):
    total = seed_demo_posts(db)
    victims = db.execute(select(Post).where(Post.demo_key.is_not(None)).limit(3)).scalars().all()
    for post in victims:   # simulate a run that died halfway for three posts
        db.query(PostLike).filter_by(post_id=post.post_id).delete()
        db.query(PostComment).filter_by(post_id=post.post_id).delete()
        db.query(PostMedia).filter_by(post_id=post.post_id).delete()
        db.query(PostPollVote).filter_by(post_id=post.post_id).delete()
        db.query(PostPollOption).filter_by(post_id=post.post_id).delete()
        db.delete(post)
    db.commit()
    assert seed_demo_posts(db) == 3
    assert _count(db, Post.demo_key.is_not(None)) == total


def test_real_posts_are_never_touched_by_seed_refresh_or_remove(db):
    author = db.execute(select(User).where(User.username == "Arjun")).scalar_one()
    real = _real_post(db, author, "caption identical to nothing in the seed")
    lookalike = _real_post(db, author, "Tip for new creators: post a little every day.")
    seed_demo_posts(db)
    seed_demo_posts(db, refresh_dates=True)
    before = (real.content, real.created_at, real.published_at)
    removed = remove_demo_posts(db)
    assert removed >= 8
    db.expire_all()
    assert _count(db, Post.demo_key.is_not(None)) == 0
    kept = db.get(Post, real.post_id)
    assert (kept.content, kept.created_at, kept.published_at) == before
    assert db.get(Post, lookalike.post_id) is not None
    assert remove_demo_posts(db) == 0


def test_a_real_post_with_a_demo_like_caption_is_not_removed(db):
    author = db.execute(select(User).where(User.username == "Priya")).scalar_one()
    seed_demo_posts(db)
    caption = db.scalar(select(Post.content).where(Post.demo_key == f"{DEMO_KEY_PREFIX}text-vanakkam"))
    twin = _real_post(db, author, caption)
    remove_demo_posts(db)
    assert db.get(Post, twin.post_id) is not None


def test_refresh_dates_only_moves_demo_posts(db):
    author = db.execute(select(User).where(User.username == "Arjun")).scalar_one()
    old_real = _real_post(db, author)
    old_real.published_at = old_real.created_at = _utc_now() - timedelta(days=100)
    db.commit()
    seed_demo_posts(db)
    db.query(Post).filter(Post.demo_key.is_not(None)).update(
        {"published_at": _utc_now() - timedelta(days=90), "created_at": _utc_now() - timedelta(days=90)}
    )
    db.commit()
    assert seed_demo_posts(db, refresh_dates=True) == 0
    db.expire_all()
    demo = db.execute(select(Post).where(Post.demo_key.is_not(None))).scalars().all()
    assert all(p.published_at >= _utc_now() - timedelta(days=13) for p in demo)
    assert db.get(Post, old_real.post_id).published_at < _utc_now() - timedelta(days=99)


def test_seeded_posts_come_through_the_real_feed_and_profile_api(db):
    from app.common.services.post_service import PostService
    seed_demo_posts(db)
    viewer = db.execute(select(User).where(User.username == "admin")).scalar_one()
    feed = PostService.get_feed(db, viewer, 30, None)
    assert len(feed.items) >= 8
    ids = [p.post_id for p in feed.items]
    assert len(ids) == len(set(ids))                       # no duplicates
    stamps = [p.published_at for p in feed.items] if hasattr(feed.items[0], "published_at") else None
    if stamps:
        assert stamps == sorted(stamps, reverse=True)       # newest first
    profile = PostService.get_user_posts("freelancer", db, viewer)
    assert len(profile.items) >= 1
