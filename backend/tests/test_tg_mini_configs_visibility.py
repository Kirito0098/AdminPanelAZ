"""Mini App config catalog must respect visible_vpn_profiles (Fider #30)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_tg_mini_user
from app.database import get_db
from app.models import UserRole, VpnType
from app.routers.tg_mini import configs as mini_configs_router


def _user(*, role: UserRole = UserRole.user):
    return SimpleNamespace(id=7, role=role, username="alice")


def _config(*, config_id: int, client_name: str, vpn_type: VpnType, owner_id: int = 7):
    owner = SimpleNamespace(username="alice", telegram_id="1")
    return SimpleNamespace(
        id=config_id,
        client_name=client_name,
        vpn_type=vpn_type,
        owner_id=owner_id,
        owner=owner,
    )


def _client(*, user, rows, policy):
    app = FastAPI()
    app.include_router(mini_configs_router.router, prefix="/tg-mini")

    def _override_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_tg_mini_user] = lambda: user

    with (
        patch("app.routers.tg_mini.configs.get_active_node", return_value=SimpleNamespace(id=1)),
        patch(
            "app.services.config_access.list_accessible_configs",
            return_value=rows,
        ),
        patch(
            "app.routers.tg_mini.configs.resolve_effective_visible_vpn_profiles",
            return_value=policy,
        ),
        TestClient(app) as client,
    ):
        yield client


def test_mini_configs_hides_protocols_outside_visibility_policy():
    user = _user()
    rows = [
        _config(config_id=1, client_name="ovpn-only", vpn_type=VpnType.openvpn),
        _config(config_id=2, client_name="wg-hidden", vpn_type=VpnType.wireguard),
        _config(config_id=3, client_name="awg2-hidden", vpn_type=VpnType.amneziawg2),
    ]
    policy = {
        "routes": ["az", "vpn"],
        "protocols": ["openvpn"],
        "openvpn_groups": ["udp"],
    }

    for client in _client(user=user, rows=rows, policy=policy):
        response = client.get("/tg-mini/configs")
        assert response.status_code == 200
        payload = response.json()["configs"]
        assert [item["client_name"] for item in payload] == ["ovpn-only"]
        assert [item["vpn_type"] for item in payload] == ["openvpn"]


def test_mini_configs_admin_still_sees_all_protocols():
    user = _user(role=UserRole.admin)
    rows = [
        _config(config_id=1, client_name="ovpn", vpn_type=VpnType.openvpn),
        _config(config_id=2, client_name="wg", vpn_type=VpnType.wireguard),
        _config(config_id=3, client_name="awg2", vpn_type=VpnType.amneziawg2),
    ]
    policy = {
        "routes": ["az", "vpn"],
        "protocols": ["openvpn", "wireguard", "amneziawg", "amneziawg2"],
        "openvpn_groups": ["udp", "tcp", "udp_tcp"],
    }

    for client in _client(user=user, rows=rows, policy=policy):
        response = client.get("/tg-mini/configs")
        assert response.status_code == 200
        names = [item["client_name"] for item in response.json()["configs"]]
        assert names == ["ovpn", "wg", "awg2"]
