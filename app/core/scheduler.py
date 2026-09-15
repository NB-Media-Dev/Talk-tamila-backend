import logging
from datetime import datetime, timezone
from app.core.database import SessionLocal

logger = logging.getLogger("talktamila.scheduler")


def clean_expired_stories() -> int:
    logger.info("Stories expiration scheduler checked at %s", datetime.now(timezone.utc).isoformat())
    return 0
