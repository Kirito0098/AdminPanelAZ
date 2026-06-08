"""Game filter sync via full pipeline (include + exclude AZ-Game-* files)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.node_adapter import NodeAdapter


_PATH_KEYS = (
    "AZ_GAME_INCLUDE_HOSTS_FILE",
    "AZ_GAME_INCLUDE_IPS_FILE",
    "AZ_GAME_EXCLUDE_HOSTS_FILE",
    "AZ_GAME_EXCLUDE_IPS_FILE",
    "LEGACY_GAME_INCLUDE_HOSTS_FILE",
    "LEGACY_GAME_INCLUDE_IPS_FILE",
    "GAME_INCLUDE_HOSTS_FILE",
    "GAME_INCLUDE_IPS_FILE",
)


def _path_overrides(config_dir: Path) -> dict[str, str]:
    config_dir = Path(config_dir)
    return {
        "AZ_GAME_INCLUDE_HOSTS_FILE": str(config_dir / "AZ-Game-include-hosts.txt"),
        "AZ_GAME_INCLUDE_IPS_FILE": str(config_dir / "AZ-Game-include-ips.txt"),
        "AZ_GAME_EXCLUDE_HOSTS_FILE": str(config_dir / "AZ-Game-exclude-hosts.txt"),
        "AZ_GAME_EXCLUDE_IPS_FILE": str(config_dir / "AZ-Game-exclude-ips.txt"),
        "LEGACY_GAME_INCLUDE_HOSTS_FILE": str(config_dir / "include-hosts.txt"),
        "LEGACY_GAME_INCLUDE_IPS_FILE": str(config_dir / "include-ips.txt"),
        "GAME_INCLUDE_HOSTS_FILE": str(config_dir / "AZ-Game-include-hosts.txt"),
        "GAME_INCLUDE_IPS_FILE": str(config_dir / "AZ-Game-include-ips.txt"),
    }


@contextmanager
def patch_game_filter_paths(config_dir: Path):
    """Point pipeline game-filter paths at a specific AntiZapret config directory."""
    from app.services.cidr import cidr_list_updater
    from app.services.cidr.pipeline import constants, games

    overrides = _path_overrides(config_dir)
    saved: list[tuple[object, str, object]] = []
    for name, value in overrides.items():
        for mod in (constants, cidr_list_updater):
            if hasattr(mod, name):
                saved.append((mod, name, getattr(mod, name)))
                setattr(mod, name, value)
    games._OVERLAP_INDEX_CACHE.update({"signature": None, "entries": None, "starts": None})
    try:
        yield
    finally:
        for mod, name, value in saved:
            setattr(mod, name, value)
        games._OVERLAP_INDEX_CACHE.update({"signature": None, "entries": None, "starts": None})


def normalize_game_filter_sync_result(result: dict) -> dict:
    include_result = result.get("include_result") or {}
    exclude_result = result.get("exclude_result") or {}
    include_hosts = include_result.get("game_hosts_filter") or {}
    include_ips = include_result.get("game_ips_filter") or {}
    exclude_hosts = exclude_result.get("game_hosts_filter") or {}
    exclude_ips = exclude_result.get("game_ips_filter") or {}

    return {
        **result,
        "hosts_changed": bool(include_hosts.get("changed") or exclude_hosts.get("changed")),
        "ips_changed": bool(include_ips.get("changed") or exclude_ips.get("changed")),
        "include_count": int(include_ips.get("selected_game_count") or 0),
        "exclude_count": int(exclude_ips.get("selected_game_count") or 0),
        "domain_count": int(include_hosts.get("domain_count") or 0),
    }


def run_sync_game_routes_filter(
    config_dir: Path,
    *,
    include_game_keys: list[str] | None = None,
    exclude_game_keys: list[str] | None = None,
    include_game_domains: bool = True,
) -> dict:
    from app.services.cidr.pipeline.games import sync_game_routes_filter

    config_dir.mkdir(parents=True, exist_ok=True)
    with patch_game_filter_paths(config_dir):
        result = sync_game_routes_filter(
            include_game_keys=list(include_game_keys or []),
            exclude_game_keys=list(exclude_game_keys or []),
            include_game_domains=bool(include_game_domains),
        )
    return normalize_game_filter_sync_result(result)


def sync_game_routes_filter_via_adapter(
    adapter: NodeAdapter,
    *,
    include_game_keys: list[str] | None = None,
    exclude_game_keys: list[str] | None = None,
    include_game_domains: bool = True,
) -> dict:
    return adapter.sync_game_routes_filter(
        include_game_keys=list(include_game_keys or []),
        exclude_game_keys=list(exclude_game_keys or []),
        include_game_domains=bool(include_game_domains),
    )
