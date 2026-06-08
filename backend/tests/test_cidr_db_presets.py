"""CIDR DB preset CRUD API tests."""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.services.cidr.constants import BUILTIN_CIDR_PRESETS
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from tests.conftest import run_async


@pytest.fixture()
def presets_env(api_test_env):
    session = api_test_env["session_factory"]()
    try:
        CidrDbUpdaterService(db=session).seed_builtin_presets()
        session.commit()
    finally:
        session.close()
    return api_test_env


def _client(env):
    return TestClient(env["app"])


def test_list_presets_admin(presets_env):
    client = _client(presets_env)
    resp = client.get("/api/routing/cidr-db/presets", headers=presets_env["admin_headers"])
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    presets = data["presets"]
    assert len(presets) >= len(BUILTIN_CIDR_PRESETS)
    builtin = next(p for p in presets if p["key"] == "cdn_only")
    assert builtin["is_builtin"] is True
    assert "akamai-ips.txt" in builtin["providers"]
    assert "akamai-ips.txt" in builtin["providers_meta"]
    assert builtin["providers_meta"]["akamai-ips.txt"]["name"]


def test_list_presets_viewer(presets_env):
    client = _client(presets_env)
    resp = client.get("/api/routing/cidr-db/presets", headers=presets_env["viewer_headers"])
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_create_custom_preset(presets_env):
    client = _client(presets_env)
    resp = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={
            "name": "My preset",
            "description": "Test",
            "providers": ["google-ips.txt", "fastly-ips.txt"],
            "settings": {"region_scopes": ["all"], "include_non_geo_fallback": True},
        },
    )
    assert resp.status_code == 201
    preset = resp.json()["preset"]
    assert preset["key"].startswith("custom_")
    assert preset["is_builtin"] is False
    assert preset["name"] == "My preset"
    assert preset["providers"] == ["google-ips.txt", "fastly-ips.txt"]


def test_create_preset_missing_name(presets_env):
    client = _client(presets_env)
    resp = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={"name": "   ", "providers": ["google-ips.txt"]},
    )
    assert resp.status_code == 400
    assert "имя" in resp.json()["detail"].lower()


def test_create_preset_missing_providers(presets_env):
    client = _client(presets_env)
    resp = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={"name": "No providers", "providers": []},
    )
    assert resp.status_code == 400
    assert "провайдер" in resp.json()["detail"].lower()


def test_update_custom_preset(presets_env):
    client = _client(presets_env)
    create = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={"name": "Before", "providers": ["google-ips.txt"]},
    )
    preset_id = create.json()["preset"]["id"]

    resp = client.put(
        f"/api/routing/cidr-db/presets/{preset_id}",
        headers=presets_env["admin_headers"],
        json={"name": "After", "providers": ["fastly-ips.txt"]},
    )
    assert resp.status_code == 200
    preset = resp.json()["preset"]
    assert preset["name"] == "After"
    assert preset["providers"] == ["fastly-ips.txt"]


def test_update_unknown_preset(presets_env):
    client = _client(presets_env)
    resp = client.put(
        "/api/routing/cidr-db/presets/99999",
        headers=presets_env["admin_headers"],
        json={"name": "Nope"},
    )
    assert resp.status_code == 404


def test_delete_custom_preset(presets_env):
    client = _client(presets_env)
    create = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={"name": "To delete", "providers": ["google-ips.txt"]},
    )
    preset_id = create.json()["preset"]["id"]

    resp = client.delete(
        f"/api/routing/cidr-db/presets/{preset_id}",
        headers=presets_env["admin_headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Удалено"


def test_delete_builtin_preset_rejected(presets_env):
    client = _client(presets_env)
    listing = client.get("/api/routing/cidr-db/presets", headers=presets_env["admin_headers"])
    builtin = next(p for p in listing.json()["presets"] if p["is_builtin"])

    resp = client.delete(
        f"/api/routing/cidr-db/presets/{builtin['id']}",
        headers=presets_env["admin_headers"],
    )
    assert resp.status_code == 400
    assert "встроенный" in resp.json()["detail"].lower()


def test_reset_builtin_preset(presets_env):
    client = _client(presets_env)
    listing = client.get("/api/routing/cidr-db/presets", headers=presets_env["admin_headers"])
    builtin = next(p for p in listing.json()["presets"] if p["key"] == "cdn_only")
    preset_id = builtin["id"]
    default_providers = next(p["providers"] for p in BUILTIN_CIDR_PRESETS if p["key"] == "cdn_only")

    client.put(
        f"/api/routing/cidr-db/presets/{preset_id}",
        headers=presets_env["admin_headers"],
        json={"providers": ["google-ips.txt"]},
    )

    resp = client.post(
        f"/api/routing/cidr-db/presets/{preset_id}/reset",
        headers=presets_env["admin_headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["preset"]["providers"] == default_providers


def test_reset_custom_preset_not_found(presets_env):
    client = _client(presets_env)
    create = client.post(
        "/api/routing/cidr-db/presets",
        headers=presets_env["admin_headers"],
        json={"name": "Custom", "providers": ["google-ips.txt"]},
    )
    preset_id = create.json()["preset"]["id"]

    resp = client.post(
        f"/api/routing/cidr-db/presets/{preset_id}/reset",
        headers=presets_env["admin_headers"],
    )
    assert resp.status_code == 404


def test_presets_require_admin_for_mutations(presets_env):
    transport = ASGITransport(app=presets_env["app"])

    async def _call():
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/routing/cidr-db/presets",
                headers=presets_env["viewer_headers"],
                json={"name": "Viewer", "providers": ["google-ips.txt"]},
            )

    resp = run_async(_call())
    assert resp.status_code == 403
