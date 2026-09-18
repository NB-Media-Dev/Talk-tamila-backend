import random
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.common.models.user import User
from app.common.models.social import Profile
from app.common.schemas.auth import RegisterRequest
from app.core.security import create_access_token, get_password_hash, verify_password


class AuthService:
    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[User]:
        user = AuthService.get_by_username(db, username)
        if not user:
            user = AuthService.get_by_email(db, username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
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
        else:
            existing_user = db.query(User).filter(User.mobile_no == mob).first()
            if existing_user and existing_user.email != data.email:
                mob = f"987{random.randint(1000000, 9999999)}"

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