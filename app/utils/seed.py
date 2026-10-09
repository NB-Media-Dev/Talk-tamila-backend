import logging
import math
import struct
import zlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.common.models import (
    Post,
    PostLike,
    PostMedia,
    PostPollOption,
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
# Example posts, so the feed is never empty the first time someone opens the app.
# Runs only when there are no posts at all (see app/main.py). The pictures are drawn
# here as small PNG landscapes, so no image files or extra packages are needed.
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


def seed_demo_posts(db: Session) -> int:
    """Create a few example posts (text, poll, photo and carousels). Returns how many."""
    if db.query(func.count(Post.post_id)).scalar():
        return 0

    wanted = ["Arjun", "Priya", "Karthik", "Swathi", "Vishwa", "Deepak", "Ananya", "Rohan", "Amrita"]
    people = [u for u in db.query(User).filter(User.username.in_(wanted)).all()]
    people.sort(key=lambda u: wanted.index(u.username))
    if not people:
        people = db.query(User).filter(User.is_active.is_(True)).limit(6).all()
    if not people:
        return 0

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # (minutes ago, kind, caption, slides or poll options)
    plan = [
        (12, "carousel", "Chennai evenings hit different 🌇 Swipe through →", 4),
        (45, "text", "Vanakkam Talk Tamila family! 🙏 Share what you are creating this week.", 0),
        (130, "poll", "What is your favourite way to spend a Sunday?", ["Family time", "Movies", "Travel", "Sleep 😴"]),
        (300, "image", "Marina sunset vibes 🌅 #chennai #tamil", 1),
        (60 * 26, "carousel", "Weekend trip diary ✨ which one is your favourite?", 3),
        (60 * 52, "text", "Tip for new creators: post a little every day. Small steps add up. 💪 #creators", 0),
        (60 * 76, "image", "Golden hour never disappoints 📸", 1),
        (60 * 120, "carousel", "Throwback to our little photo walk 🌿 Swipe for more", 5),
    ]

    created = 0
    picture_index = 0
    for number, (minutes_ago, kind, caption, extra) in enumerate(plan):
        author = people[number % len(people)]
        when = now - timedelta(minutes=minutes_ago)
        post = Post(
            user_id=author.user_id,
            post_type="poll" if kind == "poll" else ("text" if kind == "text" else "image"),
            content=caption,
            status="published",
            created_at=when,
            published_at=when,
        )

        if kind in ("image", "carousel"):
            slides = extra if kind == "carousel" else 1
            first = _scene(picture_index)
            picture_index += 1
            post.media_type = "image"
            post.media_mime = "image/png"
            post.media_size = len(first)
            post.media_data = first
            for position in range(1, slides):
                data = _scene(picture_index)
                picture_index += 1
                post.extra_media.append(
                    PostMedia(position=position, media_mime="image/png", media_size=len(data), media_data=data)
                )
        elif kind == "poll":
            post.poll_options = [PostPollOption(text=t, position=i) for i, t in enumerate(extra)]

        db.add(post)
        db.flush()

        # A few likes from the other example people, so the posts look alive.
        likers = [u for u in people if u.user_id != author.user_id][: (number % 4) + 1]
        for liker in likers:
            db.add(PostLike(post_id=post.post_id, user_id=liker.user_id))

        profile = author.profile
        if profile is not None:
            profile.posts_count = (profile.posts_count or 0) + 1
        created += 1

    db.commit()
    logger.info("Added %s example posts.", created)
    return created