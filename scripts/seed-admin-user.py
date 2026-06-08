#!/usr/bin/env python3
"""Upsert default admin user from backend/.env (called by install.sh after wizard)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.auth import get_password_hash  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import User, UserRole  # noqa: E402


def main() -> int:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == settings.default_admin_username).first()
        if user:
            user.password_hash = get_password_hash(settings.default_admin_password)
            user.must_change_password = settings.default_admin_must_change_password
            user.is_active = True
            if user.role != UserRole.admin:
                user.role = UserRole.admin
            action = "updated"
        else:
            db.add(
                User(
                    username=settings.default_admin_username,
                    password_hash=get_password_hash(settings.default_admin_password),
                    role=UserRole.admin,
                    theme="dark",
                    must_change_password=settings.default_admin_must_change_password,
                    is_active=True,
                )
            )
            action = "created"
        db.commit()
        print(f"[seed-admin-user] Admin {settings.default_admin_username!r} {action} from DEFAULT_ADMIN_*")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
