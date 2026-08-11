from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import noc_report as nr


def test_awg2_peaks_from_connection_samples():
    now = datetime.utcnow()
    samples = [
        SimpleNamespace(node_id=1, created_at=now - timedelta(hours=2), amneziawg2_count=1),
        SimpleNamespace(node_id=1, created_at=now - timedelta(hours=1), amneziawg2_count=4),
        SimpleNamespace(node_id=2, created_at=now - timedelta(hours=1), amneziawg2_count=2),
    ]
    by_node, fleet = nr._awg2_stats_from_connection_samples(
        samples, since=now - timedelta(hours=3), until=now
    )
    assert by_node[1]["amneziawg2_peak"] == 4
    assert fleet["amneziawg2_peak"] >= 4


def test_awg2_stats_avg_and_fleet_peak_sum():
    now = datetime.utcnow()
    samples = [
        SimpleNamespace(node_id=1, created_at=now - timedelta(hours=2), amneziawg2_count=1),
        SimpleNamespace(node_id=1, created_at=now - timedelta(hours=1), amneziawg2_count=4),
        SimpleNamespace(node_id=2, created_at=now - timedelta(hours=1), amneziawg2_count=2),
    ]
    by_node, fleet = nr._awg2_stats_from_connection_samples(
        samples, since=now - timedelta(hours=3), until=now
    )
    assert by_node[1]["amneziawg2"] == 2.5
    assert by_node[2]["amneziawg2_peak"] == 2
    assert fleet["amneziawg2_peak"] == 6


def test_format_noc_omits_awg2_when_disabled():
    summary = {
        "nodes_online": 1,
        "nodes_total": 1,
        "total_openvpn": 1,
        "total_wireguard": 2,
        "total_amneziawg2": 3,
        "total_openvpn_peak": 1,
        "total_wireguard_peak": 2,
        "total_amneziawg2_peak": 3,
        "awg2_enabled": False,
        "nodes": [
            {
                "name": "n1",
                "status": "online",
                "openvpn": 1,
                "wireguard": 2,
                "amneziawg2": 3,
                "openvpn_peak": 1,
                "wireguard_peak": 2,
                "amneziawg2_peak": 3,
            }
        ],
    }
    text = nr.format_noc_report_message({"period": "daily", "summary": summary})
    assert "AWG2" not in text


def test_format_noc_includes_awg2_when_enabled():
    summary = {
        "nodes_online": 1,
        "nodes_total": 1,
        "total_openvpn": 1,
        "total_wireguard": 2,
        "total_amneziawg2": 3,
        "total_openvpn_peak": 1,
        "total_wireguard_peak": 2,
        "total_amneziawg2_peak": 5,
        "awg2_enabled": True,
        "nodes": [
            {
                "name": "n1",
                "status": "online",
                "openvpn": 1,
                "wireguard": 2,
                "amneziawg2": 3,
                "openvpn_peak": 1,
                "wireguard_peak": 2,
                "amneziawg2_peak": 5,
            }
        ],
    }
    text = nr.format_noc_report_message({"period": "daily", "summary": summary})
    assert "AWG2 <b>3</b>" in text
    assert "AWG2 <b>5</b>" in text
