"""Makes sure the built-in admin account always exists.

Runs on every backend start (in every environment, including production), so a fresh
database - for example a new Aiven database - always gets its admin login.

  username: admin
  email:    admin@talktamila.com
  password: admin123   (stored hashed; only used when the account is first created)

The password is only set when the account is CREATED. If you change the admin password
later (Settings -> Edit profile & change password), it is never reset back on restart.
"""
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.common.models import Profile, User
from app.core.security import hash_password

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@talktamila.com"
ADMIN_PASSWORD = "admin123"
ADMIN_FIRST_NAME = "Admin"
ADMIN_LAST_NAME = "Tamil"
ADMIN_DOB = date(1996, 6, 15)
# mobile_no must be unique, so if the first number is already taken the next one is used.
ADMIN_MOBILE_CANDIDATES = ("9876543210", "9000000001", "9000000002")


def ensure_admin_user(db: Session) -> None:
    existing = (
        db.query(User)
        .filter(or_(User.username == ADMIN_USERNAME, User.email == ADMIN_EMAIL))
        .first()
    )

    if existing is not None:
        # Never touch the password. Only make sure the account can actually be used.
        changed = False
        if existing.role != "admin":
            existing.role = "admin"
            changed = True
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            db.commit()
            print("Admin account already existed: made sure it is an active admin.")
        return

    taken = {m for (m,) in db.query(User.mobile_no).filter(User.mobile_no.in_(ADMIN_MOBILE_CANDIDATES)).all()}
    mobile = next((m for m in ADMIN_MOBILE_CANDIDATES if m not in taken), None)
    if mobile is None:
        print("Admin account NOT created: all reserved mobile numbers are already used.")
        return

    admin = User(
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        first_name=ADMIN_FIRST_NAME,
        last_name=ADMIN_LAST_NAME,
        mobile_no=mobile,
        password=hash_password(ADMIN_PASSWORD),
        role="admin",
        dob=ADMIN_DOB,
        is_active=True,
    )
    db.add(admin)
    db.flush()  # gives the new user its id, needed for the profile row
    db.add(
        Profile(
            user_id=admin.user_id,
            username=admin.username,
            account_type="admin",
            followers_count=0,
            following_count=0,
            posts_count=0,
            bio=None,
            profile_pic_url=None,
        )
    )
    db.commit()
    print("Admin account created (username: admin).")