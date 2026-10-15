"""Demo creators and posts, so a fresh app does not look empty.

This is optional and separate from the reset. Edit the two lists below to change
who the demo creators are and what they post, then run:

    python scripts/reset_database.py --with-demo

Everything here is ordinary data (users, posts, likes, comments, follows), so the
app treats it like real activity. Real people who sign up still start with an
empty profile, no messages, no notifications and no followers.
"""

import random
import struct
import zlib
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.models import (
    Follow,
    Post,
    PostComment,
    PostLike,
    PostPollOption,
    PostPollVote,
    Profile,
    User,
)
from app.core.security import hash_password

DEMO_EMAIL_DOMAIN = "demo.talktamila.com"

# (username, first name, last name, role, location, bio)
DEMO_CREATORS: List[Tuple[str, str, str, str, str, str]] = [
    ("arjun_s", "Arjun", "Sarja", "influencer", "Chennai", "Street photography & night walks 📷"),
    ("priya_a", "Priya", "Ananthan", "influencer", "Madurai", "Food, travel and filter coffee ☕"),
    ("karthik_s", "Karthik", "Sivakumar", "influencer", "Coimbatore", "Reels editor. Cuts that hit the beat 🎬"),
    ("swathi_r", "Swathi", "Reddy", "influencer", "Hyderabad", "Fitness and honest wellness tips 💪"),
    ("vishwa_n", "Vishwa", "Nathan", "influencer", "Trichy", "Tech reviews without the hype"),
    ("deepak_r", "Deepak", "Raj", "influencer", "Salem", "Stand-up comedy in Tamil 🎤"),
    ("ananya_p", "Ananya", "Pandian", "influencer", "Puducherry", "Beaches, books and slow mornings 🌊"),
    ("rohan_m", "Rohan", "Mehra", "influencer", "Bengaluru", "Startup stories and weekend rides 🏍️"),
    ("amrita_i", "Amrita", "Iyer", "influencer", "Chennai", "Bharatanatyam dancer. Teaching on weekends 💃"),
    ("meena_d", "Meena", "Devi", "freelancer", "Chennai", "Freelance designer. Logos, posters, reels"),
    ("sathish_k", "Sathish", "Kumar", "freelancer", "Tirunelveli", "Video editor and colourist. DMs open"),
    ("nisha_b", "Nisha", "Balan", "freelancer", "Chennai", "Copywriter. Tamil and English captions"),
]

