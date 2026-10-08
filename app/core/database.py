import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger("talktamila.database")


def _connect_args() -> dict:
    if "aivencloud.com" not in settings.DATABASE_URL:
        return {}
    if settings.DATABASE_SSL_CA:
        # Verifies both the certificate chain and the hostname.
        return {"ssl": {"ca": settings.DATABASE_SSL_CA, "check_hostname": True}}
    logger.warning(
        "DATABASE_SSL_CA is not set: the database connection is encrypted but the "
        "server certificate is NOT verified. Set DATABASE_SSL_CA to Aiven's ca.pem."
    )
    return {"ssl": {"check_hostname": False}}


engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args(),
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()