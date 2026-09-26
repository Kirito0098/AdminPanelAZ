"""A write aimed at the node shown in the UI must not land on a node switched elsewhere (other tab, admin, bot)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_admin
from app.database import Base, get_db
from app.models import AppSetting, ConfigTag, Node, NodeStatus
from app.routers import config_tags
from app.services import expected_node, node_manager
from app.services.expected_node import (
    ACTIVE_NODE_CHANGED_CODE,
    EXPECTED_NODE_HEADER,
    ExpectedNodeMiddleware,
    parse_expected_node_header,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _node(db, name: str, *, kind: str = "vpn") -> Node:
    node = Node(
        name=name,
        host="10.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=False,
        node_kind=kind,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _activate(db, node: Node) -> None:
    node_manager.set_active_node_id(db, node.id)
    db.commit()


def _stored_active_id(db) -> str | None:
    row = db.query(AppSetting).filter(AppSetting.key == node_manager.ACTIVE_NODE_KEY).first()
    return row.value if row else None


@pytest.fixture()
def expect():
    tokens = []

    def _set(node_id: int | None) -> None:
        tokens.append(expected_node._expected_node_id.set(node_id))

    yield _set
    for token in reversed(tokens):
        expected_node._expected_node_id.reset(token)


def test_parse_expected_node_header():
    assert parse_expected_node_header("12") == 12
    assert parse_expected_node_header(" 7 ") == 7
    for raw in (None, "", "0", "-3", "abc", "1.5", "١٢", "9" * 30):
        assert parse_expected_node_header(raw) is None


def test_active_node_matching_the_expectation_is_returned(db, expect):
    a = _node(db, "A")
    _activate(db, a)
    expect(a.id)

    assert node_manager.get_active_node(db).id == a.id


def test_no_expectation_keeps_the_old_behaviour(db, expect):
    a = _node(db, "A")
    _activate(db, a)
    expect(None)

    assert node_manager.get_active_node(db).id == a.id


def test_active_node_switched_elsewhere_is_rejected_with_409(db, expect):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)
    expect(a.id)

    with pytest.raises(HTTPException) as exc:
        node_manager.get_active_node(db)

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == ACTIVE_NODE_CHANGED_CODE
    assert exc.value.detail["active_node_id"] == b.id
    assert "«B»" in exc.value.detail["message"]
    with pytest.raises(HTTPException):
        node_manager.get_active_adapter(db)


def test_auto_selected_node_is_checked_against_the_expectation(db, expect):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)
    node_manager.clear_active_node_id(db)
    db.commit()
    expect(b.id)

    with pytest.raises(HTTPException) as exc:
        node_manager.get_active_node(db)

    assert exc.value.detail["active_node_id"] == a.id


def test_request_that_switches_the_node_itself_follows_the_new_node(db, expect):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, a)
    expect(a.id)

    node_manager.set_active_node_id(db, b.id)
    db.commit()

    assert node_manager.get_active_node(db).id == b.id


def test_request_that_clears_the_node_itself_is_not_rejected(db, expect):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)
    expect(b.id)

    node_manager.clear_active_node_id(db)
    db.commit()

    assert node_manager.get_active_node(db).id == a.id


def test_rejected_proxy_activation_keeps_the_expectation(db, expect):
    a, b = _node(db, "A"), _node(db, "B")
    proxy = _node(db, "P", kind="proxy")
    _activate(db, b)
    expect(a.id)

    with pytest.raises(HTTPException):
        node_manager.set_active_node_id(db, proxy.id)
    with pytest.raises(HTTPException) as exc:
        node_manager.get_active_node(db)
    assert exc.value.status_code == 409


def _client(db) -> TestClient:
    app = FastAPI()
    app.add_middleware(ExpectedNodeMiddleware)
    app.include_router(config_tags.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: object()

    @app.post("/probe")
    async def probe():
        return {"expected": expected_node._expected_node_id.get()}

    @app.get("/probe")
    async def probe_get():
        return {"expected": expected_node._expected_node_id.get()}

    return TestClient(app)


def test_write_with_stale_node_is_rejected_and_nothing_is_written(db):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)

    resp = _client(db).post("/config-tags", json={"name": "vip"}, headers={EXPECTED_NODE_HEADER: str(a.id)})

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == ACTIVE_NODE_CHANGED_CODE
    assert resp.json()["detail"]["active_node_id"] == b.id
    assert db.query(ConfigTag).count() == 0
    assert _stored_active_id(db) == str(b.id)


def test_write_with_current_node_goes_through(db):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)

    resp = _client(db).post("/config-tags", json={"name": "vip"}, headers={EXPECTED_NODE_HEADER: str(b.id)})

    assert resp.status_code == 201
    assert [tag.node_id for tag in db.query(ConfigTag).all()] == [b.id]
    assert a.id != b.id


def test_write_without_header_goes_through(db):
    b = _node(db, "B")
    _activate(db, b)

    resp = _client(db).post("/config-tags", json={"name": "vip"})

    assert resp.status_code == 201


def test_reads_ignore_the_header(db):
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)
    client = _client(db)

    assert client.get("/config-tags", headers={EXPECTED_NODE_HEADER: str(a.id)}).status_code == 200
    assert client.get("/probe", headers={EXPECTED_NODE_HEADER: str(a.id)}).json() == {"expected": None}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_middleware_binds_the_header_for_writes_only_for_the_request(db, method):
    client = _client(db)
    if method != "post":
        client.app.add_api_route("/probe", lambda: {"expected": expected_node._expected_node_id.get()}, methods=[method.upper()])

    resp = client.request(method.upper(), "/probe", headers={EXPECTED_NODE_HEADER: "5"})

    assert resp.json() == {"expected": 5}
    assert client.post("/probe").json() == {"expected": None}
    assert client.post("/probe", headers={EXPECTED_NODE_HEADER: "junk"}).json() == {"expected": None}
    assert expected_node._expected_node_id.get() is None


def test_middleware_restores_the_previous_value_after_the_request():
    seen = []

    async def inner(scope, receive, send):
        seen.append(expected_node._expected_node_id.get())

    async def main():
        scope = {"type": "http", "method": "POST", "headers": [(b"x-expected-node-id", b"5")]}
        await ExpectedNodeMiddleware(inner)(scope, None, None)
        return expected_node._expected_node_id.get()

    assert asyncio.run(main()) is None
    assert seen == [5]


def test_middleware_passes_non_http_scopes_through():
    seen = []

    async def inner(scope, receive, send):
        seen.append(expected_node._expected_node_id.get())

    asyncio.run(ExpectedNodeMiddleware(inner)({"type": "lifespan"}, None, None))
    asyncio.run(
        ExpectedNodeMiddleware(inner)({"type": "websocket", "headers": [(b"x-expected-node-id", b"5")]}, None, None)
    )

    assert seen == [None, None]


def test_panel_app_installs_the_guard_and_allows_the_header_for_cors():
    from starlette.middleware.cors import CORSMiddleware

    from app.main import app

    classes = [m.cls for m in app.user_middleware]
    assert ExpectedNodeMiddleware in classes
    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert EXPECTED_NODE_HEADER in cors.kwargs["allow_headers"]


def test_background_task_runs_with_the_expectation_of_the_request(monkeypatch, expect):
    from concurrent.futures import ThreadPoolExecutor

    from app.services import background_tasks

    service = background_tasks.background_task_service
    seen: list[int | None] = []
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(background_tasks, "_EXECUTOR", executor)
    monkeypatch.setattr(service, "create_queued_task", lambda *a, **k: "t1")
    monkeypatch.setattr(service, "get_task", lambda task_id: object())
    monkeypatch.setattr(
        service, "run_background_task", lambda task_id, fn: seen.append(expected_node._expected_node_id.get())
    )

    expect(5)
    service.enqueue_background_task("run_doall", lambda: {})
    expect(None)
    service.enqueue_background_task("run_doall", lambda: {})
    executor.shutdown(wait=True)

    assert seen == [5, None]


def test_background_task_failing_on_a_switched_node_reports_the_message(db, monkeypatch, expect):
    from app.services import background_tasks

    service = background_tasks.background_task_service
    a, b = _node(db, "A"), _node(db, "B")
    _activate(db, b)
    updates: list[dict] = []
    monkeypatch.setattr(background_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(service, "update_background_task", lambda task_id, **fields: updates.append(fields))
    expect(a.id)

    service.run_background_task("t1", lambda: {"node": node_manager.get_active_node(db).id})

    failed = updates[-1]
    assert failed["status"] == "failed"
    assert failed["error"].startswith("Активный узел сменился на «B»")
    assert "409" not in failed["error"] and "{" not in failed["error"]


def test_background_task_error_text_for_other_errors():
    from app.services.background_tasks import background_task_service as service

    assert service.exception_text(RuntimeError("boom")) == "boom"
    assert service.exception_text(HTTPException(status_code=502, detail="Узел недоступен")) == "Узел недоступен"
    assert service.exception_text(HTTPException(status_code=502, detail={"code": "x"})) == str(
        HTTPException(status_code=502, detail={"code": "x"})
    )
