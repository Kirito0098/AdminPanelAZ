import type { Node, WarperHealthResponse } from '@/types'

export const INSTALL_CMD =
  'curl -fsSL https://raw.githubusercontent.com/Liafanx/AZ-WARP/main/install.sh | bash'

export function formatNodeLabel(health: WarperHealthResponse | null, activeNode: Node | null): string {
  const name = health?.node_name ?? activeNode?.name
  const host = health?.node_host ?? activeNode?.host
  if (name && host) return `${name} (${host})`
  if (name) return name
  if (host) return host
  return 'активном узле панели'
}

export function isWarperDisabled(health: WarperHealthResponse | null): boolean {
  return !health?.installed || Boolean(health?.conflict_antizapret_warp)
}

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size < 10 && unit > 0 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`
}

export function parseBulkLines(text: string): string[] {
  return text
    .split(/[\n,;]+/)
    .map((line) => line.trim())
    .filter(Boolean)
}

export function cidrLabel(item: string | Record<string, unknown>): string {
  if (typeof item === 'string') return item
  const cidr = item.cidr ?? item.range ?? item.network
  return typeof cidr === 'string' ? cidr : ''
}

export function formatOutboundMode(mode: string | null | undefined): string {
  switch (mode) {
    case 'warp':
      return 'WARP'
    case 'slave':
      return 'Slave'
    case 'wg':
      return 'WireGuard'
    default:
      return mode ?? '—'
  }
}

export function domainTypeLabel(type: string | undefined): string {
  switch (type) {
    case 'gemini':
      return 'Gemini'
    case 'chatgpt':
      return 'ChatGPT'
    case 'user':
      return 'Свой'
    default:
      return type ?? '—'
  }
}

export type WarperTab = 'domains' | 'ip-ranges' | 'monitoring' | 'settings'
