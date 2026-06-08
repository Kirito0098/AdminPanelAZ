"""Scanner firewall store tests (ported from AdminAntizapret)."""

from pathlib import Path

from app.services.scanner_firewall_store import ScannerFirewallStore


def test_persists_ban_and_strikes(tmp_path: Path) -> None:
    path = tmp_path / "scanner_blocks.json"
    store = ScannerFirewallStore(path, strikes_for_year=5, year_ban_seconds=86400, dry_run=True)
    info = store.register_ban("198.51.100.10", reason="rate_limit", short_ban_seconds=120)
    assert info["strikes"] == 1

    store2 = ScannerFirewallStore(path, dry_run=True)
    assert store2.is_banned("198.51.100.10") is True


def test_fifth_strike_is_year_ban(tmp_path: Path) -> None:
    path = tmp_path / "scanner_blocks.json"
    store = ScannerFirewallStore(
        path, strikes_for_year=5, year_ban_seconds=365 * 86400, dry_run=True
    )
    ip = "203.0.113.99"
    for _ in range(4):
        store.register_ban(ip, reason="test", short_ban_seconds=60)
        store._entry(ip)["ban_until"] = 0

    info = store.register_ban(ip, reason="test", short_ban_seconds=60)
    assert info["long_term"] is True
    assert info["remaining_seconds"] >= 364 * 86400


def test_unban_sets_grace_without_active_ban(tmp_path: Path) -> None:
    path = tmp_path / "scanner_blocks.json"
    store = ScannerFirewallStore(path, dry_run=True)
    store.register_ban("203.0.113.5", reason="test", short_ban_seconds=120)
    store.unban_ip("203.0.113.5")
    assert store.is_banned("203.0.113.5") is False
    assert store.is_in_unban_grace("203.0.113.5") is True


def test_clear_all_removes_entries(tmp_path: Path) -> None:
    path = tmp_path / "scanner_blocks.json"
    store = ScannerFirewallStore(path, dry_run=True)
    store.register_ban("198.51.100.11", reason="test", short_ban_seconds=60)
    store.clear_all()
    assert store.is_banned("198.51.100.11") is False
