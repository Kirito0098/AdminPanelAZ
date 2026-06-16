export const MONITORING_CHART_HEIGHT = 220

export const MONITORING_PROTOCOL_COLORS = {
  openvpn: 'hsl(187, 72%, 45%)',
  wireguard: 'hsl(142, 71%, 45%)',
  total: 'hsl(217, 33%, 55%)',
} as const

export const MONITORING_SLICE_COLORS = [
  MONITORING_PROTOCOL_COLORS.openvpn,
  MONITORING_PROTOCOL_COLORS.wireguard,
  MONITORING_PROTOCOL_COLORS.total,
  'hsl(38, 92%, 50%)',
  'hsl(280, 65%, 55%)',
  'hsl(0, 72%, 58%)',
  'hsl(210, 16%, 46%)',
]

/** Recharts tooltip styling lives in index.css (.recharts-default-tooltip). */
export const monitoringChartTooltipProps = {}

export function getMonitoringSliceColor(index: number) {
  return MONITORING_SLICE_COLORS[index % MONITORING_SLICE_COLORS.length]
}

export function getMonitoringSliceDotClass(index: number) {
  return `monitoring-slice-dot-${index % MONITORING_SLICE_COLORS.length}`
}

export function getProtocolBarColor(name: string) {
  if (name === 'OpenVPN') return MONITORING_PROTOCOL_COLORS.openvpn
  if (name === 'WireGuard') return MONITORING_PROTOCOL_COLORS.wireguard
  return MONITORING_PROTOCOL_COLORS.total
}
