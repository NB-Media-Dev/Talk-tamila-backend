from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import create_access_token, get_password_hash, hash_password, verify_password

# `dependencies` imports the User model, and the User model imports
# app.core.database. Loading `dependencies` eagerly here made that a circular
# import whenever the models were imported first. It is now loaded lazily, on
# first use, so `from app.core import get_current_user` still works.
_LAZY_DEPENDENCIES = {
    "get_db",
    "get_current_user",
    "get_optional_current_user",
    "get_current_admin",
}


def __getattr__(name: str):
    if name in _LAZY_DEPENDENCIES:
        from app.core import dependencies

        return getattr(dependencies, name)
    raise AttributeError(f"module 'app.core' has no attribute {name!r}")


__all__ = [
    "settings",
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "get_current_user",
    "get_optional_current_user",
    "get_current_admin",
    "create_access_token",
    "get_password_hash",
    "hash_password",
    "verify_password",
]