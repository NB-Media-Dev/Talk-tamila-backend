import hashlib
import hmac
import logging
import random
import secrets
from datetime import datetime, timedelta, timezone
from app.utils.email import send_otp_email
from app.utils.sms import send_otp_sms
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.common.models.user import User
from app.common.models.social import Profile
from app.common.schemas.auth import RegisterRequest
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password


logger = logging.getLogger("talktamila.auth")

MAX_OTP_ATTEMPTS = 5


def _hash_otp(otp: str) -> str:
    """Salted hash of an OTP, so a leaked database never exposes a usable code.
    The e-mail/SMS the user receives still has the raw 6-digit code; only what
    is stored in reset_otp is hashed."""
    return hmac.new(settings.SECRET_KEY.encode(), otp.encode(), hashlib.sha256).hexdigest()


def _looks_like_mobile(identifier: str) -> bool:
    digits = identifier.replace("+", "").replace(" ", "")
    return digits.isdigit() and 7 <= len(digits) <= 15


class AuthService:
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_by_mobile(db: Session, mobile_no: str) -> Optional[User]:
        return db.query(User).filter(User.mobile_no == mobile_no).first()

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[User]:
        user = AuthService.get_by_username(db, username)
        if not user:
            user = AuthService.get_by_email(db, username)
        if not user and _looks_like_mobile(username):
            user = AuthService.get_by_mobile(db, username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        # Deliberately not checking is_active here: returning the user lets the
        # /login route tell "wrong password" apart from "account suspended" and
        # give each its own error message, instead of both looking like bad
        # credentials.
        return user

    @staticmethod
    def get_by_identifier(db: Session, identifier: str) -> Optional[User]:
        if "@" in identifier:
            return AuthService.get_by_email(db, identifier)
        if _looks_like_mobile(identifier):
            user = AuthService.get_by_mobile(db, identifier)
            if user:
                return user
        # Not an email, and not a mobile number that matched anyone —
        # treat it as a username.
        return AuthService.get_by_username(db, identifier)

    @staticmethod
    def create_otp(db: Session, identifier: str) -> None:
        user = AuthService.get_by_identifier(db, identifier)
        if not user:
            # Don't reveal whether the account exists
            return

        otp = f"{secrets.randbelow(900000) + 100000}"
        user.reset_otp = _hash_otp(otp)
        user.reset_otp_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        user.reset_otp_verified = False
        user.reset_otp_attempts = 0
        db.commit()

        # Deliver by whichever channel the identifier actually matched: SMS
        # only when the user typed their own mobile number, email otherwise
        # (including when they typed their username, since there's no phone
        # number to send to in that case).
        use_sms = "@" not in identifier and _looks_like_mobile(identifier)

        # A delivery failure must not turn into a 500, otherwise the response
        # reveals whether the account exists.
        try:
            if use_sms:
                send_otp_sms(user.mobile_no, otp)
            else:
                send_otp_email(user.email, otp)
        except Exception:
            logger.exception("Failed to deliver password-reset OTP")

    @staticmethod
    def _clear_otp(db: Session, user: User) -> None:
        user.reset_otp = None
        user.reset_otp_expires = None
        user.reset_otp_verified = False
        user.reset_otp_attempts = 0
        db.commit()

    @staticmethod
    def _check_otp_valid(db: Session, user: User, otp: str) -> None:
        invalid = HTTPException(status_code=400, detail="Invalid or expired OTP.")
        if not user.reset_otp:
            raise invalid

        if not secrets.compare_digest(user.reset_otp, _hash_otp(otp)):
            # Limit guessing: after MAX_OTP_ATTEMPTS wrong codes the OTP is void
            # and the user has to request a new one.
            attempts = (user.reset_otp_attempts or 0) + 1
            if attempts >= MAX_OTP_ATTEMPTS:
                AuthService._clear_otp(db, user)
            else:
                user.reset_otp_attempts = attempts
                db.commit()
            raise invalid

        expires = user.reset_otp_expires
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if not expires or expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    @staticmethod
    def verify_otp(db: Session, identifier: str, otp: str) -> None:
        user = AuthService.get_by_identifier(db, identifier)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        AuthService._check_otp_valid(db, user, otp)
        user.reset_otp_verified = True
        db.commit()

    @staticmethod
    def reset_password_with_otp(db: Session, identifier: str, otp: str, new_password: str) -> User:
        user = AuthService.get_by_identifier(db, identifier)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        # If verify_otp() already confirmed this exact code, don't re-check it here:
        # re-checking would spend another one of the user's limited wrong-guess
        # attempts for no reason, and could void a code that was already verified.
        if not (user.reset_otp_verified and user.reset_otp and user.reset_otp == _hash_otp(otp)):
            AuthService._check_otp_valid(db, user, otp)
        if not user.reset_otp_verified:
            raise HTTPException(status_code=400, detail="OTP not verified yet.")

        user.password = get_password_hash(new_password)
        user.reset_otp = None
        user.reset_otp_expires = None
        user.reset_otp_verified = False
        user.reset_otp_attempts = 0
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def register(db: Session, data: RegisterRequest) -> User:
        if AuthService.get_by_email(db, data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        uname = data.username
        if not uname:
            uname = data.email.split("@")[0]
        if AuthService.get_by_username(db, uname):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this username already exists.",
            )

        fname = data.first_name
        lname = data.last_name or ""
        if not fname:
            if data.full_name:
                parts = data.full_name.strip().split(" ", 1)
                fname = parts[0]
                lname = parts[1] if len(parts) > 1 else ""
            else:
                fname = uname

        mob = data.mobile_no
        if not mob:
            mob = f"987{random.randint(1000000, 9999999)}"
            while AuthService.get_by_mobile(db, mob):
                mob = f"987{random.randint(1000000, 9999999)}"
        else:
            existing_user = AuthService.get_by_mobile(db, mob)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This mobile number is already registered. Please use a different mobile number.",
                )

        role_val = data.role if data.role in ("influencer", "freelancer", "admin") else "influencer"

        hashed = get_password_hash(data.password)
        new_user = User(
            username=uname,
            email=data.email,
            password=hashed,
            first_name=fname,
            last_name=lname,
            mobile_no=mob,
            role=role_val,
            dob=data.dob,
        )
        db.add(new_user)
        db.flush()

        profile = Profile(
            user_id=new_user.user_id,
            account_type=new_user.role,
        )
        db.add(profile)
        db.commit()
        db.refresh(new_user)
        return new_user

    @staticmethod
    def generate_token_response(user: User) -> dict:
        token = create_access_token(user.id)
        user_dict = {
            "id": user.id,
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "followers_count": user.followers_count,
        }
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user_dict,
        }