"""Put the database back to a clean "first day" state.

After a reset the database holds ONLY the admin account(s). Every other user,
post, story, message, follow, notification, report and token is deleted, so
each person who signs up afterwards starts with a completely fresh account.

This module only changes data. The command that asks for confirmation and makes
a backup first is `scripts/reset_database.py` - use that, not this, by hand.
"""

import logging
from typing import Dict, List

from sqlalchemy import MetaData, func, select, text
from sqlalchemy.orm import Session

from app.common.models import Profile, User
from app.utils.admin_bootstrap import ensure_admin_user

logger = logging.getLogger("talktamila.reset")

# Tables whose rows must never be deleted (schema bookkeeping, not app data).
PROTECTED_TABLES = frozenset({"alembic_version"})
# Tables that are cleaned row by row so the admin survives.
USER_TABLES = frozenset({"users", "profiles"})


def _reflect(db: Session) -> MetaData:
    """Read the tables that really exist in the database.

    Reflecting (instead of using our model list) also catches tables that were
    created by migrations but have no model, such as `refresh_tokens`. Those
    would otherwise block deleting users.
    """
    meta = MetaData()
    meta.reflect(bind=db.get_bind())
    return meta


def count_rows(db: Session) -> Dict[str, int]:
    """Row count of every app table (what a reset would remove or keep)."""
    meta = _reflect(db)
    counts: Dict[str, int] = {}
    for table in meta.sorted_tables:
        if table.name in PROTECTED_TABLES:
            continue
        counts[table.name] = db.execute(select(func.count()).select_from(table)).scalar_one()
    return counts


def _is_mysql(db: Session) -> bool:
    return db.get_bind().dialect.name in ("mysql", "mariadb")


def reset_to_admin_only(db: Session) -> List[str]:
    """Delete everything except admin accounts. Returns the kept admin usernames.

    Admin accounts keep their login but lose their own posts, messages and
    stats, so the admin also starts fresh. If no admin exists, one is created
    the same way the app does at startup.
    """
    meta = _reflect(db)
    mysql = _is_mysql(db)
    emptied: List[str] = []

    if mysql:
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    try:
        admin_ids = [
            uid for (uid,) in db.execute(select(User.user_id).where(User.role == "admin")).all()
        ]

        # Children before parents. Order matters on databases that enforce foreign keys.
        for table in reversed(meta.sorted_tables):
            name = table.name
            if name in PROTECTED_TABLES:
                continue
            if name == "users":
                stmt = table.delete().where(table.c.role != "admin")
            elif name == "profiles":
                stmt = (
                    table.delete().where(table.c.user_id.not_in(admin_ids))
                    if admin_ids
                    else table.delete()
                )
            else:
                stmt = table.delete()
                emptied.append(name)
            db.execute(stmt)

        # Clean slate for the admin's own counters and any half-finished password reset.
        if admin_ids:
            db.execute(
                Profile.__table__.update()
                .where(Profile.user_id.in_(admin_ids))
                .values(
                    followers_count=0,
                    following_count=0,
                    posts_count=0,
                    total_reach=0,
                    total_earned=0,
                )
            )
            db.execute(
                User.__table__.update()
                .where(User.user_id.in_(admin_ids))
                .values(
                    reset_otp=None,
                    reset_otp_expires=None,
                    reset_otp_verified=False,
                    reset_otp_attempts=0,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if mysql:
            db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            db.commit()

    if mysql:
        _restart_id_counters(db, meta)

    ensure_admin_user(db)
    kept = [u for (u,) in db.execute(select(User.username).where(User.role == "admin")).all()]
    logger.info("Reset done. Admin accounts kept: %s", ", ".join(kept) or "none")
    return kept


def _restart_id_counters(db: Session, meta: MetaData) -> None:
    """MySQL keeps counting ids after DELETE; make the next new user id small again."""
    quote = db.get_bind().dialect.identifier_preparer.quote
    for table in meta.sorted_tables:
        if table.name in PROTECTED_TABLES:
            continue
        try:
            db.execute(text(f"ALTER TABLE {quote(table.name)} AUTO_INCREMENT = 1"))
        except Exception:  # tables without an auto-increment column
            db.rollback()
    db.commit()
