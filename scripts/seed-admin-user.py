#!/usr/bin/env python3
"""Upsert default admin from backend/.env — bootstrap only (install wizard / --bootstrap)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))
(BACKEND_DIR / "data").mkdir(parents=True, exist_ok=True)

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.admin_bootstrap import upsert_bootstrap_admin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap admin user from DEFAULT_ADMIN_* in .env")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Create admin or overwrite password from .env (install wizard). "
        "Without this flag, only creates admin if missing — never resets an existing password.",
    )
    args = parser.parse_args()

    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        action = upsert_bootstrap_admin(db, force=args.bootstrap, settings=settings)
        if action == "skipped":
            print(
                f"[seed-admin-user] Admin {settings.default_admin_username!r} already exists — "
                "password unchanged (use --bootstrap to force sync from .env)"
            )
        else:
            print(f"[seed-admin-user] Admin {settings.default_admin_username!r} {action} from DEFAULT_ADMIN_*")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
