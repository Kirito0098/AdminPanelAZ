"""Non-admin users may only fetch profile files that belong to their own config."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.models import UserRole, VpnType
from app.routers import configs as configs_router

OWN_PATH = "/root/antizapret/client/openvpn/antizapret-udp/antizapret-alice-udp.ovpn"
FOREIGN_PATH = "/root/antizapret/client/openvpn/antizapret-udp/antizapret-bob-udp.ovpn"

OPEN_POLICY = {
    "routes": ["az", "vpn"],
    "protocols": ["openvpn", "wireguard", "amneziawg"],
    "openvpn_groups": ["udp", "tcp", "udp_tcp"],
}


@pytest.fixture
def make_client():
    def _make(role: UserRole):
        user = SimpleNamespace(id=7, role=role, username="alice")
        config = SimpleNamespace(
            id=1, client_name="alice", vpn_type=VpnType.openvpn, node_id=1, owner_id=7
        )
        adapter = MagicMock()
        adapter.get_profile_files.return_value = [
            {"protocol": "openvpn", "variant": "antizapret-udp", "path": OWN_PATH},
        ]
        qr_service = MagicMock()
        qr_service.create_token.return_value = {"url": "https://panel/p/x", "token": "x"}

        app = FastAPI()
        app.include_router(configs_router.router)

        def _override_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: user

        patches = [
            patch.object(configs_router, "_get_config_for_active_node", return_value=config),
            patch.object(configs_router, "_can_access_config", return_value=True),
            patch.object(configs_router, "get_active_adapter", return_value=adapter),
            patch.object(configs_router, "resolve_effective_visible_vpn_profiles", return_value=OPEN_POLICY),
            patch.object(configs_router, "load_node_remote_hosts", return_value=[]),
            patch.object(configs_router, "read_profile_file_for_delivery", return_value="client\nremote x\n"),
            patch.object(configs_router, "_qr_download_service", return_value=qr_service),
        ]
        for p in patches:
            p.start()
        client = TestClient(app)
        return client, patches

    started: list = []

    def _factory(role: UserRole):
        client, patches = _make(role)
        started.extend(patches)
        return client

    yield _factory
    for p in started:
        p.stop()


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/configs/1/download"),
        ("get", "/configs/1/qr"),
        ("post", "/configs/1/one-time-link"),
    ],
)
def test_user_cannot_fetch_profile_path_of_another_client(make_client, method, url):
    client = make_client(UserRole.user)

    response = getattr(client, method)(url, params={"path": FOREIGN_PATH})

    assert response.status_code == 403


def test_user_can_download_own_profile_path(make_client):
    client = make_client(UserRole.user)

    response = client.get("/configs/1/download", params={"path": OWN_PATH})

    assert response.status_code == 200


def test_admin_can_download_any_profile_path(make_client):
    client = make_client(UserRole.admin)

    response = client.get("/configs/1/download", params={"path": FOREIGN_PATH})

    assert response.status_code == 200
