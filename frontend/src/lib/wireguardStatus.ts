import type { WireGuardPeer } from '@/types'

/** WireGuard marks peers stale after ~3 minutes without handshake. */
export const WG_HANDSHAKE_ONLINE_SECONDS = 180

export function isWireGuardOnline(peer: WireGuardPeer) {
  if (!peer.latest_handshake) return false
  const handshakeMs = new Date(peer.latest_handshake).getTime()
  if (Number.isNaN(handshakeMs)) return false
  const ageSeconds = (Date.now() - handshakeMs) / 1000
  return ageSeconds >= 0 && ageSeconds <= WG_HANDSHAKE_ONLINE_SECONDS
}
