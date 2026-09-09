from __future__ import annotations

import json
from types import SimpleNamespace

import app.services.server_monitor as sm
from app.services.server_monitor import bandwidth_point_timestamp, ServerMonitorService


def setup_function():
    sm.clear_server_monitor_caches()


def teardown_function():
    sm.clear_server_monitor_caches()


def test_bandwidth_point_timestamp_moscow(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Moscow")

    iso = bandwidth_point_timestamp(
        {"year": 2026, "month": 9, "day": 7},
        {"hour": 11, "minute": 55},
    )

    assert iso.startswith("2026-09-07T08:55:00")


def test_get_bandwidth_emits_utc_timestamps_and_node_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Moscow")
    monkeypatch.setattr(sm, "is_vnstat_available", lambda force=False: True)

    rows = {
        "f": {
            "interfaces": [
                {
                    "name": "eth0",
                    "traffic": {
                        "fiveminute": [
                            {
                                "date": {"year": 2026, "month": 9, "day": 7},
                                "time": {"hour": 11, "minute": 55},
                                "rx": 300_000_000,
                                "tx": 150_000_000,
                            }
                        ]
                    },
                }
            ]
        },
        "d": {
            "interfaces": [
                {
                    "name": "eth0",
                    "traffic": {
                        "day": [
                            {
                                "date": {"year": 2026, "month": 9, "day": 7},
                                "rx": 1_000_000_000,
                                "tx": 500_000_000,
                            }
                        ]
                    },
                }
            ]
        },
    }

    def fake_run(args, **_kwargs):
        payload = rows[args[2]]
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sm.subprocess, "run", fake_run)

    svc = ServerMonitorService()
    result = svc.get_bandwidth("eth0", "1d")

    assert result["time_base"] == "node_local"
    assert result["node_timezone"] == "Europe/Moscow"
    assert result["labels"] == ["11:55"]
    assert result["timestamps"][0].startswith("2026-09-07T08:55:00")
