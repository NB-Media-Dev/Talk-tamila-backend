# Talk Tamila – Backend (FastAPI)

## How the code is organised

Every request travels through the same four layers. Each layer has one job.

| Layer | Where | Its job |
|---|---|---|
| **Route** | `app/<feature>/routes.py` | Receives the HTTP request, checks who is calling, hands the work to a service. No business logic. |
| **Schema** | `app/common/schemas/<feature>.py` | Describes the shape of request and response data. |
| **Service** | `app/common/services/` | The actual rules and database work for one operation. |
| **Model** | `app/common/models/<feature>.py` | The database tables. |

## One name, everywhere

A route handler and the service method it calls have **the same name**.
`POST /messages/thread/{user_id}/block` is handled by `block_user` in
`app/message/routes.py`, and `block_user` does the work in
`MessageService` (`app/common/services/message_service.py`).
Search the name once and you find both.

## Finding the code for an endpoint (Postman → code)

1. Open `docs/API_MAP.md` and search for the URL you called. Each row shows the
   handler (route file and line) and the service method (file and line).
2. Or run `python scripts/api_map.py` to print the same list in the terminal.
3. After adding or renaming an endpoint, refresh the map:
   `python scripts/api_map.py --markdown`

## Which service owns what

| Area | Service file |
|---|---|
| Sign up, login, tokens, OTP, passwords | `auth_service.py` |
| My profile, someone's public profile | `profile_service.py` |
| Posts: create, feed, schedule, edit, archive, pin, polls | `post_service.py` |
| Posts: likes, comments, saves, shares, insights | `post_engagement_service.py` |
| Messages: threads, send, block, mute, reactions | `message_service.py` |
| Browser push notifications | `push_service.py` |
| Notifications list | `notification_service.py` |
| Music search for stories | `music_service.py` |
| Stories (see below) | `story/` folder |
| Admin: moderation, bans, warnings | `app/admin/services.py` |
| Influencer dashboard numbers | `app/influencer/services.py` |

Stories are large, so they are split by what the person is doing
(`app/common/services/story/`):

| File | Operations |
|---|---|
| `story_creation_service.py` | create, upload, edit, delete, re-share |
| `story_feed_service.py` | feeds, a user's stories, one story, saved, archived |
| `story_engagement_service.py` | view, like, react, reply, share, save, report |
| `story_relationship_service.py` | mute creator, follow, suggestions |
| `story_mention_service.py` | @mention search and adding a mention |
| `story_analytics_service.py` | activity, viewers, likers, owner stats |
| `story_settings_service.py` | muted creators, close friends, followers / following lists |
| `story_helpers.py` | shared building blocks used by the files above |

## Starting fresh (clean database for new users)

A new database now starts with **only the admin account**. Nothing is
auto-created on startup any more (the old code made 10 fake users on an empty
development database).

To clean a database that already has test data:

```bash
python scripts/reset_database.py --dry-run     # look first: shows row counts, changes nothing
python scripts/reset_database.py               # admin only
python scripts/reset_database.py --with-demo   # admin + demo creators and posts
```

The script shows which database it will wipe, saves a backup in `backups/`
(needs `mysqldump`), and asks you to type the database name before deleting.
The admin keeps their password. Everything else is removed, so each person who
signs up afterwards starts with an empty account.

`--with-demo` adds 12 sample creators and 32 posts (24 text and poll posts plus
8 picture posts, with likes, comments and poll votes) so the feed does not look empty. Edit `app/utils/demo_content.py` to
change who they are and what they post. The script prints their shared password
once. Demo posts are normal data: to remove them, run the reset again without
`--with-demo`.

## Running

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in your values
uvicorn app.main:app --reload
pytest                      # run the test suite
```
