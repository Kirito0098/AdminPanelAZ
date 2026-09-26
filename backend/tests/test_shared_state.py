"""Short-lived state shared by uvicorn workers: bot dialogs and Telegram OIDC login state."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models import SharedState
from app.services import shared_state
from app.services.shared_state import clear_states, delete_state, get_state, pop_state, put_state

TTL = timedelta(minutes=5)


def _factory(db_file):
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False, "timeout": 30})
    SharedState.__table__.create(engine, checkfirst=True)
    return sessionmaker(bind=engine, autoflush=False)


@pytest.fixture(params=["memory", "db"])
def backend(request, tmp_path):
    shared_state.configure_shared_state(_factory(tmp_path / "panel.db") if request.param == "db" else None)
    yield request.param
    shared_state.configure_shared_state(None)


@pytest.fixture
def db_backend(tmp_path):
    db_file = tmp_path / "panel.db"
    shared_state.configure_shared_state(_factory(db_file))
    yield db_file
    shared_state.configure_shared_state(None)


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 9, 26, 12, 0, 0)]
    monkeypatch.setattr(shared_state, "_now", lambda: now[0])
    return now


def test_put_get_overwrite_delete(backend):
    assert get_state("ns", "k") is None
    put_state("ns", "k", {"a": 1}, ttl=TTL)
    assert get_state("ns", "k") == {"a": 1}
    put_state("ns", "k", {"a": 2}, ttl=TTL)
    assert get_state("ns", "k") == {"a": 2}
    assert get_state("other", "k") is None
    delete_state("ns", "k")
    assert get_state("ns", "k") is None
    delete_state("ns", "k")


def test_keys_are_independent(backend):
    put_state("ns", "k1", {"v": 1}, ttl=TTL)
    put_state("ns", "k2", {"v": 2}, ttl=TTL)
    assert get_state("ns", "k1") == {"v": 1}
    assert get_state("ns", "k2") == {"v": 2}
    delete_state("ns", "k1")
    assert get_state("ns", "k1") is None
    assert get_state("ns", "k2") == {"v": 2}


def test_put_again_extends_ttl(backend, clock):
    put_state("ns", "k", {"v": 1}, ttl=TTL)
    clock[0] += TTL - timedelta(seconds=1)
    put_state("ns", "k", {"v": 2}, ttl=TTL)
    clock[0] += timedelta(seconds=2)
    assert get_state("ns", "k") == {"v": 2}


def test_pop_returns_value_once(backend):
    put_state("ns", "k", {"v": "x"}, ttl=TTL)
    assert pop_state("ns", "k") == {"v": "x"}
    assert pop_state("ns", "k") is None
    assert get_state("ns", "k") is None


def test_expired_state_is_gone(backend, clock):
    put_state("ns", "k", {"v": 1}, ttl=TTL)
    clock[0] += TTL - timedelta(seconds=1)
    assert get_state("ns", "k") == {"v": 1}
    clock[0] += timedelta(seconds=1)
    assert get_state("ns", "k") is None
    assert pop_state("ns", "k") is None


def test_clear_states_only_touches_one_namespace(backend):
    put_state("a", "1", {}, ttl=TTL)
    put_state("a", "2", {}, ttl=TTL)
    put_state("b", "1", {"keep": True}, ttl=TTL)
    clear_states("a")
    assert get_state("a", "1") is None
    assert get_state("a", "2") is None
    assert get_state("b", "1") == {"keep": True}


def test_db_state_is_visible_to_another_worker(db_backend):
    put_state("ns", "k", {"v": 1}, ttl=TTL)
    other_worker = _factory(db_backend)
    shared_state.configure_shared_state(other_worker)
    assert get_state("ns", "k") == {"v": 1}


def test_db_state_written_by_another_process(db_backend):
    code = textwrap.dedent(
        f"""
        from datetime import timedelta
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.services import shared_state
        engine = create_engine("sqlite:///{db_backend}")
        shared_state.configure_shared_state(sessionmaker(bind=engine))
        shared_state.put_state("ns", "k", {{"from": "child"}}, ttl=timedelta(minutes=5))
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60)
    assert pop_state("ns", "k") == {"from": "child"}


def test_db_expired_rows_are_purged_on_put(db_backend, clock):
    put_state("ns", "old", {}, ttl=TTL)
    put_state("other", "old", {}, ttl=TTL)
    clock[0] += TTL
    put_state("ns", "new", {}, ttl=TTL)
    with shared_state._session_factory() as db:
        keys = db.execute(select(SharedState.namespace, SharedState.key)).all()
    assert sorted(keys) == [("ns", "new"), ("other", "old")]


def test_db_put_overwrites_one_row(db_backend):
    for i in range(3):
        put_state("ns", "k", {"i": i}, ttl=TTL)
    with shared_state._session_factory() as db:
        assert db.scalar(select(func.count()).select_from(SharedState)) == 1


