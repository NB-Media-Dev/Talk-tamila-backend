ALTER TABLE story_views
    ADD COLUMN IF NOT EXISTS story_sender VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS viewed_by VARCHAR(100) NULL;

-- Backfill story_sender from stories / users table
UPDATE story_views v
JOIN stories s ON v.story_id = s.story_id
JOIN users u ON s.user_id = u.user_id
SET v.story_sender = u.username
WHERE v.story_sender IS NULL OR v.story_sender = '';

-- Backfill viewed_by from users table
UPDATE story_views v
JOIN users u ON v.user_id = u.user_id
SET v.viewed_by = u.username
WHERE v.viewed_by IS NULL OR v.viewed_by = '';

-- Drop duplicate columns in story_views
ALTER TABLE story_views
    DROP COLUMN IF EXISTS username,
    DROP COLUMN IF EXISTS user_name;



ALTER TABLE story_likes
    ADD COLUMN IF NOT EXISTS liked_by VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS user_name VARCHAR(100) NULL;

-- Backfill user_name from stories / users table (story owner who uploaded the story)
UPDATE story_likes l
JOIN stories s ON l.story_id = s.story_id
JOIN users u ON s.user_id = u.user_id
SET l.user_name = u.username
WHERE l.user_name IS NULL OR l.user_name = '';

-- Backfill liked_by from users table (user who liked the story)
UPDATE story_likes l
JOIN users u ON l.user_id = u.user_id
SET l.liked_by = u.username
WHERE l.liked_by IS NULL OR l.liked_by = '';


ALTER TABLE story_replies
    ADD COLUMN IF NOT EXISTS sender_name VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS receiver_name VARCHAR(100) NULL;

-- Remove duplicate typo column if present
ALTER TABLE story_replies
    DROP COLUMN IF EXISTS recevier_name;



