"""Per-request middleware DB checks run in the threadpool, not on the event loop thread."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.database as database
import app.main as main_module
from app.middleware import active_session


def _app_with(middleware_setup) -> tuple[FastAPI, list[int]]:
    loop_threads: list[int] = []
    app = FastAPI()
    middleware_setup(app)

    @app.get(f"{main_module._API_PREFIX}/ping")
    async def ping():
        loop_threads.append(threading.get_ident())
        return {"ok": True}

    @app.get("/page")
    async def page():
        loop_threads.append(threading.get_ident())
        return {"ok": True}

    return app, loop_threads


def _recording_session(threads: list[int]):
    def factory():
        threads.append(threading.get_ident())
        return MagicMock()

    return factory


def test_active_session_touch_runs_off_the_event_loop(monkeypatch):
    db_threads: list[int] = []
    touch = MagicMock()
    monkeypatch.setattr(active_session, "SessionLocal", _recording_session(db_threads))
    monkeypatch.setattr(active_session, "get_active_user_from_access_token", lambda _db, _t: SimpleNamespace(username="admin"))
    monkeypatch.setattr(active_session, "access_token_session_id", lambda _t: "sess-1")
    monkeypatch.setattr(active_session.active_web_session_service, "touch_active_web_session", touch)
    app, loop_threads = _app_with(lambda a: a.add_middleware(active_session.ActiveSessionMiddleware))

    response = TestClient(app).get(
        f"{main_module._API_PREFIX}/ping",
        headers={"Authorization": "Bearer token", "X-Web-Session-Id": "sess-1"},
    )

    assert response.status_code == 200
    assert touch.call_count == 1
    assert db_threads and loop_threads
    assert db_threads[0] != loop_threads[0]


@pytest.fixture()
def ip_service(monkeypatch):
    """ip_restriction_service with scripted answers; records the thread of each DB check."""
    state = SimpleNamespace(hard_deny=False, enabled=False, allowed=True, db_threads=[], recorded=[])
    svc = main_module.ip_restriction_service

    def on_db(result):
        def check(*_args):
            state.db_threads.append(threading.get_ident())
            return result() if callable(result) else result

        return check

    monkeypatch.setattr(database, "SessionLocal", _recording_session(state.db_threads))
    monkeypatch.setattr(svc, "get_client_ip", lambda _request: "203.0.113.9")
    monkeypatch.setattr(svc, "should_hard_deny", on_db(lambda: state.hard_deny))
    monkeypatch.setattr(svc, "get_settings", on_db(lambda: {"ip_restriction_enabled": state.enabled}))
    monkeypatch.setattr(svc, "is_ip_allowed", on_db(lambda: state.allowed))
    monkeypatch.setattr(svc, "should_count_denied_access", lambda _path: True)
    monkeypatch.setattr(svc, "record_denied_access", lambda _db, ip: state.recorded.append((ip, threading.get_ident())))
    app, loop_threads = _app_with(lambda a: a.middleware("http")(main_module.ip_restriction_middleware))
    state.client = TestClient(app, follow_redirects=False)
    state.loop_threads = loop_threads
    return state


def test_ip_restriction_checks_run_off_the_event_loop(ip_service):
    response = ip_service.client.get(f"{main_module._API_PREFIX}/ping")

    assert response.status_code == 200
    assert ip_service.db_threads and ip_service.loop_threads
    assert ip_service.loop_threads[0] not in ip_service.db_threads


def test_ip_restriction_hard_deny(ip_service):
    ip_service.hard_deny = True

    response = ip_service.client.get(f"{main_module._API_PREFIX}/ping")

    assert response.status_code == 403
    assert response.json() == {"detail": "Доступ заблокирован на уровне сервера"}


def test_ip_restriction_denied_api_request_is_recorded(ip_service):
    ip_service.enabled = True
    ip_service.allowed = False

    response = ip_service.client.get(f"{main_module._API_PREFIX}/ping")

    assert response.status_code == 403
    assert response.json() == {"detail": "Доступ запрещён с вашего IP"}
    assert [ip for ip, _ in ip_service.recorded] == ["203.0.113.9"]


def test_ip_restriction_denied_page_redirects(ip_service):
    ip_service.enabled = True
    ip_service.allowed = False

    response = ip_service.client.get("/page", headers={"accept": "text/html"})

    assert response.status_code == 302
    assert response.headers["location"].endswith("/ip-blocked")
    assert not ip_service.loop_threads


def test_ip_restriction_allowed_ip_passes(ip_service):
    ip_service.enabled = True

    response = ip_service.client.get("/page")

    assert response.status_code == 200
    assert ip_service.recorded == []
