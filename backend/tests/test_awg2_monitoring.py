import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services import awg2


SAMPLE_OVERVIEW = """
name iface online handshake_age rx tx
ivan antizapret-awg 1 12 1000 2000
petr vpn-awg 0 999 0 0
"""


def _seed_stats_db(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE peers (
                pubkey TEXT PRIMARY KEY,
                name TEXT,
                iface TEXT,
                origin TEXT DEFAULT 'awg2'
            );
            CREATE TABLE totals (
                pubkey TEXT PRIMARY KEY,
                rx_life INTEGER,
                tx_life INTEGER,
                last_handshake INTEGER
            );
            """
        )
        now = 1_700_000_050
        conn.execute(
            "INSERT INTO peers(pubkey, name, iface, origin) VALUES (?, ?, ?, 'awg2')",
            ("pk1", "ivan", "antizapret-awg"),
        )
        conn.execute(
            "INSERT INTO totals(pubkey, rx_life, tx_life, last_handshake) VALUES (?, ?, ?, ?)",
            ("pk1", 1000, 2000, now - 12),
        )
        conn.commit()


def test_monitoring_prefers_stats_db_without_dumps(tmp_path: Path):
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    (amnezia / "services.env").write_text(
        "AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\nAZ_PORT=20001\n",
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    stats_db = overlay / "stats.db"
    _seed_stats_db(stats_db)
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n", encoding="utf-8")
    bin_path.chmod(0o755)

    dump_calls: list[str] = []
    overview_calls: list[str] = []

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", stats_db),
        patch.object(awg2.Awg2Service, "_awg_show_dump", side_effect=lambda iface: dump_calls.append(iface) or ""),
        patch.object(
            awg2.Awg2Service,
            "_run_stats_overview",
            side_effect=lambda self: overview_calls.append("overview") or "",
        ),
        patch("app.services.awg2.time.time", return_value=1_700_000_050),
    ):
        data = awg2.Awg2Service().get_monitoring()

    assert data["stats_available"] is True
    assert any(c["name"] == "ivan" and c["online"] is True for c in data["clients"])
    assert dump_calls == []
    assert overview_calls == []
    az = next(i for i in data["ifaces"] if i["name"] == "antizapret-awg")
    assert az["peer_count"] == 1


def test_monitoring_parses_overview_subprocess(tmp_path: Path):
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    (amnezia / "services.env").write_text("AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\nAZ_PORT=20001\n")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "stats.db").write_bytes(b"x")
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)
    stats_py = overlay / "awg_stats.py"
    stats_py.write_text("#!/usr/bin/env python3\nprint('ok')\n")

    dump_calls: list[str] = []

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""
        if any("overview" in str(c) for c in cmd):
            r.stdout = SAMPLE_OVERVIEW
        else:
            r.stdout = ""
        return r

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", overlay / "stats.db"),
        patch.object(awg2, "AWG2_STATS_SCRIPT", stats_py),
        patch.object(awg2.Awg2Service, "_awg_show_dump", side_effect=lambda iface: dump_calls.append(iface) or ""),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
    ):
        data = awg2.Awg2Service().get_monitoring()
    assert data["stats_available"] is True
    assert any(c["name"] == "ivan" and c["online"] is True for c in data["clients"])
    assert dump_calls == []


def test_monitoring_fallback_without_stats_db(tmp_path: Path):
    amnezia = tmp_path / "amnezia"
    amnezia.mkdir()
    (amnezia / "services.env").write_text("AZ_IFACE=antizapret-awg\nVPN_IFACE=vpn-awg\n")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    bin_path = tmp_path / "awg-client"
    bin_path.write_text("#!/bin/sh\n")
    bin_path.chmod(0o755)

    dump = (
        "peer_pubkey\tpsk\tendpoint\tallowed\tlast_hs\trx\ttx\tkeepalive\n"
        "abcd=\t(none)\t1.2.3.4:1\t10.0.0.2/32\t1700000000\t10\t20\toff\n"
    )

    def fake_run(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""
        r.stdout = dump if "show" in cmd else ""
        return r

    with (
        patch.object(awg2, "AWG2_CLIENT_BIN", bin_path),
        patch.object(awg2, "AWG2_OVERLAY_DIR", overlay),
        patch.object(awg2, "AWG2_AMNEZIA_DIR", amnezia),
        patch.object(awg2, "AWG2_SERVICES_ENV", amnezia / "services.env"),
        patch.object(awg2, "AWG2_STATS_DB", overlay / "stats.db"),
        patch("app.services.awg2.subprocess.run", side_effect=fake_run),
        patch("app.services.awg2.time.time", return_value=1700000050),
    ):
        data = awg2.Awg2Service().get_monitoring()
    assert data["stats_available"] is False
    assert isinstance(data["clients"], list)
    assert isinstance(data["ifaces"], list)
