"""Game filter UI state helpers (catalog modes for Routing page)."""

from app.services.cidr.game_catalog import GAME_FILTER_CATALOG


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
