from datetime import datetime, timedelta

from app.schemas import WireGuardPeer
from app.services.traffic.collector import build_status_rows, protocol_type_from_profile


def test_protocol_type_awg2_not_wireguard():
    assert protocol_type_from_profile("antizapret-awg2") == "amneziawg2"
    assert protocol_type_from_profile("vpn-awg2") == "amneziawg2"
    assert protocol_type_from_profile("antizapret-awg") == "wireguard"  # stock path unchanged
    assert protocol_type_from_profile("antizapret-wg") == "wireguard"


def test_build_status_rows_includes_online_awg2_only():
    now = datetime.utcnow()
    online = WireGuardPeer(
        interface="antizapret-awg",
        public_key="pk1",
        client_name="ivan",
        endpoint="1.2.3.4:1",
        transfer_rx=10,
        transfer_tx=20,
        latest_handshake=(now - timedelta(seconds=5)).isoformat(),
    )
    offline = WireGuardPeer(
        interface="vpn-awg",
        public_key="pk2",
        client_name="ghost",
        latest_handshake=(now - timedelta(seconds=400)).isoformat(),
    )
    rows = build_status_rows([], [], [online, offline])
    assert len(rows) == 1
    assert rows[0]["profile"] == "antizapret-awg2"
    client = rows[0]["traffic_clients"][0]
    assert client["session_kind"] == "amneziawg2"
    assert client["common_name"] == "ivan"
    assert protocol_type_from_profile(rows[0]["profile"]) == "amneziawg2"
