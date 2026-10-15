"""Profile operations: my own profile (read and edit) and another person's public profile."""

import re
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.models import Story, StoryLike, StoryReply, StoryView, User
from app.common.models.social import Follow
from app.common.services.auth_service import AuthService
from app.utils.media_upload import file_to_base64_data_url

AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
AVATAR_MAX_DATA_URL_CHARS = 2_800_000  # about 2 MB of image data once base64-encoded
NAME_MAX_LENGTH = 100
BIO_MAX_LENGTH = 300
LOCATION_MAX_LENGTH = 100
MOBILE_MAX_LENGTH = 20
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^\+?[0-9\s\-]{7,20}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,30}$")


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class ProfileService:
    # ------------------------------------------------------------ read my profile
    @staticmethod
    def get_my_profile(db: Session, current_user: User) -> dict:
        profile = ProfileService._profile_payload(current_user)
        profile["followers_count"] = db.query(Follow).filter(Follow.following_id == current_user.user_id).count()
        profile["following_count"] = db.query(Follow).filter(Follow.follower_id == current_user.user_id).count()
        return profile

    # ------------------------------------------------------------ edit my profile
    @staticmethod
    async def update_my_profile(
        db: Session,
        current_user: User,
        first_name: Optional[str],
        last_name: Optional[str],
        username: Optional[str],
        bio: Optional[str],
        location: Optional[str],
        email: Optional[str],
        mobile_no: Optional[str],
        avatar: Optional[UploadFile],
    ) -> dict:
        # Validate everything first, change nothing until all checks pass.
        first_name = ProfileService._validate_name(first_name, "First name", required=True)
        last_name = ProfileService._validate_name(last_name, "Last name", required=False)
        bio = ProfileService._validate_text(bio, "Bio", BIO_MAX_LENGTH)
        location = ProfileService._validate_text(location, "Location", LOCATION_MAX_LENGTH)
        email = ProfileService._validate_email(db, email, current_user)
        mobile_no = ProfileService._validate_mobile(db, mobile_no, current_user)
        username = ProfileService._validate_username(db, username, current_user)
        avatar_data_url = await ProfileService._read_avatar(avatar)

        changed_fields = {
            "first_name": first_name,
            "last_name": last_name,
            "bio": bio,
            "location": location,
            "email": email,
            "mobile_no": mobile_no,
            "avatar_url": avatar_data_url,
        }
        for field, value in changed_fields.items():
            if value is not None:
                setattr(current_user, field, value)

        if username is not None and username != current_user.username:
            ProfileService._rename_user_everywhere(db, current_user, username)

        db.commit()
        db.refresh(current_user)
        return ProfileService._profile_payload(current_user)

    # ------------------------------------------------------- read someone's profile
    @staticmethod
    def get_public_profile(db: Session, current_user: User, username: str) -> dict:
        """Public details of one person plus how they relate to me."""
        wanted_username = username.strip().lstrip("@")
        user = (
            db.query(User)
            .filter(func.lower(User.username) == wanted_username.lower(), User.is_active.is_(True))
            .first()
        )
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

        followers_count = db.query(Follow).filter(Follow.following_id == user.user_id).count()
        following_count = db.query(Follow).filter(Follow.follower_id == user.user_id).count()

        is_me = user.user_id == current_user.user_id
        is_following = False
        follows_you = False
        if not is_me:
            is_following = (
                db.query(Follow.id)
                .filter(Follow.follower_id == current_user.user_id, Follow.following_id == user.user_id)
                .first()
                is not None
            )
            follows_you = (
                db.query(Follow.id)
                .filter(Follow.follower_id == user.user_id, Follow.following_id == current_user.user_id)
                .first()
                is not None
            )

        return {
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "bio": user.bio,
            "location": user.location,
            "followers_count": followers_count,
            "following_count": following_count,
            "posts_count": user.posts_count,
            "is_following": is_following,
            "follows_you": follows_you,
            "is_me": is_me,
            "joined_at": user.created_at.isoformat() if user.created_at else None,
        }

    # ------------------------------------------------------------------- helpers
    @staticmethod
    def _profile_payload(user: User) -> dict:
        return {
            "id": user.user_id,
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "mobile_no": user.mobile_no,
            "dob": user.dob.isoformat() if user.dob else None,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "bio": user.bio,
            "location": user.location,
            "followers_count": user.followers_count,
            "following_count": user.following_count,
            "posts_count": user.posts_count,
        }

    @staticmethod
    def _validate_name(value: Optional[str], label: str, required: bool) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if required and not value:
            raise _bad_request(f"{label} cannot be empty.")
        if len(value) > NAME_MAX_LENGTH:
            raise _bad_request(f"{label} must be {NAME_MAX_LENGTH} characters or less.")
        return value

    @staticmethod
    def _validate_text(value: Optional[str], label: str, max_length: int) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if len(value) > max_length:
            raise _bad_request(f"{label} must be {max_length} characters or less.")
        return value

    @staticmethod
    def _validate_email(db: Session, value: Optional[str], me: User) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if not value or not EMAIL_RE.match(value):
            raise _bad_request("Please enter a valid email address.")
        existing = AuthService.get_by_email(db, value)
        if existing is not None and existing.user_id != me.user_id:
            raise _bad_request("This email is already registered.")
        return value

    @staticmethod
    def _validate_mobile(db: Session, value: Optional[str], me: User) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value or not MOBILE_RE.match(value):
            raise _bad_request("Please enter a valid phone number.")
        if len(value) > MOBILE_MAX_LENGTH:
            raise _bad_request(f"Phone number must be {MOBILE_MAX_LENGTH} characters or less.")
        existing = AuthService.get_by_mobile(db, value)
        if existing is not None and existing.user_id != me.user_id:
            raise _bad_request("This phone number is already registered.")
        return value

    @staticmethod
    def _validate_username(db: Session, value: Optional[str], me: User) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not USERNAME_RE.match(value):
            raise _bad_request("Username must be 3-30 characters: letters, numbers, dots and underscores only.")
        existing = AuthService.get_by_username(db, value)
        if existing is not None and existing.user_id != me.user_id:
            raise _bad_request("This username is already taken.")
        return value

    @staticmethod
    async def _read_avatar(avatar: Optional[UploadFile]) -> Optional[str]:
        if avatar is None or not avatar.filename:
            return None
        if avatar.content_type not in AVATAR_ALLOWED_TYPES:
            raise _bad_request("Avatar must be a JPG, PNG or WEBP image.")
        data_url, _ = await file_to_base64_data_url(avatar)
        if len(data_url) > AVATAR_MAX_DATA_URL_CHARS:
            raise _bad_request("Avatar must be 2 MB or smaller.")
        return data_url

    @staticmethod
    def _rename_user_everywhere(db: Session, user: User, new_username: str) -> None:
        """Keep the copies of the username stored on story rows in sync."""
        user_id = user.user_id
        user.username = new_username
        if user.profile is not None:
            user.profile.username = new_username

        my_story_ids = select(Story.story_id).where(Story.user_id == user_id)
        updates = (
            (Story, Story.user_id == user_id, {Story.username: new_username}),
            (StoryView, StoryView.user_id == user_id, {StoryView.viewed_by: new_username}),
            (StoryView, StoryView.story_id.in_(my_story_ids), {StoryView.story_sender: new_username}),
            (StoryLike, StoryLike.user_id == user_id, {StoryLike.liked_by: new_username}),
            (StoryLike, StoryLike.story_id.in_(my_story_ids), {StoryLike.user_name: new_username}),
            (StoryReply, StoryReply.user_id == user_id, {StoryReply.sender_name: new_username}),
            (StoryReply, StoryReply.story_id.in_(my_story_ids), {StoryReply.receiver_name: new_username}),
        )
        for model, condition, values in updates:
            db.query(model).filter(condition).update(values, synchronize_session=False)
