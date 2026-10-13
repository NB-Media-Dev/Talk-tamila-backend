import logging
import math
import struct
import zlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.common.models import (
    Post,
    PostComment,
    PostCommentLike,
    PostLike,
    PostMedia,
    PostPollOption,
    PostPollVote,
    PostReport,
    PostSave,
    PostShare,
    PostView,
    Profile,
    Story,
    User,
)

logger = logging.getLogger("talktamila.seed")


def seed_db_data(db: Session):
    if db.query(User).first() is not None:
        return

    admin_pass = hash_password("admin123")
    creator_pass = hash_password("creator123")

    users_data = [
        ("admin@talktamila.com", "admin", "Admin", "Tamil", "admin", "9876543210"),
        ("arjun@talktamila.com", "Arjun", "Arjun", "Sarja", "influencer", "9876543211"),
        ("priya@talktamila.com", "Priya", "Priya", "Ananthan", "influencer", "9876543212"),
        ("karthik@talktamila.com", "Karthik", "Karthik", "Sivakumar", "influencer", "9876543213"),
        ("swathi@talktamila.com", "Swathi", "Swathi", "Reddy", "influencer", "9876543214"),
        ("vishwa@talktamila.com", "Vishwa", "Vishwa", "Nathan", "influencer", "9876543215"),
        ("deepak@talktamila.com", "Deepak", "Deepak", "Raj", "influencer", "9876543216"),
        ("ananya@talktamila.com", "Ananya", "Ananya", "Pandian", "influencer", "9876543217"),
        ("rohan@talktamila.com", "Rohan", "Rohan", "Mehra", "influencer", "9876543218"),
        ("amrita@talktamila.com", "Amrita", "Amrita", "Iyer", "influencer", "9876543219"),
        ("free@talktamila.com", "freelancer", "Freelance", "Creator", "freelancer", "9876543220"),
    ]

    created_users = {}
    for email, uname, fname, lname, role, phone in users_data:
        pwd = admin_pass if role == "admin" else creator_pass
        u = User(
            email=email,
            username=uname,
            first_name=fname,
            last_name=lname,
            mobile_no=phone,
            password=pwd,
            role=role,
            dob=date(1996, 6, 15),
        )
        db.add(u)
        created_users[uname] = u

    db.flush()
    for uname, u in created_users.items():
        prof = Profile(
            user_id=u.user_id,
            username=u.username,
            account_type=u.role,
            followers_count=0,
            following_count=0,
            posts_count=0,
            bio=None,
            profile_pic_url=None,
        )
        db.add(prof)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    arjun_user = created_users["Arjun"]
    s_arjun_1 = Story(
        user_id=arjun_user.user_id,
        media_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        media_type="image",
        caption="Night walk in the rain 🌧️ 💡",
        created_at=now,
        expires_at=now + timedelta(hours=24),
        music_title="Trend Beat",
        music_artist="Anirudh",
        music_url="https://actions.google.com/sounds/v1/weather/rain_heavy.ogg",
        music_duration=30.0,
    )
    s_arjun_2 = Story(
        user_id=arjun_user.user_id,
        media_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        media_type="image",
        caption="City lights shining bright! ✨",
        created_at=now + timedelta(seconds=10),
        expires_at=now + timedelta(hours=24),
        music_title="Trend Beat",
        music_artist="Anirudh",
        music_duration=30.0,
    )

    priya_user = created_users["Priya"]
    s_priya = Story(
        user_id=priya_user.user_id,
        media_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        media_type="image",
        caption="Beach vibes and sea breeze 🌊☀️",
        created_at=now + timedelta(minutes=5),
        expires_at=now + timedelta(hours=24),
        music_title="Hukum",
        music_artist="Anirudh Ravichander",
    )

    karthik_user = created_users["Karthik"]
    s_karthik = Story(
        user_id=karthik_user.user_id,
        media_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        media_type="image",
        caption="Editing a new reel today 🎥🔥",
        created_at=now + timedelta(minutes=15),
        expires_at=now + timedelta(hours=24),
        music_title="Naa Ready",
        music_artist="Thalapathy Vijay",
    )

    db.add_all([s_arjun_1, s_arjun_2, s_priya, s_karthik])
    db.commit()


