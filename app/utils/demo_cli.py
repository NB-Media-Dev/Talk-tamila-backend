"""Manage demo posts by hand.

    python -m app.utils.demo_cli status
    python -m app.utils.demo_cli seed                  # add the missing demo posts
    python -m app.utils.demo_cli seed --refresh-dates  # also make existing ones "recent" again
    python -m app.utils.demo_cli remove                # delete ONLY posts with a demo key

Production and hosted databases need --allow-production, so it can never happen by accident.
Real posts have no demo key and are never changed or deleted.
"""
import argparse
import sys

from sqlalchemy import func, select

from app.common.models import Post
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.utils.db_migrations import apply_startup_migrations
from app.utils.seed import DEMO_KEY_PREFIX, remove_demo_posts, seed_db_data, seed_demo_posts


def _is_protected() -> bool:
    return settings.is_production or "aivencloud.com" in settings.DATABASE_URL


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed, refresh or remove Talk Tamila demo posts.")
    parser.add_argument("command", choices=["status", "seed", "remove"])
    parser.add_argument("--refresh-dates", action="store_true", help="seed: move existing demo posts to 'recent'")
    parser.add_argument("--allow-production", action="store_true", help="required for production / hosted databases")
    args = parser.parse_args(argv)

    if args.command != "status" and _is_protected() and not args.allow_production:
        print("Refusing: this looks like a production/hosted database. Re-run with --allow-production if you are sure.")
        return 2

    Base.metadata.create_all(bind=engine)
    apply_startup_migrations(engine)

    with SessionLocal() as db:
        if args.command == "status":
            total = db.scalar(select(func.count(Post.post_id)))
            demo = db.scalar(select(func.count(Post.post_id)).where(Post.demo_key.like(f"{DEMO_KEY_PREFIX}%")))
            print(f"posts: {total} total, {demo} demo, {total - demo} real")
        elif args.command == "seed":
            if not _is_protected():
                seed_db_data(db)  # sample users (known passwords), only on a local DB with no users
            print(f"demo posts added: {seed_demo_posts(db, refresh_dates=args.refresh_dates)}")
        else:
            print(f"demo posts removed: {remove_demo_posts(db)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
