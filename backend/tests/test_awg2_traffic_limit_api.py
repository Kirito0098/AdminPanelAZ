"""API + HA policy_sync for AmneziaWG2 traffic limits."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AmneziaWg2AccessPolicy, Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.routers import client_access
from app.services.feature_guards import blocked_json_response, check_path_access
from app.services.feature_toggles import FeatureToggleService
from app.services.node_sync import policy_sync


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


def _make_node(db, *, name: str = "node-1") -> Node:
    node = Node(
        name=name,
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


def _make_owner(db) -> User:
    user = User(username="owner", password_hash="hash", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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


def test_awg2_traffic_limit_routes_disabled_when_feature_off(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_AWG2_ENABLED=false\n", encoding="utf-8")
    client = _feature_app(FeatureToggleService(env_file))

    set_resp = client.post(
        "/api/client-access/amneziawg2/set-traffic-limit",
        json={"client_name": "ivan", "limit_value": 100, "limit_unit": "MB"},
    )
    clear_resp = client.post(
        "/api/client-access/amneziawg2/clear-traffic-limit",
        json={"client_name": "ivan"},
    )

    assert set_resp.status_code == 403
    assert set_resp.json()["feature_disabled"] == "awg2"
    assert clear_resp.status_code == 403
    assert clear_resp.json()["feature_disabled"] == "awg2"


def test_set_traffic_limit_endpoint_ok():
    db = MagicMock()
    user = SimpleNamespace(id=7, username="admin")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    service = MagicMock()
    service.awg2_set_traffic_limit.return_value = {
        "traffic_limit_bytes": 104857600,
        "traffic_limit_period_days": 7,
    }

    with (
        patch.object(client_access, "_service", return_value=service),
        patch.object(client_access, "log_action") as log_action,
        patch.object(client_access, "_replicate_policy_after_success") as replicate,
    ):
        result = client_access.awg2_set_traffic_limit(
            client_access.TrafficLimitRequest(
                client_name="Ivan",
                limit_value=100,
                limit_unit="MB",
                limit_period_days=7,
            ),
            request=request,
            db=db,
            user=user,
        )

    assert result["traffic_limit_bytes"] == 104857600
    service.awg2_set_traffic_limit.assert_called_once_with(
        "Ivan",
        104857600,
        period_days=7,
        actor="admin",
    )
    log_action.assert_called_once()
    replicate.assert_called_once_with(
        db,
        client_name="Ivan",
        vpn_type=VpnType.amneziawg2,
        op="set_traffic_limit",
        actor="admin",
        limit_bytes=104857600,
        period_days=7,
    )


def test_clear_traffic_limit_endpoint_ok():
    db = MagicMock()
    user = SimpleNamespace(id=7, username="admin")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    service = MagicMock()
    service.awg2_clear_traffic_limit.return_value = {
        "traffic_limit_bytes": None,
        "traffic_limit_period_days": None,
    }

    with (
        patch.object(client_access, "_service", return_value=service),
        patch.object(client_access, "log_action") as log_action,
        patch.object(client_access, "_replicate_policy_after_success") as replicate,
    ):
        result = client_access.awg2_clear_traffic_limit(
            client_access.BlockRequest(client_name="Ivan"),
            request=request,
            db=db,
            user=user,
        )

    assert result["traffic_limit_bytes"] is None
    service.awg2_clear_traffic_limit.assert_called_once_with("Ivan", actor="admin")
    log_action.assert_called_once()
    replicate.assert_called_once_with(
        db,
        client_name="Ivan",
        vpn_type=VpnType.amneziawg2,
        op="clear_traffic_limit",
        actor="admin",
    )


def test_awg2_unblock_maps_traffic_limit_exceeded_to_409():
    from fastapi import HTTPException

    from app.services.traffic_limit import (
        TRAFFIC_LIMIT_EXCEEDED_CODE,
        TrafficLimitExceededError,
    )

    db = MagicMock()
    user = SimpleNamespace(id=7, username="admin")
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    service = MagicMock()
    service.awg2_unblock.side_effect = TrafficLimitExceededError()

    with patch.object(client_access, "_service", return_value=service):
        with pytest.raises(HTTPException) as exc_info:
            client_access.awg2_unblock(
                client_access.BlockRequest(client_name="Ivan"),
                request=request,
                db=db,
                user=user,
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == TRAFFIC_LIMIT_EXCEEDED_CODE
    assert "лимита трафика" in exc_info.value.detail["message"]


def test_replicate_awg2_set_traffic_limit(db):
    owner = _make_owner(db)
    primary = _make_node(db, name="primary")
    replica = _make_node(db, name="replica")
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="Ivan",
        vpn_type=VpnType.amneziawg2,
        owner_id=owner.id,
    )
    db.add(primary_config)
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=primary.id,
            client_name="ivan",
            traffic_limit_bytes=5000,
            traffic_limit_period_days=7,
            updated_by="admin",
        )
    )
    db.commit()
    db.refresh(primary_config)
    adapter = MagicMock()
    group = SimpleNamespace(primary_node_id=primary.id, sync_mode="auto")
    shadow = SimpleNamespace(node_id=replica.id, id=88)

    with (
        patch.object(policy_sync, "get_replica_nodes", return_value=[replica]),
        patch.object(policy_sync, "get_shadow_configs", return_value=[shadow]),
        patch.object(policy_sync, "get_adapter_for_node", return_value=adapter),
        patch.object(policy_sync, "finalize_replicate_outcome"),
        patch("app.services.access_policy.get_client_consumed_traffic_bytes", return_value=0),
        patch("app.services.access_policy.awg2_block_client_runtime"),
        patch("app.services.access_policy.awg2_unblock_client_runtime"),
    ):
        result = policy_sync.replicate_policy_op(
            db,
            group,
            primary_config,
            "set_traffic_limit",
            limit_bytes=5000,
            period_days=7,
            actor="admin",
        )

    row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=replica.id, client_name="ivan")
        .first()
    )
    assert result == {"applied": [{"node_id": replica.id, "config_id": 88}], "errors": [], "skipped": False}
    assert row is not None
    assert row.traffic_limit_bytes == 5000
    assert row.traffic_limit_period_days == 7


def test_replicate_awg2_clear_traffic_limit(db):
    owner = _make_owner(db)
    primary = _make_node(db, name="primary")
    replica = _make_node(db, name="replica")
    primary_config = VpnConfig(
        node_id=primary.id,
        client_name="Ivan",
        vpn_type=VpnType.amneziawg2,
        owner_id=owner.id,
    )
    db.add(primary_config)
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=primary.id,
            client_name="ivan",
            traffic_limit_bytes=None,
            traffic_limit_period_days=None,
            updated_by="admin",
        )
    )
    db.add(
        AmneziaWg2AccessPolicy(
            node_id=replica.id,
            client_name="ivan",
            traffic_limit_bytes=9000,
            traffic_limit_period_days=30,
            updated_by="admin",
        )
    )
    db.commit()
    db.refresh(primary_config)
    adapter = MagicMock()
    group = SimpleNamespace(primary_node_id=primary.id, sync_mode="auto")
    shadow = SimpleNamespace(node_id=replica.id, id=99)

    with (
        patch.object(policy_sync, "get_replica_nodes", return_value=[replica]),
        patch.object(policy_sync, "get_shadow_configs", return_value=[shadow]),
        patch.object(policy_sync, "get_adapter_for_node", return_value=adapter),
        patch.object(policy_sync, "finalize_replicate_outcome"),
        patch("app.services.access_policy.get_client_consumed_traffic_bytes", return_value=0),
        patch("app.services.access_policy.awg2_block_client_runtime"),
        patch("app.services.access_policy.awg2_unblock_client_runtime"),
    ):
        result = policy_sync.replicate_policy_op(
            db,
            group,
            primary_config,
            "clear_traffic_limit",
            actor="admin",
        )

    row = (
        db.query(AmneziaWg2AccessPolicy)
        .filter_by(node_id=replica.id, client_name="ivan")
        .first()
    )
    assert result == {"applied": [{"node_id": replica.id, "config_id": 99}], "errors": [], "skipped": False}
    assert row is not None
    assert row.traffic_limit_bytes is None
    assert row.traffic_limit_period_days is None
