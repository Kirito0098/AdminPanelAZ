"""Tests for VPN profile QR generation."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import create_access_token, get_password_hash
from app.database import Base, get_db
from app.main import app
from app.models import Node, NodeStatus, User, UserRole, VpnConfig, VpnType
from app.services.qr_generator import fits_in_qr, generate_qr_png


def test_fits_in_qr_small_config():
    assert fits_in_qr("[Interface]\nPrivateKey=abc\n")


def test_fits_in_qr_rejects_large_config():
    assert not fits_in_qr("client\n" + "A" * 5000)


def test_generate_qr_png_returns_png_bytes():
    png = generate_qr_png("hello")
    assert png.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "ovpn_path",
    [
        "/root/antizapret/client/openvpn/vpn-tcp/vpn-HerringtonMisha-(vpn.claymore-it.ru)-tcp.ovpn",
        "/root/antizapret/client/openvpn/antizapret-udp/antizapret-Andrew_Rano-(vpn.claymore-it.ru)-udp.ovpn",
    ],
)
def test_real_openvpn_profiles_do_not_fit_inline_qr(ovpn_path: str):
    path = Path(ovpn_path)
    if not path.exists():
        pytest.skip(f"missing fixture file: {ovpn_path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    assert not fits_in_qr(content)


@pytest.fixture()
def qr_route_client(tmp_path):
    db_path = tmp_path / "qr_route.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    admin = User(
        username="qr_admin",
        password_hash=get_password_hash("secret123"),
        role=UserRole.admin,
        is_active=True,
    )
    node = Node(
        name="local",
        host="127.0.0.1",
        port=9100,
        is_local=True,
        status=NodeStatus.online,
    )
    session.add_all([admin, node])
    session.flush()
    config = VpnConfig(
        node_id=node.id,
        client_name="alice",
        vpn_type=VpnType.openvpn,
        owner_id=admin.id,
    )
    session.add(config)
    session.commit()

    env_file = tmp_path / ".env"
    env_file.write_text("FEATURE_QR_DOWNLOADS_ENABLED=true\n", encoding="utf-8")
    monkeypatch_target = "app.services.feature_guards.get_feature_service"

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    large_ovpn = "client\n" + "A" * 5000
    small_wg = "[Interface]\nPrivateKey=abc\n"

    mock_adapter = MagicMock()
    mock_adapter.read_profile_file.side_effect = lambda path: large_ovpn if "large" in path else small_wg

    with (
        patch(monkeypatch_target, lambda: __import__(
            "app.services.feature_toggles", fromlist=["FeatureToggleService"]
        ).FeatureToggleService(env_file)),
        patch("app.routers.configs.get_active_adapter", return_value=mock_adapter),
        patch("app.routers.configs.get_active_node", return_value=node),
    ):
        client = TestClient(app)
        admin_token = create_access_token({"sub": admin.username, "role": admin.role.value})
        yield client, config.id, admin_token

    app.dependency_overrides.clear()
    session.close()


def test_generate_qr_inline_for_small_profile(qr_route_client):
    client, config_id, token = qr_route_client
    response = client.get(
        f"/api/configs/{config_id}/qr",
        params={"path": "/tmp/small.conf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers.get("x-qr-content") == "profile"
    assert response.content.startswith(b"\x89PNG")


def test_generate_qr_falls_back_to_download_link_for_large_profile(qr_route_client):
    client, config_id, token = qr_route_client
    response = client.get(
        f"/api/configs/{config_id}/qr",
        params={"path": "/tmp/large.ovpn"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers.get("x-qr-content") == "download-link"
    assert "/api/public/qr-download/" in response.headers.get("x-qr-download-url", "")
    assert response.content.startswith(b"\x89PNG")
