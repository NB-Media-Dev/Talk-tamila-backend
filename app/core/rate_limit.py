"""Small in-memory rate limiter for login and OTP endpoints.

Counts are kept per process. That already stops simple brute forcing; if you run many
server instances, put a shared limiter (e.g. Redis) in front for a hard guarantee.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings

_lock = threading.Lock()
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # The right-most X-Forwarded-For entry is the one added by our own proxy (Railway).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, max_calls: int, window_seconds: int) -> Callable[[Request], None]:
    """FastAPI dependency: allow `max_calls` per `window_seconds` per client IP."""

    def _check(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        key = f"{name}:{_client_ip(request)}"
        now = time.monotonic()
        with _lock:
            window = _hits[key]
            while window and now - window[0] > window_seconds:
                window.popleft()
            if len(window) >= max_calls:
                retry_after = max(1, int(window_seconds - (now - window[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)

    return _check


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()