# (author username, hours ago, post type, text, poll options)
DEMO_POSTS: List[Tuple[str, float, str, str, List[str]]] = [
    ("arjun_s", 1.5, "text", "Marina at 5 AM is a different city. Quiet, cool, and the only crowd is the fishermen. Worth waking up for.", []),
    ("priya_a", 2.5, "text", "Found a tiny tiffin place in Madurai where the idli is softer than my pillow. Jigarthanda after, obviously. 😋", []),
    ("karthik_s", 4, "poll", "Which edit style do you want more of on my reels?", ["Fast beat cuts", "Slow cinematic", "Behind the scenes"]),
    ("swathi_r", 5, "text", "Day 30 of walking 8,000 steps a day. No fancy gym, no supplements. Small habits win. 💪", []),
    ("deepak_r", 6.5, "text", "My mother asked what I do for a living. I said comedy. She said, \"Yes, but what is your real job?\" 😂", []),
    ("meena_d", 8, "text", "Open for freelance work this month: logos, festival posters and reel covers. Message me with your idea!", []),
    ("vishwa_n", 9, "poll", "Next review: which phone should I test?", ["Budget under 15k", "Mid-range", "Flagship"]),
    ("ananya_p", 11, "text", "Rainy evening, a good book and hot tea. Plans cancelled, and I am not sorry. 🌧️📖", []),
    ("rohan_m", 13, "text", "Shipped our first version today after 4 months of late nights. Scary and exciting. Thank you to everyone who tested it. 🚀", []),
    ("amrita_i", 15, "text", "Teaching a new adavu batch this weekend. Basics first, always. The foundation decides how high you can go.", []),
    ("sathish_k", 18, "text", "Colour grading tip: fix skin tones first, then style everything else around them. Saves hours.", []),
    ("nisha_b", 20, "text", "A good caption does not explain the picture. It adds the one thing the picture cannot say.", []),
    ("arjun_s", 24, "text", "Chennai local train, window seat, golden hour. Some shots you cannot plan. 🚆", []),
    ("priya_a", 27, "poll", "Weekend trip idea: where should I go next?", ["Ooty", "Kodaikanal", "Pondicherry", "Yercaud"]),
    ("deepak_r", 30, "text", "Tried a new bit about Bengaluru traffic in front of 40 people. Three laughs, one cough. Progress. 🎤", []),
    ("swathi_r", 34, "text", "Reminder: rest days are part of the plan. Your body grows when you recover, not only when you train.", []),
    ("karthik_s", 38, "text", "Pro tip for editors: cut on the action, not after it. Your viewers will feel the difference without knowing why.", []),
    ("vishwa_n", 44, "text", "Battery life matters more than the camera megapixels. I will keep saying it until phone ads change.", []),
    ("meena_d", 48, "text", "Finished a poster series for a local temple festival today. Tradition plus clean layout is such a fun mix. 🎨", []),
    ("ananya_p", 52, "text", "Pondicherry in the morning smells like salt, bread and jasmine. Take the slow route. 🌸", []),
    ("rohan_m", 58, "poll", "Founders and creators: what slows you down the most?", ["Finding time", "Staying consistent", "Getting reach"]),
    ("amrita_i", 64, "text", "Rehearsal tonight, performance next week. Nervous in the best way. Wish me luck! 🙏", []),
    ("nisha_b", 70, "text", "Tamil captions are getting popular again, and I love it. Our own language has the best punchlines.", []),
    ("sathish_k", 76, "text", "Editors: back up your project files twice. Ask me how I learned this. 😅", []),
]

# (author username, hours ago, caption, (top colour, bottom colour, sun colour))
DEMO_IMAGE_POSTS: List[Tuple[str, float, str, Tuple[Tuple[int, int, int], ...]]] = [
    ("arjun_s", 3, "Golden hour never disappoints. 🌅", ((255, 140, 66), (120, 40, 90), (255, 224, 140))),
    ("priya_a", 7, "Sunset over the temple tank, Madurai. 🛕", ((255, 183, 77), (183, 58, 88), (255, 240, 200))),
    ("ananya_p", 10, "Morning light on the Pondicherry promenade. 🌊", ((120, 200, 230), (20, 90, 140), (255, 250, 220))),
    ("rohan_m", 16, "Weekend ride, no destination. 🏍️", ((90, 120, 200), (20, 30, 70), (255, 220, 120))),
    ("amrita_i", 22, "Practice hall, 6 AM. Ghungroos ready. 💃", ((230, 90, 110), (90, 20, 60), (255, 210, 160))),
    ("meena_d", 36, "New poster palette for a festival campaign. 🎨", ((60, 190, 170), (20, 70, 110), (255, 235, 150))),
    ("swathi_r", 46, "Post-workout sky. Worth the early alarm. 💪", ((250, 120, 80), (60, 40, 110), (255, 230, 170))),
    ("sathish_k", 60, "Colour grade test: teal shadows, warm skin. 🎞️", ((40, 120, 140), (15, 25, 45), (255, 190, 120))),
]


def _art_png(top, bottom, sun, size: int = 480) -> bytes:
    """A small gradient picture with a sun, as PNG bytes. Needs no image library."""
    cx, cy, radius = int(size * 0.68), int(size * 0.38), int(size * 0.14)
    rows = bytearray()
    for y in range(size):
        t = y / (size - 1)
        base = [int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)]
        row = bytearray(base * size)
        dy = y - cy
        if abs(dy) <= radius:
            half = int((radius * radius - dy * dy) ** 0.5)
            for x in range(max(0, cx - half), min(size, cx + half)):
                row[x * 3 : x * 3 + 3] = bytes(sun)
        rows += b"\x00" + row

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


