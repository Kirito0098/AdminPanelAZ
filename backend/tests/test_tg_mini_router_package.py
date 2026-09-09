from fastapi.routing import APIRoute

from app import main
from app.routers.tg_mini import router as tg_mini_router


def _route_paths(routes, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for route in routes:
        if isinstance(route, APIRoute):
            paths.add(f"{prefix}{route.path}")
            continue
        if hasattr(route, "original_router") and hasattr(route, "include_context"):
            child_prefix = getattr(route.include_context, "prefix", "") or ""
            paths.update(_route_paths(route.original_router.routes, prefix=f"{prefix}{child_prefix}"))
    return paths


def test_tg_mini_package_router_exposes_critical_paths():
    paths = _route_paths(tg_mini_router.routes)
    assert {
        "/tg-mini",
        "/tg-mini/auth",
        "/tg-mini/configs",
        "/tg-mini/nodes",
        "/tg-mini/awg2/status",
        "/tg-mini/warper/status",
        "/tg-mini/settings",
    }.issubset(paths)


def test_main_mounts_tg_mini_package_routes():
    paths = _route_paths(main.app.routes)
    prefix = main._API_PREFIX
    assert {
        f"{prefix}/tg-mini",
        f"{prefix}/tg-mini/auth",
        f"{prefix}/tg-mini/configs",
        f"{prefix}/tg-mini/nodes",
        f"{prefix}/tg-mini/awg2/status",
        f"{prefix}/tg-mini/warper/status",
        f"{prefix}/tg-mini/settings",
    }.issubset(paths)
