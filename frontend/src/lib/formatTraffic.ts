/** Format bits-per-second as Kbps / Mbps with non-breaking space. */
export function formatBitrate(
  bps: number | null | undefined,
  opts?: { pending?: boolean },
): string {
  if (bps == null || !Number.isFinite(bps) || bps < 0) {
    return opts?.pending ? '…' : '—'
  }
  const unit = '\u00A0'
  if (bps < 1000) return `${Math.round(bps)}${unit}bps`
  if (bps < 1_000_000) return `${(bps / 1000).toFixed(1)}${unit}Kbps`
  return `${(bps / 1_000_000).toFixed(2)}${unit}Mbps`
}

/** Short human duration: 4ч 12м / 37м / <1м */
export function formatDurationShort(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const total = Math.floor(seconds)
  if (total < 60) return '<1м'
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (hours > 0) {
    return minutes > 0 ? `${hours}ч ${minutes}м` : `${hours}ч`
  }
  return `${minutes}м`
}

export function sessionDurationSeconds(
  connectedSinceTs?: number | null,
  connectedSince?: string | null,
  nowMs: number = Date.now(),
): number | null {
  if (connectedSinceTs && connectedSinceTs > 0) {
    // connected_since_ts is usually unix seconds
    const ms = connectedSinceTs > 1e12 ? connectedSinceTs : connectedSinceTs * 1000
    return Math.max(0, (nowMs - ms) / 1000)
  }
  if (connectedSince) {
    const parsed = Date.parse(connectedSince)
    if (!Number.isNaN(parsed)) return Math.max(0, (nowMs - parsed) / 1000)
  }
  return null
}
