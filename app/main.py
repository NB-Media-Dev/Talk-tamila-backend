import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin.routes import router as admin_router
from app.auth.routes import router as auth_router
from app.common.models import User
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.scheduler import post_publisher_loop
from app.freelancer.routes import router as freelancer_router
from app.influencer.routes import router as influencer_router
from app.message.calls import router as calls_router
from app.message.routes import router as message_router
from app.post.routes import router as post_router
from app.profile.routes import router as profile_router
from app.story.routes import router as story_router
from app.story.settings_routes import router as story_settings_router
from app.utils.admin_bootstrap import ensure_admin_user
from app.utils.db_migrations import apply_startup_migrations
from app.utils.seed import seed_db_data

logger = logging.getLogger("talktamila.main")


def _prepare_database() -> None:
    """Create tables, patch older databases, and make sure the first admin exists."""
    Base.metadata.create_all(bind=engine)
    apply_startup_migrations(engine)

    with SessionLocal() as db:
        if not settings.is_production and db.query(User).first() is None:
            seed_db_data(db)

    with SessionLocal() as db:
        ensure_admin_user(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(_prepare_database)
    except Exception:
        logger.exception("Database preparation failed; the API may not work until this is fixed")

    publisher = None
    if settings.POST_SCHEDULER_ENABLED:
        publisher = asyncio.create_task(post_publisher_loop())
    try:
        yield
    finally:
        if publisher is not None:
            publisher.cancel()
            try:
                await publisher
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Backend API for Talk Tamila: authentication, stories, posts, messages",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.docs_enabled else None,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    # The local-network regex is for development only.
    allow_origin_regex=None if settings.is_production else (settings.CORS_ORIGIN_REGEX or None),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {"status": "ok"}


# Every router is mounted exactly once, under /api/v1.
for _router in (
    auth_router,
    story_router,
    story_settings_router,
    message_router,
    calls_router,
    post_router,
    profile_router,
    admin_router,
    influencer_router,
    freelancer_router,
):
    app.include_router(_router, prefix=settings.API_V1_PREFIX)