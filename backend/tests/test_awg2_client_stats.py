import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.services import awg2


def _write_stats_db(
    path: Path,
    *,
    peer_rows: list[tuple[str, str, str, str]],
    total_rows: list[tuple[str, int, int, int, str | None]],
    daily_rows: list[tuple[str, str, int, int]],
) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE peers (pubkey TEXT PRIMARY KEY, name TEXT, iface TEXT, origin TEXT)"
        )
        conn.execute(
            "CREATE TABLE totals (pubkey TEXT PRIMARY KEY, rx_life INTEGER, tx_life INTEGER, last_handshake INTEGER, endpoint TEXT)"
        )
        conn.execute(
            "CREATE TABLE daily (pubkey TEXT, day TEXT, rx INTEGER, tx INTEGER)"
        )
        conn.executemany("INSERT INTO peers(pubkey, name, iface, origin) VALUES (?, ?, ?, ?)", peer_rows)
        conn.executemany(
            "INSERT INTO totals(pubkey, rx_life, tx_life, last_handshake, endpoint) VALUES (?, ?, ?, ?, ?)",
            total_rows,
        )
        conn.executemany("INSERT INTO daily(pubkey, day, rx, tx) VALUES (?, ?, ?, ?)", daily_rows)
        conn.commit()
    finally:
        conn.close()


def _install_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    (amnezia / "services.env").write_text(
        "AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\n",
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")
    bin_path.chmod(0o755)
    return amnezia, overlay, bin_path


def test_client_stats_parses_daily_from_stats_db(tmp_path: Path):
    amnezia, overlay, bin_path = _install_layout(tmp_path)
    stats_db = overlay / "stats.db"
    _write_stats_db(
        stats_db,
        peer_rows=[
            ("pk-az", "ivan", "antizapret-awg", "awg2"),
            ("pk-vpn", "ivan", "vpn-awg", "awg2"),
        ],
        total_rows=[
            ("pk-az", 100, 200, 1_700_000_090, "1.2.3.4:1111"),
            ("pk-vpn", 30, 40, 1_700_000_095, "5.6.7.8:2222"),
        ],
        daily_rows=[
            ("pk-az", "2026-08-09", 7, 8),
            ("pk-vpn", "2026-08-09", 3, 4),
            ("pk-az", "2026-08-10", 10, 20),
            ("pk-vpn", "2026-08-10", 1, 2),
        ],
    )

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", stats_db),
        patch.object(awg2.Awg2Service, "_awg_show_dump", return_value=""),
        patch("app.services.awg2.time.time", return_value=1_700_000_100),
        patch("app.services.awg2.is_local_geoip_loaded", return_value=False),
    ):
        data = awg2.Awg2Service().get_client_stats("ivan")

    assert data == {
        "name": "ivan",
        "online": True,
        "endpoint": "5.6.7.8:2222",
        "handshake_age_s": 5,
        "rx_life": 130,
        "tx_life": 240,
        "daily": [
            {"day": "2026-08-09", "rx": 10, "tx": 12},
            {"day": "2026-08-10", "rx": 11, "tx": 22},
        ],
        "geo": None,
    }


def test_client_stats_dump_fallback_empty_daily(tmp_path: Path):
    amnezia, overlay, bin_path = _install_layout(tmp_path)
    (amnezia / "services.env").write_text("AZ_IFACE=antizapret-awg\n", encoding="utf-8")
    (amnezia / "antizapret-awg.conf").write_text(
        "# ivan\n[Peer]\nPublicKey = abcd=\n",
        encoding="utf-8",
    )
    dump = (
        "peer_pubkey\tpsk\tendpoint\tallowed\tlast_hs\trx\ttx\tkeepalive\n"
        "abcd=\t(none)\t1.2.3.4:12345\t10.0.0.2/32\t1700000090\t10\t20\toff\n"
    )

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", overlay / "stats.db"),
        patch.object(awg2.Awg2Service, "_awg_show_dump", return_value=dump),
        patch("app.services.awg2.time.time", return_value=1_700_000_100),
        patch("app.services.awg2.is_local_geoip_loaded", return_value=False),
    ):
        data = awg2.Awg2Service().get_client_stats("ivan")

    assert data["name"] == "ivan"
    assert data["online"] is True
    assert data["endpoint"] == "1.2.3.4:12345"
    assert data["handshake_age_s"] == 10
    assert data["rx_life"] == 10
    assert data["tx_life"] == 20
    assert data["daily"] == []
    assert data["geo"] is None


def test_client_stats_geo_null_without_mmdb(tmp_path: Path):
    amnezia, overlay, bin_path = _install_layout(tmp_path)
    stats_db = overlay / "stats.db"
    _write_stats_db(
        stats_db,
        peer_rows=[("pk-az", "ivan", "antizapret-awg", "awg2")],
        total_rows=[("pk-az", 100, 200, 1_700_000_090, "1.2.3.4:1111")],
        daily_rows=[],
    )

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", stats_db),
        patch.object(awg2.Awg2Service, "_awg_show_dump", return_value=""),
        patch("app.services.awg2.time.time", return_value=1_700_000_100),
        patch("app.services.awg2.is_local_geoip_loaded", return_value=False),
    ):
        data = awg2.Awg2Service().get_client_stats("ivan")

    assert data["geo"] is None


def test_client_stats_geo_filled_when_lookup_returns(tmp_path: Path):
    amnezia, overlay, bin_path = _install_layout(tmp_path)
    stats_db = overlay / "stats.db"
    _write_stats_db(
        stats_db,
        peer_rows=[("pk-az", "ivan", "antizapret-awg", "awg2")],
        total_rows=[("pk-az", 100, 200, 1_700_000_090, "[1.2.3.4]:1111")],
        daily_rows=[],
    )
    geo = {"city": "Paris", "country": "France", "isp": "Example ISP"}

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", stats_db),
        patch.object(awg2.Awg2Service, "_awg_show_dump", return_value=""),
        patch("app.services.awg2.time.time", return_value=1_700_000_100),
        patch("app.services.awg2.is_local_geoip_loaded", return_value=True),
        patch("app.services.geoip_local.lookup_geo_local", return_value=geo) as lookup,
    ):
        data = awg2.Awg2Service().get_client_stats("ivan")

    lookup.assert_called_once_with("1.2.3.4")
    assert data["geo"] == geo


def test_node_agent_client_stats_route(monkeypatch):
    monkeypatch.setenv("NODE_AGENT_MODE", "dev")
    monkeypatch.setenv("NODE_AGENT_API_KEY", "n" * 32)
    os.environ.pop("NODE_AGENT_ALLOWED_IPS", None)

    import node_agent.main as agent_main

    payload = {
        "name": "ivan",
        "online": True,
        "endpoint": "1.2.3.4:12345",
        "handshake_age_s": 12,
        "rx_life": 10,
        "tx_life": 20,
        "daily": [{"day": "2026-08-10", "rx": 1, "tx": 2}],
        "geo": None,
    }

    with patch("node_agent.main.Awg2Service.get_client_stats", return_value=payload):
        client = TestClient(agent_main.app)
        response = client.get(
            "/awg2/clients/ivan/stats",
            headers={"X-Node-Key": agent_main.NODE_AGENT_API_KEY},
        )

    assert response.status_code == 200
    assert response.json() == payload
