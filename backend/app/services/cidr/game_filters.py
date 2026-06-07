"""Game filter sync to AntiZapret config files (simplified port)."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.cidr.game_catalog import (
    GAME_BLOCK_END,
    GAME_BLOCK_START,
    GAME_FILTER_CATALOG,
    GAME_IP_BLOCK_END,
    GAME_IP_BLOCK_START,
)

if TYPE_CHECKING:
    from app.services.node_adapter import NodeAdapter


def _strip_block(content: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    return pattern.sub("", content).strip()


def _games_by_keys(keys: list[str]) -> list[dict]:
    key_set = {k.strip().lower() for k in keys}
    return [g for g in GAME_FILTER_CATALOG if g["key"] in key_set]


def get_game_filters_state(saved_keys: list[str], saved_modes: dict[str, str]) -> dict:
    games = []
    for item in GAME_FILTER_CATALOG:
        mode = saved_modes.get(item["key"], "none")
        games.append({**item, "mode": mode, "selected": mode != "none"})
    return {
        "games": games,
        "saved_include_keys": [k for k, m in saved_modes.items() if m == "include"],
        "saved_exclude_keys": [k for k, m in saved_modes.items() if m == "exclude"],
        "catalog_count": len(GAME_FILTER_CATALOG),
    }


def _compute_game_filter_contents(
    hosts_content: str,
    ips_content: str,
    *,
    include_keys: list[str],
    exclude_keys: list[str],
    include_domains: bool = True,
) -> tuple[str, str, bool, bool, dict]:
    include_games = _games_by_keys(include_keys)
    exclude_games = _games_by_keys(exclude_keys)

    hosts_clean = _strip_block(hosts_content, GAME_BLOCK_START, GAME_BLOCK_END)
    ips_clean = _strip_block(ips_content, GAME_IP_BLOCK_START, GAME_IP_BLOCK_END)

    domain_lines: list[str] = []
    if include_domains and include_games:
        domain_lines.append(GAME_BLOCK_START)
        for g in include_games:
            domain_lines.append(f"# {g['title']}")
            domain_lines.extend(g["domains"])
        domain_lines.append(GAME_BLOCK_END)

    ip_lines: list[str] = []
    if include_games:
        ip_lines.append(GAME_IP_BLOCK_START)
        for g in include_games:
            for ip in g.get("server_ips") or []:
                token = ip if "/" in ip else f"{ip}/32"
                ip_lines.append(token)
        ip_lines.append(GAME_IP_BLOCK_END)

    next_hosts = "\n".join(filter(None, [hosts_clean, "\n".join(domain_lines)])).strip() + "\n"
    next_ips = "\n".join(filter(None, [ips_clean, "\n".join(ip_lines)])).strip() + "\n"

    hosts_changed = next_hosts != hosts_content
    ips_changed = next_ips != ips_content
    meta = {
        "include_count": len(include_games),
        "exclude_count": len(exclude_games),
        "domain_count": sum(len(g["domains"]) for g in include_games) if include_domains else 0,
    }
    return next_hosts, next_ips, hosts_changed, ips_changed, meta


def sync_game_filters(
    config_dir: Path,
    *,
    include_keys: list[str],
    exclude_keys: list[str],
    include_domains: bool = True,
) -> dict:
    hosts_path = config_dir / "include-hosts.txt"
    ips_path = config_dir / "include-ips.txt"
    hosts_content = hosts_path.read_text(encoding="utf-8", errors="replace") if hosts_path.exists() else ""
    ips_content = ips_path.read_text(encoding="utf-8", errors="replace") if ips_path.exists() else ""

    next_hosts, next_ips, hosts_changed, ips_changed, meta = _compute_game_filter_contents(
        hosts_content,
        ips_content,
        include_keys=include_keys,
        exclude_keys=exclude_keys,
        include_domains=include_domains,
    )

    hosts_path.parent.mkdir(parents=True, exist_ok=True)
    if hosts_changed:
        hosts_path.write_text(next_hosts, encoding="utf-8")
    if ips_changed:
        ips_path.write_text(next_ips, encoding="utf-8")

    return {
        "hosts_changed": hosts_changed,
        "ips_changed": ips_changed,
        **meta,
    }


def sync_game_filters_via_adapter(
    adapter: "NodeAdapter",
    *,
    include_keys: list[str],
    exclude_keys: list[str],
    include_domains: bool = True,
) -> dict:
    hosts_content = adapter.read_config_file("include-hosts.txt")
    ips_content = adapter.read_config_file("include-ips.txt")

    next_hosts, next_ips, hosts_changed, ips_changed, meta = _compute_game_filter_contents(
        hosts_content,
        ips_content,
        include_keys=include_keys,
        exclude_keys=exclude_keys,
        include_domains=include_domains,
    )

    if hosts_changed:
        adapter.write_config_file("include-hosts.txt", next_hosts)
    if ips_changed:
        adapter.write_config_file("include-ips.txt", next_ips)

    return {
        "hosts_changed": hosts_changed,
        "ips_changed": ips_changed,
        **meta,
    }
