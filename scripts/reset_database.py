"""Reset the database so every new user gets a clean, first-day experience.

Keeps: the admin account(s).
Deletes: every other user, post, story, message, follow, notification, report, token.
Optional: --with-demo adds sample creators and posts so the app does not look empty.

Run from the backend folder (the one that has .env):

    python scripts/reset_database.py                  # admin only
    python scripts/reset_database.py --with-demo      # admin + demo creators and posts
    python scripts/reset_database.py --dry-run        # only show what would be deleted

This cannot be undone. The script therefore:
  1. shows which database it will wipe and how many rows each table has,
  2. saves a backup with mysqldump first (needs mysqldump installed),
  3. makes you type the database name to confirm.
"""

import argparse
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.utils.db_reset import count_rows, reset_to_admin_only  # noqa: E402

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


def _backup(url) -> Path:
    """Dump the whole database to backups/. Aborts the reset if this fails."""
    dump = shutil.which("mysqldump")
    if dump is None:
        sys.exit(
            "mysqldump was not found, so I cannot make a backup.\n"
            "Install the MySQL client tools, or re-run with --skip-backup if you accept the risk."
        )
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"{url.database}-{datetime.now():%Y%m%d-%H%M%S}.sql"
    cmd = [
        dump,
        f"--host={url.host}",
        f"--port={url.port or 3306}",
        f"--user={url.username}",
        "--single-transaction",
        "--no-tablespaces",
        f"--result-file={target}",
    ]
    if settings.DATABASE_SSL_CA:
        cmd.append(f"--ssl-ca={settings.DATABASE_SSL_CA}")
    cmd.append(url.database)
    env = {**os.environ, "MYSQL_PWD": url.password or ""}  # keeps the password off the command line
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"Backup failed, nothing was deleted.\n{result.stderr.strip()}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--with-demo", action="store_true", help="add demo creators and posts after the reset")
    parser.add_argument("--demo-password", help="password for demo accounts (default: random, printed once)")
    parser.add_argument("--dry-run", action="store_true", help="show row counts and stop")
    parser.add_argument("--skip-backup", action="store_true", help="do NOT back up first (dangerous)")
    parser.add_argument("--confirm-db", help="database name, to skip the typing prompt (for scripts)")
    args = parser.parse_args()

    url = make_url(settings.DATABASE_URL)
    is_mysql = url.get_backend_name() in ("mysql", "mariadb")
    target = f"{url.host or 'local file'} / {url.database}"

    print(f"Environment : {settings.ENVIRONMENT}")
    print(f"Database    : {target}\n")

    Base.metadata.create_all(bind=engine)  # make sure the tables exist before counting
    with SessionLocal() as db:
        counts = count_rows(db)
    for name, n in counts.items():
        print(f"  {name:<24}{n:>8}")
    print()
    if args.dry_run:
        print("Dry run: nothing was changed.")
        return

    typed = args.confirm_db
    if typed is None:
        typed = input(f"This deletes everything except the admin. Type the database name ({url.database}) to continue: ")
    if typed.strip() != url.database:
        sys.exit("Name did not match. Nothing was changed.")

    if args.skip_backup:
        print("Skipping backup (--skip-backup).")
    elif is_mysql:
        print(f"Backup saved: {_backup(url)}")
    else:
        print("Backup skipped: automatic backup only supports MySQL.")

    with SessionLocal() as db:
        kept = reset_to_admin_only(db)
    print(f"Reset complete. Admin kept: {', '.join(kept) or 'none'}")

    if args.with_demo:
        from app.utils.demo_content import DEMO_CREATORS, add_demo_content

        password = args.demo_password or secrets.token_urlsafe(9)
        with SessionLocal() as db:
            made = add_demo_content(db, password)
        if made is None:
            print("Demo accounts already exist, so none were added.")
        else:
            print(
                f"Demo content added: {made['users']} creators, {made['posts']} posts, "
                f"{made['likes']} likes, {made['comments']} comments, {made['votes']} poll votes."
            )
            print(f"\nDemo accounts (password for all: {password})")
            for username, first, last, role, *_ in DEMO_CREATORS:
                print(f"  {username:<12}{first} {last}  [{role}]")
            print("Save that password now; it is not stored anywhere in plain text.")


if __name__ == "__main__":
    main()
