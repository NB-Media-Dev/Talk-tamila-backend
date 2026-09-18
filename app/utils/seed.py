from datetime import date, datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.common.models import User, Profile, Story


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
            account_type=u.role,
            bio=f"Hey, I am {uname} on Talk Tamila! ✨",
            followers_count=350,
            profile_pic_url="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150",
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

