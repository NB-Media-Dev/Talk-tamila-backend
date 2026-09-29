# Talk Tamila — Backend API

**Talk Tamila** is a Tamil-language social media and creator platform. This repository contains the **FastAPI (Python) backend** that powers authentication, stories, posts, direct messaging, wallet, campaigns, and role-based dashboards for SuperAdmins, Admins, Influencers, and Freelancers.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.10+) with Uvicorn |
| Database | MySQL 8.0 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Schemas | Pydantic v2 |
| Auth | JWT (HS256) — Access + Refresh tokens |
| Email (OTP) | Brevo (Sendinblue) HTTP API |
| Password Hashing | bcrypt via Passlib |
| Scheduling | APScheduler |
| Testing | pytest |

---

## Project Structure

```
talk-tamila-backend/
├── alembic/                    # Database migrations
│   └── versions/               # Migration scripts
├── app/
│   ├── admin/                  # Admin module (routes, schemas, services)
│   ├── common/
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── user.py         # User, Profile, Follow
│   │   │   ├── story.py        # Story, StoryView, StoryLike, StoryReply
│   │   │   ├── messaging.py    # DirectMessage, MessageReaction
│   │   │   ├── post.py         # Post, Comment, Like, Repost
│   │   │   ├── social.py       # Social interactions
│   │   │   ├── music.py        # MusicTrack
│   │   │   ├── wallet.py       # Wallet, Transaction
│   │   │   └── freelancer.py   # FreelancerProfile, Assignment
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Core business logic
│   │   │   ├── auth_service.py     # Register, login, OTP, password reset
│   │   │   ├── message_service.py  # Direct messaging, reactions, threads
│   │   │   ├── story_service.py    # Story CRUD, views, likes, replies
│   │   │   ├── post_service.py     # Posts, comments, likes, reposts
│   │   │   ├── social_service.py   # Follow, unfollow, notifications
│   │   │   ├── music_service.py    # Music tracks
│   │   │   └── notification_service.py
│   │   ├── enums.py            # Role enums (admin, influencer, freelancer)
│   │   └── routes.py           # Shared routes
│   ├── core/
│   │   ├── config.py           # Settings loaded from .env
│   │   ├── database.py         # SQLAlchemy engine & session
│   │   ├── dependencies.py     # get_db, get_current_user, role guards
│   │   ├── middleware.py       # Request logging middleware
│   │   ├── scheduler.py        # Background job scheduler
│   │   └── security.py        # JWT create/decode, password hashing
│   ├── freelancer/             # Freelancer module
│   ├── influencer/             # Influencer module
│   ├── message/                # Direct messaging module
│   │   └── routes.py           # /messages endpoints
│   ├── story/                  # Story module (public & settings routes)
│   ├── superadmin/             # SuperAdmin module
│   ├── utils/
│   │   ├── email.py            # Brevo email OTP sender
│   │   ├── sms.py              # SMS utility
│   │   ├── pagination.py       # Cursor/offset pagination helpers
│   │   └── seed.py             # Database seeding for development
│   └── main.py                 # FastAPI app entry point & auth endpoints
├── tests/                      # Pytest test suite
│   ├── conftest.py
│   ├── test_admin.py
│   ├── test_common.py
│   ├── test_freelancer.py
│   ├── test_influencer.py
│   ├── test_superadmin.py
│   ├── test_security.py
│   ├── test_story_privacy.py
│   └── test_message_reactions_and_story_messages.py
├── .env.example                # Example environment variables
├── docker-compose.yml          # MySQL via Docker for local dev
├── requirements.txt
└── alembic.ini
```

---

## API Modules & Endpoints

