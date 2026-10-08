-- Post scheduling (MySQL). The app applies these automatically on startup and it is safe to
-- run them again. Run this file by hand only if you prefer to migrate manually.
-- A "duplicate column" / "duplicate key name" error just means that step was already done.

ALTER TABLE posts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'published';
ALTER TABLE posts ADD COLUMN scheduled_at DATETIME NULL;
ALTER TABLE posts ADD COLUMN published_at DATETIME NULL;

-- Existing posts are already live: their publish time is their creation time.
UPDATE posts SET published_at = created_at WHERE status = 'published' AND published_at IS NULL;

CREATE INDEX idx_posts_status_scheduled ON posts (status, scheduled_at);
CREATE INDEX idx_posts_published_at ON posts (published_at, post_id);