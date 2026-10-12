"""Nightly idle restart: the last-run mark is saved before the panel restarts itself."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AppSetting
from app.services import nightly_idle_restart_worker as nightly
from app.services.app_setting_store import _get_setting

LAST_RUN_KEY = "nightly_idle_restart_last_run"


@pytest.fixture()
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'panel.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(nightly, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _arm(monkeypatch, fake_run) -> None:
    monkeypatch.setattr(nightly, "_is_nightly_idle_restart_enabled", lambda: True)
    monkeypatch.setattr(nightly, "cron_matches_now", lambda _expr, _now=None: True)
    monkeypatch.setattr(
        nightly,
        "get_settings",
        lambda: SimpleNamespace(
            nightly_idle_restart_cron="0 4 * * *",
            admin_panel_az_service_name="adminpanelaz.service",
        ),
    )
    monkeypatch.setattr(nightly.active_web_session_service, "cleanup_stale_for_nightly", lambda _db: None)
    monkeypatch.setattr(nightly.active_web_session_service, "count_active_sessions", lambda _db: 0)
    monkeypatch.setattr(nightly.subprocess, "run", fake_run)


def test_last_run_is_saved_before_restart(session_factory, monkeypatch):
    seen: list[str] = []

    def fake_run(cmd, **_kwargs):
        db = session_factory()
        try:
            seen.append(_get_setting(db, LAST_RUN_KEY, ""))
        finally:
            db.close()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    _arm(monkeypatch, fake_run)

    result = nightly.run_nightly_idle_restart_once()

    assert result["status"] == "restarted"
    assert len(seen) == 1
    assert seen[0] != ""


def test_naive_last_run_counts_as_this_minute(session_factory):
    now = datetime.now(timezone.utc)
    db = session_factory()
    try:
        db.add(AppSetting(key=LAST_RUN_KEY, value=now.replace(tzinfo=None).isoformat()))
        db.commit()

        assert nightly._already_ran_this_minute(db, now) is True
    finally:
        db.close()
