-- Posts feature tables (MySQL). The app also creates these automatically on startup;
-- run this only if you prefer to create them by hand.
USE `talktamila_db`;

CREATE TABLE IF NOT EXISTS posts (
	post_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	post_type VARCHAR(20) NOT NULL, 
	content TEXT, 
	media_type VARCHAR(20), 
	media_mime VARCHAR(100), 
	media_size INTEGER, 
	media_data LONGBLOB, 
	gif_url VARCHAR(1000), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (post_id), 
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_posts_user_id ON posts (user_id);
CREATE INDEX idx_posts_created_at ON posts (created_at);

CREATE TABLE IF NOT EXISTS post_poll_options (
	option_id INTEGER NOT NULL AUTO_INCREMENT, 
	post_id INTEGER NOT NULL, 
	text VARCHAR(100) NOT NULL, 
	position INTEGER NOT NULL, 
	PRIMARY KEY (option_id), 
	FOREIGN KEY(post_id) REFERENCES posts (post_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ppo_post_id ON post_poll_options (post_id);

CREATE TABLE IF NOT EXISTS post_poll_votes (
	vote_id INTEGER NOT NULL AUTO_INCREMENT, 
	post_id INTEGER NOT NULL, 
	option_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (vote_id), 
	CONSTRAINT uq_post_poll_votes_post_user UNIQUE (post_id, user_id), 
	FOREIGN KEY(post_id) REFERENCES posts (post_id) ON DELETE CASCADE, 
	FOREIGN KEY(option_id) REFERENCES post_poll_options (option_id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_ppv_option_id ON post_poll_votes (option_id);
