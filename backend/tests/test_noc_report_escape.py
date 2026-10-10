"""NOC report goes out with parse_mode=HTML: user-controlled names must be escaped."""

from app.services import noc_report as nr

EVIL = '<a href="https://evil.example">click</a>&'
SAFE = "&lt;a href=&quot;https://evil.example&quot;&gt;click&lt;/a&gt;&amp;"


def test_format_noc_escapes_user_controlled_names():
    summary = {
        "nodes_online": 0,
        "nodes_total": 1,
        "total_openvpn": 0,
        "total_wireguard": 0,
        "total_openvpn_peak": 0,
        "total_wireguard_peak": 0,
        "awg2_enabled": False,
        "nodes": [
            {
                "name": EVIL,
                "status": "offline",
                "openvpn": 0,
                "wireguard": 0,
                "openvpn_peak": 0,
                "wireguard_peak": 0,
            }
        ],
    }

    text = nr.format_noc_report_message(
        {
            "period": "daily",
            "summary": summary,
            "incidents": [{"name": EVIL}],
            "top_clients": [{"common_name": EVIL, "traffic_bytes": 1024}],
        }
    )

    assert "<a href" not in text
    assert text.count(SAFE) == 4
