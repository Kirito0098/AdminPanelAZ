"""WireGuard peer online detection helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import WireGuardPeer

# WireGuard considers a peer stale after ~3 minutes without traffic/handshake.
WG_HANDSHAKE_ONLINE_SECONDS = 180


def wireguard_peer_is_online(
    peer: WireGuardPeer,
    *,
    max_age_seconds: int = WG_HANDSHAKE_ONLINE_SECONDS,
) -> bool:
    handshake = peer.latest_handshake
    if not handshake:
        return False
    try:
        parsed = datetime.fromisoformat(str(handshake))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return False
    age_seconds = (datetime.utcnow() - parsed).total_seconds()
    return 0 <= age_seconds <= max_age_seconds
