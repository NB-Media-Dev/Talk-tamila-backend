from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Date, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.common.models.social import Profile
    from app.common.models.story import Story

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    mobile_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("admin", "influencer", "freelancer", native_enum=False, length=20),
        default="influencer",
        nullable=False,
    )
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reset_otp: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    reset_otp_expires: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reset_otp_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reset_otp_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    @property
    def id(self) -> int:
        return self.user_id

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @full_name.setter
    def full_name(self, value: str):
        if value:
            parts = value.strip().split(" ", 1)
            self.first_name = parts[0]
            self.last_name = parts[1] if len(parts) > 1 else ""

    @property
    def hashed_password(self) -> str:
        return self.password

    @hashed_password.setter
    def hashed_password(self, value: str):
        self.password = value

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def followers_count(self) -> int:
        return self.profile.followers_count if self.profile else 0

    @property
    def avatar_url(self) -> Optional[str]:
        return self.profile.profile_pic_url if self.profile else None

    @avatar_url.setter
    def avatar_url(self, value: Optional[str]):
        from app.common.models.social import Profile
        if not self.profile:
            self.profile = Profile(user_id=self.user_id, account_type=self.role)
        self.profile.profile_pic_url = value

    @property
    def bio(self) -> Optional[str]:
        return self.profile.bio if self.profile else None

    @property
    def location(self) -> Optional[str]:
        return self.profile.location if self.profile else None

    profile: Mapped[Optional["Profile"]] = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    stories: Mapped[list["Story"]] = relationship("Story", back_populates="owner", cascade="all, delete-orphan")
