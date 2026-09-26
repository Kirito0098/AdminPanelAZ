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

/** Shows the new switch position while saving and puts the previous one back if the save failed. */
export async function saveSwitch<T>(
  previous: T,
  next: T,
  show: (value: T) => void,
  save: () => Promise<boolean>,
): Promise<boolean> {
  show(next)
  let saved = false
  try {
    saved = await save()
    return saved
  } finally {
    if (!saved) show(previous)
  }
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
  return `${size < 10 && unit > 0 ? size.toFixed(1) : Math.round(size)}\u00A0${units[unit]}`
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

function cidrLabel(item: string | Record<string, unknown>): string {
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
    case 'vless':
      return 'VLESS'
    case 'hy2':
      return 'Hysteria2'
    case 'openvpn':
      return 'OpenVPN'
    default:
      return mode ?? '—'
  }
}

export type WarperTab = 'domains' | 'catalog' | 'ip-ranges' | 'monitoring' | 'settings'

export type WarperOutboundMode = 'warp' | 'slave' | 'wg' | 'vless' | 'hy2' | 'openvpn'

export const DEFAULT_FAKE_SUBNET = '10.224.0.0/16'

export const WARP_KEY_SOURCES = [
  { value: 'auto', label: 'Автовыбор', description: 'WARP сам выберет доступный ключ' },
  { value: 'system', label: 'AntiZapret', description: 'Ключи встроенного WARP AntiZapret (warp-antizapret / warp-vpn)' },
  { value: 'wgcf', label: 'wgcf (локальный)', description: 'wgcf-profile.conf в каталоге AZ-WARP' },
  { value: 'root', label: 'wgcf в /root', description: '/root/wgcf-profile.conf' },
  { value: 'generate', label: 'Новый ключ', description: 'Сгенерировать новый WARP-ключ' },
] as const

export type WarperWarpKeySource = (typeof WARP_KEY_SOURCES)[number]['value']

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
    description: 'Свой донор warperslave (ссылка ss:// или host/port/key)',
  },
  {
    id: 'wg',
    label: 'WireGuard',
    description: 'Собственный WG-конфиг на узле',
  },
  {
    id: 'vless',
    label: 'VLESS',
    description: 'VLESS / Reality по ссылке vless://',
  },
  {
    id: 'hy2',
    label: 'Hysteria2',
    description: 'Hysteria2 по ссылке hy2://',
  },
  {
    id: 'openvpn',
    label: 'OpenVPN',
    description: 'Сторонний сервер по файлу .ovpn на узле',
  },
]

export function normalizeOutboundMode(value: unknown): WarperOutboundMode | null {
  const mode = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return OUTBOUND_MODE_OPTIONS.some((option) => option.id === mode) ? (mode as WarperOutboundMode) : null
}

export function formatAzWarpMode(mode: string | null | undefined): string {
  switch (mode) {
    case 'all':
      return 'весь трафик'
    case 'selective':
      return 'выборочно (домены)'
    case 'off':
      return 'выключен'
    default:
      return '—'
  }
}
