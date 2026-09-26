import type { MonitoringOverview } from '@/types'

export function formatBytes(n: number) {
  const unit = '\u00A0'
  if (n < 1024) return `${n}${unit}B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)}${unit}KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)}${unit}MB`
  if (n < 1024 ** 4) return `${(n / 1024 ** 3).toFixed(2)}${unit}GB`
  return `${(n / 1024 ** 4).toFixed(2)}${unit}TB`
}

export function totalTraffic(data: MonitoringOverview) {
  const ovpn = data.openvpn_clients.reduce((s, c) => s + c.bytes_received + c.bytes_sent, 0)
  const wg = data.wireguard_peers.reduce((s, p) => s + p.transfer_rx + p.transfer_tx, 0)
  const awg2 = (data.amneziawg2_peers ?? []).reduce((s, p) => s + p.transfer_rx + p.transfer_tx, 0)
  return ovpn + wg + awg2
}
