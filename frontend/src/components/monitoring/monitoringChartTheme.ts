export const MONITORING_CHART_HEIGHT = 220

export const MONITORING_PROTOCOL_COLORS = {
  openvpn: 'hsl(187, 72%, 45%)',
  wireguard: 'hsl(142, 71%, 45%)',
  amneziawg2: 'hsl(38, 92%, 50%)',
  total: 'hsl(217, 33%, 55%)',
} as const

const MONITORING_SLICE_COLORS = [
  MONITORING_PROTOCOL_COLORS.openvpn,
  MONITORING_PROTOCOL_COLORS.wireguard,
  MONITORING_PROTOCOL_COLORS.amneziawg2,
  MONITORING_PROTOCOL_COLORS.total,
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
  if (name === 'AWG 2.0') return MONITORING_PROTOCOL_COLORS.amneziawg2
  return MONITORING_PROTOCOL_COLORS.total
}