def test_db_concurrent_pops_have_one_winner(db_backend):
    put_state("ns", "k", {"v": 1}, ttl=TTL)
    factories = [_factory(db_backend) for _ in range(8)]
    barrier = threading.Barrier(len(factories))
    results: list[object] = []

    def worker(factory):
        barrier.wait()
        with factory() as db:
            results.append(shared_state._db_pop(db, "ns", "k"))

    threads = [threading.Thread(target=worker, args=(f,)) for f in factories]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results, key=repr) == [None] * 7 + [{"v": 1}]


def test_settings_dialog_continues_in_another_worker(db_backend):
    from app.services.telegram_bot_handlers import settings_fsm

    settings_fsm.set_pending("42", "sec_tmp_ip")
    shared_state.configure_shared_state(_factory(db_backend))
    pending = settings_fsm.get_pending("42")
    assert (pending.field, pending.value) == ("sec_tmp_ip", "")
    settings_fsm.set_pending_value("42", "10.0.0.1")
    shared_state.configure_shared_state(_factory(db_backend))
    assert settings_fsm.get_pending("42").value == "10.0.0.1"
    settings_fsm.clear_pending("42")
    assert settings_fsm.get_pending("42") is None


def test_settings_dialog_value_ignored_without_pending(db_backend):
    from app.services.telegram_bot_handlers import settings_fsm

    settings_fsm.set_pending_value("42", "10.0.0.1")
    assert settings_fsm.get_pending("42") is None


def test_unlock_code_dialog_continues_in_another_worker(db_backend):
    from app.services.telegram_bot_handlers import unlock_codes_fsm

    unlock_codes_fsm.set_pending("7", step="mode", grant_days=30, protocols=("openvpn", "wireguard"))
    shared_state.configure_shared_state(_factory(db_backend))
    pending = unlock_codes_fsm.get_pending("7")
    assert (pending.step, pending.grant_days, pending.protocols) == ("mode", 30, ("openvpn", "wireguard"))
    unlock_codes_fsm.clear_pending("7")
    assert unlock_codes_fsm.get_pending("7") is None


def test_dialogs_expire(db_backend, clock):
    from app.services.telegram_bot_handlers import settings_fsm, unlock_codes_fsm

    settings_fsm.set_pending("1", "token")
    unlock_codes_fsm.set_pending("1", step="grant_days")
    clock[0] += settings_fsm.PENDING_TTL
    assert settings_fsm.get_pending("1") is None
    clock[0] += unlock_codes_fsm.PENDING_TTL - settings_fsm.PENDING_TTL
    assert unlock_codes_fsm.get_pending("1") is None


def test_clear_all_resets_dialogs(db_backend):
    from app.services.telegram_bot_handlers import settings_fsm, unlock_codes_fsm

    settings_fsm.set_pending("1", "token")
    unlock_codes_fsm.set_pending("1", step="grant_days")
    settings_fsm.clear_all()
    unlock_codes_fsm.clear_all()
    assert settings_fsm.get_pending("1") is None
    assert unlock_codes_fsm.get_pending("1") is None


def test_oidc_login_state_is_shared_and_single_use(db_backend, clock):
    from app.services import telegram_oidc

    telegram_oidc.save_oidc_state("st", code_verifier="cv", redirect_uri="https://panel/cb")
    shared_state.configure_shared_state(_factory(db_backend))
    stored = telegram_oidc.pop_oidc_state("st")
    assert stored["code_verifier"] == "cv"
    assert stored["redirect_uri"] == "https://panel/cb"
    assert telegram_oidc.pop_oidc_state("st") is None

    telegram_oidc.save_oidc_state("late", code_verifier="cv", redirect_uri="https://panel/cb")
    clock[0] += timedelta(seconds=telegram_oidc.OIDC_STATE_TTL)
    assert telegram_oidc.pop_oidc_state("late") is None


def test_lifespan_uses_panel_db_and_returns_to_memory_on_shutdown(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app import main

    panel_sessions = object()
    seen: list[object] = []
    monkeypatch.setattr(
        main,
        "settings",
        SimpleNamespace(database_url=f"sqlite:///{tmp_path / 'adminpanel.db'}", backup_root=tmp_path / "backups"),
    )
    monkeypatch.setattr(main, "SessionLocal", panel_sessions)
    monkeypatch.setattr(main, "seed_database", lambda: None)
    monkeypatch.setattr(main, "restrict_sensitive_file_permissions", lambda _paths: None)
    monkeypatch.setattr(main, "spawn_background_tasks", lambda **_kw: {})
    monkeypatch.setattr(main, "run_leader_startup_actions", lambda: None)
    monkeypatch.setattr(main, "should_start_resource_monitor", lambda: False)

    async def scenario():
        async with main.lifespan(main.app):
            seen.append(shared_state._session_factory)

    asyncio.run(scenario())
    assert seen == [panel_sessions]
    assert shared_state._session_factory is None
