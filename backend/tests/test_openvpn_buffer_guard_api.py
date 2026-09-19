from types import SimpleNamespace

from fastapi.routing import APIRoute

from app.routers import openvpn_buffer_guard as api
from app.routers.openvpn_buffer_guard import router as openvpn_buffer_guard_router
from app.schemas import OpenVpnBufferGuardSettingsOut
from app.services.openvpn_buffer_guard import recommended_by_mode


def _route_map() -> dict[str, APIRoute]:
    return {
        route.path: route
        for route in openvpn_buffer_guard_router.routes
        if isinstance(route, APIRoute)
    }


def test_openvpn_buffer_guard_routes_registered():
    routes = _route_map()

    assert "/openvpn-buffer-guard/settings" in routes
    assert "/openvpn-buffer-guard/events" in routes
    assert "/openvpn-buffer-guard/scan" in routes


def test_openvpn_buffer_guard_routes_require_admin():
    routes = _route_map()
    for path in (
        "/openvpn-buffer-guard/settings",
        "/openvpn-buffer-guard/events",
        "/openvpn-buffer-guard/scan",
    ):
        route = routes[path]
        dep_names = {getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies}
        assert "require_admin" in dep_names


def test_settings_out_includes_recommendations():
    payload = OpenVpnBufferGuardSettingsOut(
        node_id=1,
        enabled=False,
        mode="notify",
        threshold_count=40,
        window_seconds=60,
        escalate_after_seconds=30,
        cooldown_minutes=15,
        temp_ban_minutes=60,
        watch_units=["antizapret-udp", "vpn-udp"],
        recommended_threshold=40,
        recommended_by_mode=recommended_by_mode(),
    )
    assert payload.recommended_threshold == 40
    assert payload.recommended_by_mode["kill_restart"] == 120


def test_settings_to_response_fills_recommendations():
    row = SimpleNamespace(
        node_id=1,
        enabled=False,
        mode="kill",
        threshold_count=80,
        window_seconds=60,
        escalate_after_seconds=30,
        cooldown_minutes=15,
        temp_ban_minutes=60,
        watch_units_json='["antizapret-udp","vpn-udp"]',
        updated_at=None,
    )
    out = api._settings_to_response(row)
    assert out.recommended_threshold == 80
    assert out.recommended_by_mode["notify"] == 40