### Auth (`/api/v1/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/signup` | Register a new user |
| `POST` | `/register` | Alias for `/signup` |
| `POST` | `/login` | Login (JSON or form-data), returns JWT tokens |
| `GET` | `/profile` | Get current user's profile (live follower counts) |
| `GET` | `/me` | Alias for `/profile` |
| `PUT` | `/profile` | Update profile (name, bio, avatar, username, email) |
| `GET` | `/check-availability` | Check if email / username / mobile is already taken |
| `POST` | `/refresh` | Refresh access token using refresh token |
| `POST` | `/change-password/request-otp` | Send OTP to email for password change |
| `POST` | `/change-password` | Change password with OTP verification |
| `POST` | `/forgot-password` | Send OTP for password reset |
| `POST` | `/verify-otp` | Verify reset OTP |
| `POST` | `/reset-password` | Reset password with verified OTP |

### Messages (`/api/v1/messages`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/summary` | Unread count + last message (used by navbar badge) |
| `GET` | `/conversations` | List all conversations |
| `GET` | `/users` | Search all users to start a new conversation |
| `GET` | `/thread/{user_id}` | Fetch message thread with a specific user |
| `POST` | `/thread/{user_id}` | Send a message (text or story reply) |
| `PUT` | `/thread/{user_id}/read` | Mark thread as read |
| `POST` | `/react/{message_id}` | Add emoji reaction to a message |
| `DELETE` | `/react/{message_id}` | Remove emoji reaction |

### Stories (`/api/v1/`)
- Create, view, like, reply to, and share stories (24h ephemeral)
- Story privacy controls, mute/report
- Music soundtrack sync on stories

### Other Modules
- **Admin** — Content moderation, user management, approvals
- **Influencer** — Analytics, assignments, submissions, earnings
- **Freelancer** — Tasks, content submissions, earnings
- **SuperAdmin** — Platform configuration, admin management

---

## Setup & Local Development

### Prerequisites
- Python 3.10+
- MySQL 8.0 (via Docker or local install)

### 1. Clone the Repository
```bash
git clone https://github.com/NB-Media-Dev/Talk-tamila-backend.git
cd talk-tamila-backend
```

### 2. Create a Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Start MySQL via Docker
```bash
docker-compose up -d
```
This starts MySQL on port `3306` with database `talktamila`.

### 5. Configure Environment Variables
Copy the example file and fill in your values:
```bash
cp .env.example .env
```

Edit `.env`:
```env
ENVIRONMENT=development
DATABASE_URL=mysql+pymysql://root:1234@localhost:3306/talktamila
SECRET_KEY=your-strong-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
REFRESH_TOKEN_EXPIRE_MINUTES=10080

# Brevo (for OTP emails)
BREVO_API_KEY=your-brevo-api-key
```

### 6. Run Database Migrations
```bash
alembic upgrade head
```

### 7. Start the Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **Local:** `http://localhost:8000`
- **Docs (Swagger UI):** `http://localhost:8000/docs`
- **Redoc:** `http://localhost:8000/redoc`
- **Health Check:** `http://localhost:8000/health`

---

## Running Tests
```bash
pytest tests/ -v
```

---

## Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | `development` or `production` | `development` |
| `DATABASE_URL` | MySQL connection string | `mysql+pymysql://root:1234@localhost:3306/talktamila` |
| `SECRET_KEY` | JWT signing key (must be strong in production) | dev key |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL in minutes | `1440` (24h) |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | Refresh token TTL in minutes | `10080` (7 days) |
| `BREVO_API_KEY` | Brevo API key for OTP emails | — |
| `SMTP_HOST` | SMTP host (fallback email) | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USERNAME` | SMTP username | — |
| `SMTP_PASSWORD` | SMTP password | — |

> **Note:** Railway blocks SMTP ports. Use Brevo (HTTP-based) for email in production.

---

## User Roles

| Role | Description |
|---|---|
| `superadmin` | Full platform control — admin management, platform config |
| `admin` | Content moderation, user management, approvals |
| `influencer` | Content creator with analytics, earnings, assignments |
| `freelancer` | Task-based creator — submissions, reposts, earnings |

---

## Deployment

The backend is hosted on **Railway** with a live MySQL database.

Push to `main` branch on GitHub to trigger auto-deployment:
```bash
git push origin main
```

Live API base URL: configured via `BASE_URL` environment variable in Railway.

---

## License

Private — NB Media Dev. All rights reserved.
