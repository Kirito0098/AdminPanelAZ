from fastapi.routing import APIRoute

from app.routers.openvpn_buffer_guard import router as openvpn_buffer_guard_router


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



