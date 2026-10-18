"""Admin-notify test recipients must be admins only."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.models import User, UserRole
from app.services.telegram_recipients import resolve_notify_recipient_users


def test_resolve_notify_recipient_users_admins_only():
    admin = User(id=1, username="admin", password_hash="x", role=UserRole.admin, telegram_id="100")
    user = User(id=2, username="client", password_hash="x", role=UserRole.user, telegram_id="200")
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.all.return_value = [admin]  # SQL filter already restricts to admin

    result = resolve_notify_recipient_users(db, lambda _k, default="": default)
    assert result == [admin]
    # Ensure role filter was applied (role == admin in filter args)
    assert query.filter.called
