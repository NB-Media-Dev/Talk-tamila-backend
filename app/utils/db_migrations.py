"""Safe, repeatable schema patches applied at startup.

`Base.metadata.create_all` creates missing tables but never alters existing ones, so
older databases get their new columns/indexes here. Every statement can be run any number
of times: "already exists" errors are expected and silent, anything else is logged.
"""
import logging
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger("talktamila.migrations")

# MySQL error codes that just mean "this change was already applied".
_ALREADY_APPLIED = {
    1050,  # table exists
    1060,  # duplicate column name
    1061,  # duplicate key name
    1091,  # can't drop - doesn't exist
    1826,  # duplicate foreign key constraint name
    1022,  # duplicate key
}

STARTUP_STATEMENTS: tuple[str, ...] = (
    # --- stories / music
    "ALTER TABLE stories MODIFY COLUMN media_type VARCHAR(20) NOT NULL DEFAULT 'image'",
    "ALTER TABLE stories MODIFY COLUMN media_url LONGTEXT NOT NULL",
    "ALTER TABLE stories MODIFY COLUMN caption LONGTEXT NULL",
    "ALTER TABLE stories MODIFY COLUMN music_url LONGTEXT NULL",
    "ALTER TABLE stories MODIFY COLUMN music_thumbnail LONGTEXT NULL",
    "ALTER TABLE stories ADD COLUMN username VARCHAR(100) NULL",
    "ALTER TABLE stories ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE stories ADD COLUMN deleted_at DATETIME NULL",
    "ALTER TABLE stories ADD COLUMN reply LONGTEXT NULL",
    "ALTER TABLE music_tracks ADD COLUMN language VARCHAR(50) DEFAULT 'Tamil'",
    "ALTER TABLE music_tracks ADD COLUMN genre VARCHAR(50) DEFAULT 'Tamil'",
    "ALTER TABLE music_tracks ADD COLUMN is_trending BOOLEAN DEFAULT TRUE",
    "ALTER TABLE music_tracks ADD COLUMN cover_url VARCHAR(500) NULL",
    "ALTER TABLE music_tracks ADD COLUMN duration_seconds FLOAT DEFAULT 60.0",
    # --- users / profiles
    "ALTER TABLE users ADD COLUMN reset_otp VARCHAR(6) NULL",
    "ALTER TABLE users ADD COLUMN reset_otp_expires DATETIME NULL",
    "ALTER TABLE users ADD COLUMN reset_otp_verified BOOLEAN DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN reset_otp_attempts INT NOT NULL DEFAULT 0",
    "ALTER TABLE users MODIFY COLUMN reset_otp VARCHAR(64) NULL",
    "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE profiles MODIFY COLUMN profile_pic_url LONGTEXT NULL",
    "ALTER TABLE profiles ADD COLUMN username VARCHAR(100) NULL",
    # --- story activity names
    "ALTER TABLE story_views ADD COLUMN story_sender VARCHAR(100) NULL",
    "ALTER TABLE story_views ADD COLUMN viewed_by VARCHAR(100) NULL",
    "ALTER TABLE story_likes ADD COLUMN liked_by VARCHAR(100) NULL",
    "ALTER TABLE story_likes ADD COLUMN user_name VARCHAR(100) NULL",
    "ALTER TABLE story_replies ADD COLUMN sender_name VARCHAR(100) NULL",
    "ALTER TABLE story_replies ADD COLUMN receiver_name VARCHAR(100) NULL",
    "ALTER TABLE follows ADD COLUMN user_name VARCHAR(100) NULL",
    # --- direct messages
    "ALTER TABLE direct_messages ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'text'",
    "ALTER TABLE direct_messages ADD COLUMN story_id INT NULL",
    "ALTER TABLE direct_messages ADD CONSTRAINT fk_direct_messages_story "
    "FOREIGN KEY (story_id) REFERENCES stories(story_id) ON DELETE SET NULL",
    # --- scheduled posts
    "ALTER TABLE posts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'published'",
    "ALTER TABLE posts ADD COLUMN scheduled_at DATETIME NULL",
    "ALTER TABLE posts ADD COLUMN published_at DATETIME NULL",
    "UPDATE posts SET published_at = created_at WHERE status = 'published' AND published_at IS NULL",
    "CREATE INDEX idx_posts_status_scheduled ON posts (status, scheduled_at)",
    "CREATE INDEX idx_posts_published_at ON posts (published_at, post_id)",
)


def _error_code(exc: DBAPIError) -> int:
    args = getattr(exc.orig, "args", ())
    return args[0] if args and isinstance(args[0], int) else 0


def apply_startup_migrations(engine: Engine, statements: Iterable[str] = STARTUP_STATEMENTS) -> None:
    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except DBAPIError as exc:
            if _error_code(exc) in _ALREADY_APPLIED:
                continue
            logger.warning("Startup migration skipped: %s -> %s", stmt[:80], exc.orig)