from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_token
from app.common.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _extract_token(request: Request, token: Optional[str]) -> Optional[str]:
    if token:
        return token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def _user_from_access_token(db: Session, raw_token: Optional[str]) -> Optional[User]:
    """Resolve the user for a valid *access* token, otherwise None.

    Identity comes only from a signed JWT. Refresh tokens are rejected, and
    there is no header / environment based fallback.
    """
    if not raw_token:
        return None
    try:
        payload = decode_token(raw_token)
        if payload.get("type") != "access":
            return None
        user = db.get(User, int(payload.get("sub")))
    except Exception:
        return None
    if user and user.is_active:
        return user
    return None


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    user = _user_from_access_token(db, _extract_token(request, token))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    return _user_from_access_token(db, _extract_token(request, token))


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def get_current_influencer(current_user: User = Depends(get_current_user)) -> User:
    """Allow influencers and admins."""
    if current_user.role not in ("influencer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Influencer account required",
        )
    return current_user


def get_current_freelancer(current_user: User = Depends(get_current_user)) -> User:
    """Allow freelancers and admins."""
    if current_user.role not in ("freelancer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Freelancer account required",
        )
    return current_user


def require_role(*roles: str):
    """Factory that returns a dependency enforcing any of the given roles."""
    def _dep(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles and not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles is required: {', '.join(roles)}",
            )
        return current_user
    return _dep