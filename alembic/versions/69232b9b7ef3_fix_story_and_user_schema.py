"""fix_story_and_user_schema

Revision ID: 69232b9b7ef3
Revises: a9c4be670396
Create Date: 2026-09-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '69232b9b7ef3'
down_revision = 'a9c4be670396'
branch_labels = ''
depends_on = None

def upgrade() -> None:
    # Helper function to execute SQL and ignore errors if column already exists
    def safe_execute(sql):
        try:
            op.execute(sql)
        except Exception:
            pass

    # --- Stories Table Updates ---
    # We use ADD COLUMN here. If it already exists, the try-except will skip it.
    safe_execute("ALTER TABLE stories ADD COLUMN media_type VARCHAR(20) NOT NULL DEFAULT 'image'")
    safe_execute("ALTER TABLE stories ADD COLUMN media_url LONGTEXT NOT NULL")
    safe_execute("ALTER TABLE stories ADD COLUMN caption LONGTEXT NULL")
    safe_execute("ALTER TABLE stories ADD COLUMN music_url LONGTEXT NULL")
    safe_execute("ALTER TABLE stories ADD COLUMN music_thumbnail LONGTEXT NULL")
    safe_execute("ALTER TABLE stories ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE NOT NULL")
    safe_execute("ALTER TABLE stories ADD COLUMN deleted_at DATETIME NULL")

    # --- Music Tracks Table Updates ---
    safe_execute("ALTER TABLE music_tracks ADD COLUMN language VARCHAR(50) DEFAULT 'Tamil'")
    safe_execute("ALTER TABLE music_tracks ADD COLUMN genre VARCHAR(50) DEFAULT 'Tamil'")
    safe_execute("ALTER TABLE music_tracks ADD COLUMN is_trending BOOLEAN DEFAULT TRUE")
    safe_execute("ALTER TABLE music_tracks ADD COLUMN cover_url VARCHAR(500) NULL")
    # --- Users Table Updates ---
    safe_execute("ALTER TABLE users ADD COLUMN reset_otp VARCHAR(6) NULL")
    safe_execute("ALTER TABLE users ADD COLUMN reset_otp_expires DATETIME NULL")
    safe_execute("ALTER TABLE users ADD COLUMN reset_otp_verified BOOLEAN DEFAULT FALSE")
    safe_execute("ALTER TABLE users ADD COLUMN reset_otp_attempts INT NOT NULL DEFAULT 0")

    # --- Story Views Cleanup & Updates ---
    safe_execute("DELETE v1 FROM story_views v1 INNER JOIN story_views v2 WHERE v1.story_id = v2.story_id AND v1.user_id = v2.user_id AND v1.view_id > v2.view_id")
    safe_execute("ALTER TABLE story_views ADD UNIQUE INDEX uq_story_views_story_user (story_id, user_id)")
    safe_execute("ALTER TABLE story_views ADD COLUMN user_name VARCHAR(100) NULL")

    # --- Story Likes Cleanup & Updates ---
    safe_execute("DELETE l1 FROM story_likes l1 INNER JOIN story_likes l2 WHERE l1.story_id = l2.story_id AND l1.user_id = l2.user_id AND l1.story_likes_id > l2.story_likes_id")
    safe_execute("ALTER TABLE story_likes ADD UNIQUE INDEX uq_story_likes_story_user (story_id, user_id)")
    safe_execute("ALTER TABLE story_likes ADD COLUMN user_name VARCHAR(100) NULL")

    # --- Story Saves Cleanup & Updates ---
    safe_execute("DELETE s1 FROM story_saves s1 INNER JOIN story_saves s2 WHERE s1.story_id = s2.story_id AND s1.user_id = s2.user_id AND s1.save_id > s2.save_id")
    safe_execute("ALTER TABLE story_saves ADD UNIQUE INDEX uq_story_saves_story_user (story_id, user_id)")

    # --- Story Replies Updates ---
    safe_execute("ALTER TABLE story_replies ADD COLUMN user_name VARCHAR(100) NULL")

def downgrade() -> None:
    # Downgrade is left empty as these changes are destructive (adding/modifying columns)
    pass