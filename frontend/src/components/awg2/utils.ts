import type { Awg2HealthResponse, Awg2StatusResponse, Node } from '@/types'

export type Awg2Tab = 'obfuscation' | 'backup' | 'help'

export function awg2StatusMeta(health: Awg2HealthResponse | null) {
  if (!health) {
    return { label: 'Нет данных', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
  if (!health.installed) {
    return { label: 'Не установлен', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  return { label: 'Установлен', variant: 'success' as const, dot: 'bg-emerald-500' }
}

export function formatAwg2ClientCount(status: Awg2StatusResponse | null): string {
  const vpn = status?.client_counts?.vpn
  if (typeof vpn === 'number') return String(vpn)
  const az = status?.client_counts?.antizapret
  if (typeof az === 'number') return String(az)
  return '—'
}

export function formatAwg2IfacePort(iface?: string | null, port?: string | null): string {
  const parts = [iface, port].map((p) => (typeof p === 'string' ? p.trim() : '')).filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}

export const AWG2_INSTALL_CMD =
  'bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh)'

export const AWG2_PRESETS = [
  { value: 'router', label: 'router — минимум шума' },
  { value: 'low', label: 'low — лёгкая обфускация' },
  { value: 'medium', label: 'medium — баланс' },
  { value: 'high', label: 'high — агрессивный DPI' },
  { value: 'paranoid', label: 'paranoid — максимум' },
] as const

export const AWG2_TEMPLATES = [
  { value: 'quic', label: 'quic' },
  { value: 'tls', label: 'tls' },
  { value: 'web', label: 'web' },
  { value: 'voip', label: 'voip' },
  { value: 'dns', label: 'dns' },
  { value: 'mixed', label: 'mixed' },
] as const

export const AWG2_TTL_OPTIONS = [
  { value: 'none', label: 'нет' },
  { value: '30m', label: '30m' },
  { value: '2h', label: '2h' },
  { value: '6h', label: '6h' },
  { value: '7d', label: '7d' },
] as const

export function formatAwg2NodeLabel(health: Awg2HealthResponse | null, activeNode: Node | null): string {
  const name = health?.node_name ?? activeNode?.name
  const host = health?.node_host ?? activeNode?.host
  if (name && host) return `${name} (${host})`
  if (name) return name
  if (host) return host
  return 'активном узле панели'
}