# ---------------------------------------------------------------------------
# Demo posts for presentations. Every demo post carries a stable `demo_key` ("demo-v1:...").
# Seeding creates only the keys that are missing, so it can run any number of times, and
# removal deletes only rows whose key starts with DEMO_KEY_PREFIX. Real posts have no key
# and are never touched. The pictures are drawn below as small PNG landscapes and stored
# in the database like any uploaded image, so nothing depends on the internet.
# ---------------------------------------------------------------------------
_PALETTES = [
    ((255, 183, 94), (237, 117, 73), (74, 38, 64)),   # warm sunset
    ((135, 206, 235), (84, 140, 214), (30, 58, 95)),  # blue morning
    ((253, 220, 160), (244, 143, 110), (96, 52, 70)), # peach evening
    ((171, 222, 190), (84, 170, 140), (24, 74, 66)),  # green hills
    ((216, 190, 240), (150, 110, 205), (52, 36, 102)),# violet dusk
    ((255, 214, 120), (255, 150, 70), (120, 40, 40)), # golden hour
]


def _png(width: int, height: int, rows: list) -> bytes:
    """Encode a tiny RGB PNG. `rows` holds one bytes object (3 bytes per pixel) per line."""
    raw = b"".join(b"\x00" + row for row in rows)  # each line starts with filter type 0

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def _scene(index: int, width: int = 432, height: int = 540) -> bytes:
    """A simple sky, sun and hills picture. Each index gives a different look."""
    top, bottom, hill = _PALETTES[index % len(_PALETTES)]
    sun_x = width * (0.25 + 0.5 * ((index * 37) % 100) / 100)
    sun_y = height * 0.38
    sun_r = width * 0.13
    phase = index * 1.7

    # Where the hills start in every column.
    horizon = [
        height
        * (0.66 + 0.05 * math.sin(x / width * 6.0 + phase) + 0.03 * math.sin(x / width * 13.0 + phase * 2))
        for x in range(width)
    ]

    rows = []
    for y in range(height):
        t = min(1.0, y / (height * 0.7))
        sky = bytes(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        row = bytearray(sky * width)

        # the sun
        dy = y - sun_y
        if abs(dy) <= sun_r:
            half = math.sqrt(sun_r**2 - dy**2)
            left, right = max(0, int(sun_x - half)), min(width, int(sun_x + half) + 1)
            row[left * 3 : right * 3] = bytes((255, 244, 214)) * (right - left)

        # the hills (darker the further down)
        for x in range(width):
            h = horizon[x]
            if y >= h:
                shade = 1 - 0.35 * min(1.0, (y - h) / (height * 0.3))
                row[x * 3 : x * 3 + 3] = bytes((int(hill[0] * shade), int(hill[1] * shade), int(hill[2] * shade)))
        rows.append(bytes(row))

    return _png(width, height, rows)


DEMO_KEY_PREFIX = "demo-v1:"

# Newest demo post is this many minutes old; the oldest is still inside the feed's
# 14-day "recent posts from everyone" window (FEED_DISCOVER_DAYS in post_service.py).
# kind: text | image | carousel | poll.  `extra` = slide count (carousel) or poll options.
# likes = how many of the other demo people liked it; votes = poll votes per option.
_DEMO_POSTS: list[dict] = [
    {"key": "carousel-chennai-evening", "author": "Arjun", "minutes_ago": 25, "kind": "carousel", "extra": 4, "likes": 6,
     "caption": "சென்னை மாலைகள் எப்போதும் ஸ்பெஷல் தான் 🌇 Swipe through → #Chennai #Tamil",
     "comments": [("Priya", "Semma clicks! 🔥"), ("Karthik", "Super ra, keep going 👏")]},
    {"key": "text-vanakkam", "author": "Priya", "minutes_ago": 70, "kind": "text", "likes": 5,
     "caption": "வணக்கம் Talk Tamila குடும்பமே! 🙏 இந்த வாரம் நீங்கள் என்ன உருவாக்குகிறீர்கள்? Tell us below. #TamilCreators",
     "comments": [("Swathi", "Working on a new reel 🎬"), ("Deepak", "வாழ்த்துகள்! 🙌")]},
    {"key": "poll-sunday", "author": "Karthik", "minutes_ago": 150, "kind": "poll", "likes": 4,
     "caption": "ஞாயிற்றுக்கிழமை எப்படி கொண்டாடுவீர்கள்? How do you spend your Sunday?",
     "extra": ["குடும்பத்துடன்", "திரைப்படம்", "பயணம்", "தூக்கம் 😴"], "votes": [4, 3, 2, 1],
     "comments": [("Ananya", "Family time always ❤️")]},
    {"key": "image-marina-sunset", "author": "Swathi", "minutes_ago": 60 * 6, "kind": "image", "extra": 1, "likes": 7,
     "caption": "Marina sunset vibes 🌅 கடற்கரை காற்று தனி சுகம் #Chennai #Marina",
     "comments": [("Arjun", "Golden hour never disappoints 📸")]},
    {"key": "carousel-weekend-trip", "author": "Vishwa", "minutes_ago": 60 * 20, "kind": "carousel", "extra": 3, "likes": 5,
     "caption": "Weekend trip diary ✨ உங்களுக்குப் பிடித்த படம் எது? #Travel #Weekend",
     "comments": [("Amrita", "Third one! 😍"), ("Rohan", "Take me along next time 😄")]},
    {"key": "text-creator-tip", "author": "Deepak", "minutes_ago": 60 * 34, "kind": "text", "likes": 3,
     "caption": "Tip for new creators: post a little every day. தினமும் சிறிது சிறிதாக பதிவிடுங்கள் 💪 #CreatorTips",
     "comments": []},
    {"key": "poll-diwali", "author": "Ananya", "minutes_ago": 60 * 52, "kind": "poll", "likes": 4,
     "caption": "தீபாவளிக்கு எந்த லுக் போஸ்ட் செய்யட்டும்? Which festive look should I post next? #Diwali",
     "extra": ["பாரம்பரிய புடவை", "Indo-western", "Casual street style"], "votes": [5, 2, 1],
     "comments": [("Priya", "Saree look please! 🪔")]},
    {"key": "image-golden-hour", "author": "Rohan", "minutes_ago": 60 * 24 * 3, "kind": "image", "extra": 1, "likes": 5,
     "caption": "Golden hour never disappoints 📸 #Photography #GoldenHour",
     "comments": [("Swathi", "Love the colours ❤️")]},
    {"key": "carousel-photo-walk", "author": "Amrita", "minutes_ago": 60 * 24 * 5, "kind": "carousel", "extra": 5, "likes": 6,
     "caption": "Throwback to our little photo walk 🌿 இயற்கையோடு ஒரு நாள் #PhotoWalk",
     "comments": [("Vishwa", "Great memories! 🙌")]},
    {"key": "freelancer-portfolio", "author": "freelancer", "minutes_ago": 60 * 24 * 7, "kind": "image", "extra": 1, "likes": 4,
     "caption": "Poster design for a Pongal campaign 🎨 Open for new projects this month! #Design #Portfolio",
     "comments": [("Arjun", "Clean work 👌")]},
    {"key": "text-freelancer-open", "author": "freelancer", "minutes_ago": 60 * 24 * 9, "kind": "text", "likes": 3,
     "caption": "Reels editing, posters and thumbnails ✅ DM me for rates. திட்டங்களுக்கு தொடர்பு கொள்ளுங்கள் #Freelance",
     "comments": []},
]

_FALLBACK_AUTHORS = 6


def _demo_key(short: str) -> str:
    return f"{DEMO_KEY_PREFIX}{short}"[:64]


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _demo_people(db: Session) -> dict:
    """username -> User for everyone a demo post can be attributed to (active users only)."""
    wanted = {spec["author"] for spec in _DEMO_POSTS} | {
        "Arjun", "Priya", "Karthik", "Swathi", "Vishwa", "Deepak", "Ananya", "Rohan", "Amrita"
    }
    rows = db.execute(select(User).where(User.username.in_(wanted), User.is_active.is_(True))).scalars().all()
    return {u.username: u for u in rows}


def _build_demo_post(spec: dict, author: User, others: list, when: datetime, picture_index: int) -> Post:
    kind = spec["kind"]
    post = Post(
        user_id=author.user_id,
        post_type="poll" if kind == "poll" else ("text" if kind == "text" else "image"),
        content=spec["caption"],
        status="published",
        created_at=when,
        published_at=when,
        demo_key=_demo_key(spec["key"]),
    )
    if kind in ("image", "carousel"):
        slides = spec["extra"] if kind == "carousel" else 1
        first = _scene(picture_index)
        post.media_type = "image"
        post.media_mime = "image/png"
        post.media_size = len(first)
        post.media_data = first
        for position in range(1, slides):
            data = _scene(picture_index + position)
            post.extra_media.append(
                PostMedia(position=position, media_mime="image/png", media_size=len(data), media_data=data)
            )
    elif kind == "poll":
        post.poll_options = [PostPollOption(text=t, position=i) for i, t in enumerate(spec["extra"])]
    return post


def seed_demo_posts(db: Session, refresh_dates: bool = False) -> int:
    """Create the demo posts that do not exist yet. Safe to run any number of times.

    * A post is identified by its `demo_key`, never by its caption, so real posts can
      never collide with it and are never changed.
    * Each post (pictures, poll options, likes, comments, votes) is committed on its own,
      so an interrupted run leaves only complete posts and the next run finishes the rest.
    * `refresh_dates=True` moves the timestamps of the EXISTING demo posts back to "recent"
      (use it before a presentation if the demo data is more than a few days old).

    Returns how many posts were newly created.
    """
    people = _demo_people(db)
    if not people:
        # Unusual database: borrow the first few active users instead.
        fallback = db.execute(select(User).where(User.is_active.is_(True)).limit(_FALLBACK_AUTHORS)).scalars().all()
        people = {u.username: u for u in fallback}
    if not people:
        return 0
    fallback_cycle = list(people.values())

    now = _naive_utc_now()
    existing = {
        key: post_id
        for key, post_id in db.execute(
            select(Post.demo_key, Post.post_id).where(Post.demo_key.like(f"{DEMO_KEY_PREFIX}%"))
        ).all()
    }

    created = 0
    picture_index = 0
    for number, spec in enumerate(_DEMO_POSTS):
        key = _demo_key(spec["key"])
        when = now - timedelta(minutes=spec["minutes_ago"])
        slides = spec["extra"] if spec["kind"] == "carousel" else (1 if spec["kind"] == "image" else 0)
        base_picture = picture_index
        picture_index += slides  # keeps the pictures of every post stable between runs

        if key in existing:
            if refresh_dates:
                db.execute(
                    Post.__table__.update()
                    .where(Post.demo_key == key)
                    .values(created_at=when, published_at=when, status="published")
                )
                db.commit()
            continue

        author = people.get(spec["author"]) or fallback_cycle[number % len(fallback_cycle)]
        others = [u for u in people.values() if u.user_id != author.user_id]
        try:
            post = _build_demo_post(spec, author, others, when, base_picture)
            db.add(post)
            db.flush()

            for liker in others[: spec.get("likes", 0)]:
                db.add(PostLike(post_id=post.post_id, user_id=liker.user_id, created_at=when))

            for who, body in spec.get("comments", []):
                commenter = people.get(who) or (others[0] if others else author)
                db.add(PostComment(post_id=post.post_id, user_id=commenter.user_id, body=body, created_at=when))

            if spec["kind"] == "poll":
                voters = [u for u in others]
                cursor = 0
                for option, count in zip(post.poll_options, spec.get("votes", [])):
                    for _ in range(count):
                        if cursor >= len(voters):
                            break
                        db.add(PostPollVote(post_id=post.post_id, option_id=option.option_id, user_id=voters[cursor].user_id))
                        cursor += 1

            if author.profile is not None:
                author.profile.posts_count = (author.profile.posts_count or 0) + 1
            db.commit()
            created += 1
        except IntegrityError:
            # Another process created the same key at the same moment. Nothing to do.
            db.rollback()
        except Exception:
            db.rollback()
            logger.exception("Could not add demo post %s; it will be retried on the next run", key)

    if created:
        logger.info("Added %s demo posts.", created)
    return created


def remove_demo_posts(db: Session) -> int:
    """Delete ONLY posts whose demo_key starts with DEMO_KEY_PREFIX (and their likes,
    comments, votes, pictures). Returns how many posts were removed."""
    rows = db.execute(
        select(Post.post_id, Post.user_id).where(Post.demo_key.like(f"{DEMO_KEY_PREFIX}%"))
    ).all()
    if not rows:
        return 0
    ids = [r[0] for r in rows]

    comment_ids = select(PostComment.comment_id).where(PostComment.post_id.in_(ids))
    db.execute(delete(PostCommentLike).where(PostCommentLike.comment_id.in_(comment_ids)))
    for model in (PostLike, PostComment, PostPollVote, PostSave, PostShare, PostView, PostReport):
        db.execute(delete(model).where(model.post_id.in_(ids)))
    db.execute(delete(PostMedia).where(PostMedia.post_id.in_(ids)))
    db.execute(delete(PostPollOption).where(PostPollOption.post_id.in_(ids)))

    per_author: dict = {}
    for _post_id, user_id in rows:
        per_author[user_id] = per_author.get(user_id, 0) + 1
    db.execute(delete(Post).where(Post.post_id.in_(ids)))
    for user_id, count in per_author.items():
        profile = db.execute(select(Profile).where(Profile.user_id == user_id)).scalar_one_or_none()
        if profile is not None:
            profile.posts_count = max(0, (profile.posts_count or 0) - count)
    db.commit()
    return len(ids)
