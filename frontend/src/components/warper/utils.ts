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

export function countActiveTextLines(text: string): number {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#')).length
}

export function buildUserDomainsTextFromItems(
  domains: Array<{ domain?: string | null; name?: string | null; type?: string | null } | string>,
): string {
  const lines = ['# Пользовательские домены:']
  for (const item of domains) {
    if (typeof item === 'string') {
      lines.push(item)
      continue
    }
    if (item.type && item.type !== 'user') continue
    const label = item.domain ?? item.name
    if (label) lines.push(label)
  }
  return `${lines.join('\n')}\n`
}

export function buildIpRangesTextFromItems(ranges: Array<string | Record<string, unknown>>): string {
  const lines: string[] = []
  for (const item of ranges) {
    const label = typeof item === 'string' ? item : cidrLabel(item)
    if (label) lines.push(label)
  }
  return lines.length ? `${lines.join('\n')}\n` : ''
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

export type WarperOutboundMode = 'warp' | 'slave' | 'wg'

export const WARP_KEY_SOURCES = [
  { value: 'auto', label: 'Автовыбор', description: 'WARP сам выберет доступный ключ' },
  { value: 'system', label: 'AntiZapret', description: 'Ключи из настроек AntiZapret' },
  { value: 'generate', label: 'Новый ключ', description: 'Сгенерировать новый WARP-ключ' },
] as const

export const OUTBOUND_MODE_OPTIONS: Array<{
  id: WarperOutboundMode
  label: string
  description: string
}> = [
  {
    id: 'warp',
    label: 'WARP',
    description: 'Cloudflare WARP — основной режим AZ-WARP',
  },
  {
    id: 'slave',
    label: 'Slave',
    description: 'Выход через донор-сервер Shadowsocks',
  },
  {
    id: 'wg',
    label: 'WireGuard',
    description: 'Собственный WG-конфиг на узле',
  },
]

export function normalizeOutboundMode(value: unknown): WarperOutboundMode | null {
  const mode = typeof value === 'string' ? value.trim().toLowerCase() : ''
  if (mode === 'warp' || mode === 'slave' || mode === 'wg') return mode
  return null
}
