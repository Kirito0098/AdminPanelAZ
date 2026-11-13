import { PROTOCOL_CHART_COLORS, protocolKey } from '@/lib/vpnTypes'

export const MONITORING_CHART_HEIGHT = 220

/** Брендовая палитра протоколов — единый источник в lib/vpnTypes. */
export const MONITORING_PROTOCOL_COLORS = PROTOCOL_CHART_COLORS

// Независимая категориальная палитра для гео-срезов. Не связана с протоколами:
// цвета протоколов живут в PROTOCOL_CHART_COLORS.
// Keep order aligned with .monitoring-slice-dot-* in styles/index.css (geo legends).
const MONITORING_SLICE_COLORS = [
  'hsl(187, 72%, 45%)',
  'hsl(142, 71%, 45%)',
  'hsl(217, 33%, 55%)',
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

/** Цвет столбца по каноническому ключу протокола, не по подписи. */
export function getProtocolBarColor(protocol: string) {
  switch (protocolKey(protocol)) {
    case 'openvpn':
      return MONITORING_PROTOCOL_COLORS.openvpn
    case 'wireguard':
    case 'amneziawg':
      return MONITORING_PROTOCOL_COLORS.wireguard
    case 'amneziawg2':
      return MONITORING_PROTOCOL_COLORS.amneziawg2
    default:
      return MONITORING_PROTOCOL_COLORS.total
  }
}
