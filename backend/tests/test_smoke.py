"""Smoke tests for AdminPanelAZ backend."""

from fastapi.testclient import TestClient

# Router prefixes registered in app.main (prefix="/api" unless noted).
EXPECTED_ROUTER_PREFIXES = (
    "/api/auth",
    "/api/users",
    "/api/configs",
    "/api/monitoring",
    "/api/settings",
    "/api/backups",
    "/api/nodes",
    "/api/routing",
    "/api/routing/cidr-db",
    "/api/routing/game-filters",
    "/api/traffic",
    "/api/client-access",
    "/api/edit-files",
    "/api/security",
    "/api/public",
    "/api/server-monitor",
    "/api/logs",
    "/api/system",
    "/api/tg-mini",
    "/api/tests",
    "/api/feature-toggles",
    "/api/feature-modules",
)


def _route_paths(app) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def _has_route_under_prefix(paths: set[str], prefix: str) -> bool:
    return prefix in paths or any(path.startswith(f"{prefix}/") for path in paths)


def test_import_app():
    from app.main import app

    assert app.title


def test_health_route_exists():
    from app.main import app

    assert "/api/health" in _route_paths(app)


def test_health_endpoint_returns_ok():
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"]


def test_routers_registered():
    from app.main import app

    paths = _route_paths(app)
    missing = [prefix for prefix in EXPECTED_ROUTER_PREFIXES if not _has_route_under_prefix(paths, prefix)]
    assert not missing, f"Missing router prefixes: {missing}"
