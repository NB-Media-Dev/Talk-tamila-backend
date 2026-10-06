from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserBlock(Base):

    __tablename__ = "user_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_blocks_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blocker_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class ChatMute(Base):

    __tablename__ = "chat_mutes"
    __table_args__ = (
        UniqueConstraint("user_id", "partner_id", name="uq_chat_mutes_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)


class UserReport(Base):

    __tablename__ = "user_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    reported_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now_naive, nullable=False)
    