_COMMENTS = [
    "Super! 🔥",
    "Well said 👏",
    "This made my day",
    "Nandri for sharing this!",
    "Love this so much ❤️",
    "Waiting for the next one!",
    "Exactly what I needed to read today",
    "Great work, keep going 🙌",
    "This is so true 😂",
    "Saved this for later",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def demo_emails() -> List[str]:
    return [f"{c[0]}@{DEMO_EMAIL_DOMAIN}" for c in DEMO_CREATORS]


def add_demo_content(db: Session, password: str, seed: int = 7) -> Optional[Dict[str, int]]:
    """Create the demo creators, posts, likes, comments, poll votes and follows.

    Returns counts of what was created, or None if demo accounts already exist
    (so running it twice never duplicates anything).
    """
    already = db.execute(select(User.user_id).where(User.email.in_(demo_emails())).limit(1)).first()
    if already is not None:
        return None

    rng = random.Random(seed)
    now = _utc_now()
    hashed = hash_password(password)

    users: Dict[str, User] = {}
    for i, (username, first, last, role, location, bio) in enumerate(DEMO_CREATORS):
        user = User(
            username=username,
            first_name=first,
            last_name=last,
            email=f"{username}@{DEMO_EMAIL_DOMAIN}",
            mobile_no=f"90000{10001 + i}",
            password=hashed,
            role=role,
            dob=date(1995, 1, 1),
            is_active=True,
        )
        db.add(user)
        users[username] = user
    db.flush()

    profiles: Dict[str, Profile] = {}
    for username, first, last, role, location, bio in DEMO_CREATORS:
        user = users[username]
        profile = Profile(
            user_id=user.user_id,
            username=username,
            account_type=role,
            bio=bio,
            location=location,
            followers_count=0,
            following_count=0,
            posts_count=0,
        )
        db.add(profile)
        profiles[username] = profile

    # Follow graph: everyone follows a handful of the others.
    names = list(users)
    for username in names:
        others = [n for n in names if n != username]
        for target in rng.sample(others, rng.randint(4, 8)):
            db.add(
                Follow(
                    follower_id=users[username].user_id,
                    following_id=users[target].user_id,
                    user_name=target,
                )
            )
            profiles[username].following_count += 1
            profiles[target].followers_count += 1

    counts = {"users": len(users), "posts": 0, "likes": 0, "comments": 0, "votes": 0}

    entries = [(a, h, t, x, o, None) for a, h, t, x, o in DEMO_POSTS]
    for author, hours_ago, caption, colours in DEMO_IMAGE_POSTS:
        entries.append((author, hours_ago, "image", caption, [], _art_png(*colours)))

    for author, hours_ago, post_type, text, options, image in entries:
        published = now - timedelta(hours=hours_ago)
        post = Post(
            user_id=users[author].user_id,
            post_type=post_type,
            content=text,
            status="published",
            published_at=published,
            created_at=published,
        )
        if image is not None:
            post.media_type = "image"
            post.media_mime = "image/png"
            post.media_size = len(image)
            post.media_data = image
        db.add(post)
        for position, label in enumerate(options):
            post.poll_options.append(PostPollOption(text=label, position=position))
        db.flush()
        profiles[author].posts_count += 1
        counts["posts"] += 1

        others = [n for n in names if n != author]
        for liker in rng.sample(others, rng.randint(3, len(others))):
            db.add(PostLike(post_id=post.post_id, user_id=users[liker].user_id, created_at=published))
            counts["likes"] += 1

        if post_type != "poll":
            for commenter in rng.sample(others, rng.randint(0, 3)):
                when = min(now, published + timedelta(minutes=rng.randint(3, 240)))
                db.add(
                    PostComment(
                        post_id=post.post_id,
                        user_id=users[commenter].user_id,
                        body=rng.choice(_COMMENTS),
                        created_at=when,
                    )
                )
                counts["comments"] += 1
        else:
            for voter in rng.sample(others, rng.randint(4, len(others))):
                option = rng.choice(post.poll_options)
                db.add(
                    PostPollVote(
                        post_id=post.post_id,
                        option_id=option.option_id,
                        user_id=users[voter].user_id,
                        created_at=published,
                    )
                )
                counts["votes"] += 1

    db.commit()
    return counts
