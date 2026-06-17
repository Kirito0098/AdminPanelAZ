from datetime import datetime, timedelta

from app.schemas import WireGuardPeer
from app.services.wireguard_status import WG_HANDSHAKE_ONLINE_SECONDS, wireguard_peer_is_online


def _peer(handshake: str | None) -> WireGuardPeer:
    return WireGuardPeer(
        interface="vpn",
        public_key="abc",
        latest_handshake=handshake,
    )


def test_wireguard_peer_is_online_without_handshake():
    assert wireguard_peer_is_online(_peer(None)) is False


def test_wireguard_peer_is_online_with_recent_handshake():
    recent = datetime.utcnow().isoformat()
    assert wireguard_peer_is_online(_peer(recent)) is True


def test_wireguard_peer_is_online_with_stale_handshake():
    stale = (datetime.utcnow() - timedelta(seconds=WG_HANDSHAKE_ONLINE_SECONDS + 1)).isoformat()
    assert wireguard_peer_is_online(_peer(stale)) is False
