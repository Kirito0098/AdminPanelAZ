from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.models import RefreshToken, User, UserRole, VpnConfig, VpnType
from app.services.refresh_token import create_refresh_token


def test_delete_user_with_related_records(api_test_env):
    session = api_test_env["session_factory"]()
    node = api_test_env["node"]
    admin = session.query(User).filter(User.username == "api_admin").first()

    victim = User(
        username="victim_owner",
        password_hash=get_password_hash("secret123"),
        role=UserRole.user,
        is_active=True,
    )
    session.add(victim)
    session.commit()
    session.refresh(victim)

    session.add(
        VpnConfig(
            node_id=node.id,
            client_name="owned_cfg",
            vpn_type=VpnType.openvpn,
            owner_id=victim.id,
        )
    )
    create_refresh_token(session, victim)

    victim_token = create_access_token({"sub": victim.username, "role": victim.role.value})
    client = TestClient(api_test_env["app"])
    response = client.delete(
        f"/api/users/{victim.id}",
        headers={"Authorization": f"Bearer {victim_token}"},
    )
    assert response.status_code == 403

    response = client.delete(f"/api/users/{victim.id}", headers=api_test_env["admin_headers"])
    assert response.status_code == 200

    config = session.query(VpnConfig).filter(VpnConfig.client_name == "owned_cfg").first()
    assert config is not None
    assert config.owner_id == admin.id
    assert session.query(RefreshToken).filter(RefreshToken.user_id == victim.id).count() == 0
    assert session.query(User).filter(User.id == victim.id).first() is None
    session.close()
