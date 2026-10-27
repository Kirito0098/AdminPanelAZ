"""A newer panel commit must produce one bell notification per release."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AdminPanelNotification
from app.services import panel_update_notifier as notifier

SHA = "a" * 40


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    make = sessionmaker(bind=engine)
    session = make()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _patch_git(monkeypatch, *, ahead: int = 3, ref: str | None = "origin/release/2.26.6", sha: str = SHA):
    monkeypatch.setattr(notifier, "resolve_repo_root", lambda *_a, **_k: Path("/repo"))
    monkeypatch.setattr(notifier, "fetch_remote", lambda *_a, **_k: True)
    monkeypatch.setattr(notifier, "resolve_update_ref", lambda _root: (ref, None if ref else "нет"))
    monkeypatch.setattr(notifier, "ahead_count", lambda _root, _ref: ahead)
    monkeypatch.setattr(notifier, "rev_parse", lambda _root, _ref: sha)


def test_new_commit_writes_one_readable_notification(db, monkeypatch):
    _patch_git(monkeypatch)

    result = notifier.check_panel_update(db)

    assert result is not None and result["ahead"] == 3
    row = db.query(AdminPanelNotification).one()
    assert row.title == "Вышло обновление панели"
    assert row.category == "services"
    assert "3" in row.message
    assert SHA[:8] in row.message
    assert "origin/release/2.26.6" in row.message


def test_same_commit_is_not_notified_twice(db, monkeypatch):
    _patch_git(monkeypatch)

    assert notifier.check_panel_update(db) is not None
    assert notifier.check_panel_update(db) is None
    assert db.query(AdminPanelNotification).count() == 1


def test_up_to_date_repo_stays_silent(db, monkeypatch):
    _patch_git(monkeypatch, ahead=0)

    assert notifier.check_panel_update(db) is None
    assert db.query(AdminPanelNotification).count() == 0


def test_missing_upstream_stays_silent(db, monkeypatch):
    _patch_git(monkeypatch, ref=None)

    assert notifier.check_panel_update(db) is None
    assert db.query(AdminPanelNotification).count() == 0
