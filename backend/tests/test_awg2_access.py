from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus
from app.routers import client_access
from app.services.access_policy import AccessPolicyService
from app.services.feature_guards import blocked_json_response, check_path_access
from app.services.feature_toggles import FeatureToggleService
from app.services.node_adapter import LocalNodeAdapter, RemoteNodeAdapter


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_node(db) -> Node:
    node = Node(
        name="node-1",
        host="127.0.0.1",
        port=9100,
        api_key_hash="",
        api_key_encrypted="",
        status=NodeStatus.online,
        is_local=True,
        node_metadata="{}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _make_service(db, node_id: int) -> AccessPolicyService:
    return AccessPolicyService(db, antizapret_path=Path("/tmp"), node_id=node_id, node_name="node-1")


def _feature_app(service: FeatureToggleService) -> TestClient:
    app = FastAPI()
    app.include_router(client_access.router, prefix="/api")

    @app.middleware("http")
    async def _feature_guard(request, call_next):
        blocked = check_path_access(request.url.path, service=service)
        if blocked is not None:
            return blocked_json_response(blocked[0])
        return await call_next(request)

    return TestClient(app)


def test_awg2_temp_block_calls_awg2_runtime_not_wg(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.block_client_runtime") as wg_block,
        patch("app.services.access_policy.unblock_client_runtime") as wg_unblock,
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
    ):
        state = service.awg2_temp_block("Ivan", 3, actor="admin")

    assert state["is_blocked"] is True
    assert state["block_mode"] == "temp"
    assert state["block_duration_days"] == 3
    awg2_block.assert_called_once_with("ivan")
    wg_block.assert_not_called()
    wg_unblock.assert_not_called()


def test_policy_isolation_same_name_wg_unaffected(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.block_client_runtime", return_value={"success": True}) as wg_block,
        patch("app.services.access_policy.unblock_client_runtime", return_value={"success": True}) as wg_unblock,
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime", return_value={"success": True}) as awg2_unblock,
    ):
        wg_state = service.wg_permanent_block("same-client", actor="admin")
        awg2_state = service.awg2_temp_block("same-client", 2, actor="admin")

    awg2_row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=node.id, client_name="same-client")
        .first()
    )

    assert wg_state["is_blocked"] is True
    assert wg_state["block_mode"] == "permanent"
    assert awg2_state["is_blocked"] is True
    assert awg2_state["block_mode"] == "temp"
    assert awg2_row is not None
    assert awg2_row.is_temp_blocked is True
    assert awg2_row.is_permanent_blocked is False
    wg_block.assert_called_once_with("same-client")
    wg_unblock.assert_not_called()
    awg2_block.assert_called_once_with("same-client")
    awg2_unblock.assert_not_called()


def test_awg2_unblock_clears_flags_and_restores_runtime(db):
    node = _make_node(db)
    service = _make_service(db, node.id)
    with (
        patch("app.services.access_policy.awg2_block_client_runtime", return_value={"success": True}) as awg2_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime", return_value={"success": True}) as awg2_unblock,
    ):
        service.awg2_permanent_block("locked", actor="admin")
        state = service.awg2_unblock("locked", actor="admin")

    row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=node.id, client_name="locked")
        .first()
    )

    assert state["is_blocked"] is False
    assert state["block_mode"] == "none"
    assert row is not None
    assert row.is_temp_blocked is False
    assert row.is_permanent_blocked is False
    assert row.block_reason is None
    assert row.block_started_at is None
    assert row.block_days is None
    assert row.block_until is None
    awg2_block.assert_called_once_with("locked")
    awg2_unblock.assert_called_once_with("locked")


def test_awg2_access_routes_disabled_when_feature_off(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_AWG2_ENABLED=false\n", encoding="utf-8")
    client = _feature_app(FeatureToggleService(env_file))

    response = client.get("/api/client-access/amneziawg2/status")

    assert response.status_code == 403
    assert response.json()["feature_disabled"] == "awg2"


def test_temp_block_endpoint_ok():
    db = MagicMock()
    user = SimpleNamespace(id=7, username="admin")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    service = MagicMock()
    service.awg2_temp_block.return_value = {
        "is_blocked": True,
        "block_mode": "temp",
        "block_duration_days": 5,
        "block_until": "2030-01-01 00:00:00",
    }

    with (
        patch.object(client_access, "_service", return_value=service),
        patch.object(client_access, "log_action") as log_action,
        patch.object(client_access, "_notify_client_ban") as notify,
        patch.object(client_access, "_replicate_policy_after_success") as replicate,
    ):
        result = client_access.awg2_temp_block(
            client_access.BlockRequest(client_name="Ivan", days=5),
            request=request,
            db=db,
            user=user,
        )

    assert result["block_mode"] == "temp"
    service.awg2_temp_block.assert_called_once_with("Ivan", 5, actor="admin")
    log_action.assert_called_once()
    notify.assert_called_once()
    replicate.assert_called_once()


def test_awg2_temp_block_uses_adapter_runtime_when_present(db):
    node = _make_node(db)
    adapter = MagicMock()
    service = AccessPolicyService(
        db,
        antizapret_path=Path("/tmp"),
        node_id=node.id,
        node_name="node-1",
        adapter=adapter,
    )
    with (
        patch("app.services.access_policy.awg2_block_client_runtime") as local_block,
        patch("app.services.access_policy.awg2_unblock_client_runtime") as local_unblock,
    ):
        state = service.awg2_temp_block("Ivan", 3, actor="admin")

    assert state["is_blocked"] is True
    adapter.block_awg2_client_runtime.assert_called_once_with("ivan")
    local_block.assert_not_called()
    local_unblock.assert_not_called()


def test_local_node_adapter_calls_awg2_runtime():
    adapter = LocalNodeAdapter(awg2=MagicMock())
    with patch("app.services.node_adapter.awg2_block_client_runtime", return_value={"success": True}) as runtime_block:
        result = adapter.block_awg2_client_runtime("ivan")

    assert result == {"success": True}
    runtime_block.assert_called_once_with("ivan")


def test_remote_node_adapter_hits_awg2_agent_path():
    adapter = RemoteNodeAdapter("127.0.0.1", 9100, "secret")
    with patch.object(adapter, "_request", return_value={"success": True}) as request:
        result = adapter.block_awg2_client_runtime("ivan")

    assert result == {"success": True}
    request.assert_called_once_with("POST", "/clients/amneziawg2/ivan/block", timeout=30.0)
