"""Background loop that publishes scheduled posts when their time arrives.

It runs inside the FastAPI process. Publishing is an atomic UPDATE, so running several
server instances at once cannot publish a post twice. Posts that came due while the
server was down are published on the first run after it starts.
"""
import asyncio
import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.common.services.post_service import PostService
from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger("talktamila.scheduler")


def run_publish_cycle(session_factory: Callable[[], Session] = SessionLocal) -> int:
    """Publish all due posts once. Never raises; returns how many posts went live."""
    db: Optional[Session] = None
    try:
        db = session_factory()
        count = PostService.publish_due_posts(db)
        if count:
            logger.info("Published %s scheduled post(s)", count)
        return count
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Scheduled-post publish cycle failed")
        return 0
    finally:
        if db is not None:
            db.close()


async def post_publisher_loop(
    interval_seconds: Optional[int] = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> None:
    interval = max(5, interval_seconds or settings.POST_SCHEDULER_INTERVAL_SECONDS)
    logger.info("Post scheduler started (every %ss)", interval)
    while True:
        # Run the blocking database work off the event loop.
        await asyncio.to_thread(run_publish_cycle, session_factory)
        await asyncio.sleep(interval)