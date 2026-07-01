import type { ClientAccessPolicy, OpenVpnClient, VpnConfig, WireGuardPeer } from '@/types'
import { formatDate } from '@/lib/datetime'
import { getProfileDownloadFilename } from '@/lib/profileDownloadName'
import { isWireGuardOnline } from '@/lib/wireguardStatus'

export type ProtocolTab = 'openvpn' | 'wireguard' | 'amneziawg'
export type ClientFilter = 'all' | 'active' | 'expiring' | 'expired'
export type ClientPresenceFilter = 'all' | 'online' | 'offline' | 'blocked'

type ProfileFile = VpnConfig['profile_files'][number]

/** Profile subdirs under client/ — must not match ANTIZAPRET install root (/root/antizapret/...). */
const AZ_PROFILE_DIR = /\/(?:openvpn|wireguard|amneziawg)\/antizapret(?:[-/]|$)/
const VPN_PROFILE_DIR = /\/(?:openvpn|wireguard|amneziawg)\/vpn(?:[-/]|$)/

export function isAzProfile(file: ProfileFile): boolean {
  if (file.variant.includes('antizapret')) return true
  return AZ_PROFILE_DIR.test(file.path)
}

export function isVpnProfile(file: ProfileFile): boolean {
  if (isAzProfile(file)) return false
  if (file.variant === 'vpn' || file.variant.startsWith('vpn-')) return true
  return VPN_PROFILE_DIR.test(file.path)
}

export function profileProtocolForTab(tab: ProtocolTab): ProfileFile['protocol'] {
  if (tab === 'openvpn') return 'openvpn'
  if (tab === 'amneziawg') return 'amneziawg'
  return 'wireguard'
}

export function profileFilesForTab(config: VpnConfig, tab: ProtocolTab): ProfileFile[] {
  if (tab === 'openvpn') {
    return config.profile_files.filter((file) => file.protocol === 'openvpn')
  }
  const protocol = profileProtocolForTab(tab)
  return config.profile_files.filter((file) => file.protocol === protocol)
}

export function hasAzProfiles(config: VpnConfig, tab?: ProtocolTab): boolean {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return files.some(isAzProfile)
}

export function hasVpnProfiles(config: VpnConfig, tab?: ProtocolTab): boolean {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return files.some(isVpnProfile)
}

export function pickAzFile(config: VpnConfig, tab?: ProtocolTab): ProfileFile | undefined {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return files.find(isAzProfile)
}

export function pickVpnFile(config: VpnConfig, tab?: ProtocolTab): ProfileFile | undefined {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return files.find(isVpnProfile)
}

export function protocolLabel(tab: ProtocolTab): string {
  if (tab === 'openvpn') return 'OpenVPN'
  if (tab === 'amneziawg') return 'AmneziaWG'
  return 'WireGuard'
}

export function hasProtocolProfiles(config: VpnConfig, protocol: 'amneziawg' | 'wireguard' | 'openvpn'): boolean {
  if (!config.profile_files?.length) return false
  return config.profile_files.some((file) => file.protocol === protocol)
}

export function configMatchesTab(config: VpnConfig, tab: ProtocolTab): boolean {
  if (tab === 'openvpn') return config.vpn_type === 'openvpn'
  if (!config.profile_files?.length) return config.vpn_type === 'wireguard'
  if (tab === 'amneziawg') return hasProtocolProfiles(config, 'amneziawg')
  return hasProtocolProfiles(config, 'wireguard')
}

export function parseAccessExpiresAt(value?: string | null): Date | null {
  if (!value) return null
  const raw = value.trim()
  if (!raw) return null
  const normalized = raw.endsWith(' UTC')
    ? `${raw.slice(0, -4).replace(' ', 'T')}Z`
    : raw.includes('T')
      ? raw
      : `${raw.replace(' ', 'T')}Z`
  const parsed = Date.parse(normalized)
  return Number.isNaN(parsed) ? null : new Date(parsed)
}

export function formatAccessRemaining(accessExpiresAt?: string | null): string | null {
  const expiresAt = parseAccessExpiresAt(accessExpiresAt)
  if (!expiresAt) return null

  const totalSeconds = Math.floor((expiresAt.getTime() - Date.now()) / 1000)
  if (totalSeconds <= 0) return 'срок истёк'

  const days = Math.floor(totalSeconds / 86400)
  if (days >= 1) return `${days} дн.`

  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  if (hours > 0 && minutes > 0) return `${hours} ч. ${minutes} мин.`
  if (hours > 0) return `${hours} ч.`
  if (minutes > 0) return `${minutes} мин.`
  return 'менее минуты'
}

export function formatDateShort(value?: string | null): string {
  if (!value) return 'не ограничено'
  const d = parseAccessExpiresAt(value)
  if (!d) return value.split(' ')[0] || value
  return formatDate(d, undefined, value.split(' ')[0] || value)
}

export interface AccessMetaLine {
  text: string
}

export function buildAccessMeta(
  config: VpnConfig,
  tab: ProtocolTab,
  policy?: ClientAccessPolicy,
): { lines: AccessMetaLine[]; tone: 'active' | 'expiring' | 'expired' } {
  const lines: AccessMetaLine[] = []
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const isBlocked = policy?.is_blocked ?? false
  let tone: 'active' | 'expiring' | 'expired' = 'active'

  if (config.vpn_type === 'openvpn') {
    lines.push({ text: `Сертификат: ${config.cert_expire_days ?? '—'} дн.` })
  } else if (policy?.expires_at) {
    lines.push({ text: `Отключение: ${formatDateShort(policy.expires_at)}` })
    const remaining = formatAccessRemaining(policy.expires_at)
    lines.push({ text: `Осталось: ${remaining || 'неизвестно'}` })
  } else {
    lines.push({ text: 'Отключение: не ограничено' })
    lines.push({ text: 'Осталось: неизвестно' })
  }

  if (policy?.traffic_limit_human) {
    let limitText = `Лимит: ${policy.traffic_limit_human}`
    if (policy.traffic_limit_period_label) {
      limitText += ` (${policy.traffic_limit_period_label})`
    }
    lines.push({ text: limitText })
    if (policy.traffic_consumed_human) {
      const left = policy.traffic_bytes_left_human ? `, осталось ${policy.traffic_bytes_left_human}` : ''
      lines.push({ text: `Трафик: ${policy.traffic_consumed_human}${left}` })
    }
    if (policy.traffic_limit_exceeded) {
      tone = 'expired'
    }
  } else if (!isBlocked) {
    const consumed = policy?.traffic_consumed_human
    const hasTraffic = Boolean(consumed && (policy?.traffic_consumed_bytes ?? 0) > 0)
    lines.push({
      text: hasTraffic ? `Трафик: ${consumed} · лимит не задан` : 'Трафик · Лимит не задан',
    })
  }

  if (blockMode === 'traffic_limit' || policy?.traffic_limit_exceeded) {
    lines.push({ text: 'Блокировка: превышен лимит трафика' })
    if (policy?.traffic_limit_unblock_label) {
      lines.push({ text: policy.traffic_limit_unblock_label })
    }
    tone = 'expired'
  } else if (blockMode === 'temp') {
    if (policy?.block_duration_days != null) {
      lines.push({ text: `Блокировка: на ${policy.block_duration_days} дн.` })
    } else if (policy?.blocked_days_left != null && policy.blocked_days_left >= 0) {
      lines.push({ text: `Блокировка: на ${policy.blocked_days_left} дн.` })
    } else {
      lines.push({ text: 'Блокировка: временная' })
    }
  } else if (blockMode === 'permanent' || blockMode === 'expired') {
    lines.push({ text: 'Блокировка: до ручной разблокировки' })
  } else {
    lines.push({ text: 'Блокировка: нет' })
  }

  if (blockMode === 'temp' || blockMode === 'permanent' || blockMode === 'expired' || blockMode === 'traffic_limit' || isBlocked) {
    tone = 'expired'
  } else if (config.vpn_type === 'openvpn' && config.cert_expire_days != null && config.cert_expire_days <= 30) {
    tone = 'expiring'
  } else if (policy?.access_days_left != null && policy.access_days_left <= 30) {
    tone = 'expiring'
  } else if (policy?.expires_at && formatAccessRemaining(policy.expires_at) === 'срок истёк') {
    tone = 'expired'
  }

  if (tab === 'openvpn' && config.cert_expire_days != null && config.cert_expire_days < 0) {
    tone = 'expired'
  }

  return { lines, tone }
}

export function matchesFilter(
  config: VpnConfig,
  tab: ProtocolTab,
  filter: ClientFilter,
  policy?: ClientAccessPolicy,
): boolean {
  if (filter === 'all') return true

  const isBlocked = policy?.is_blocked ?? false
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const { tone } = buildAccessMeta(config, tab, policy)

  if (filter === 'active') return !isBlocked && tone !== 'expired'
  if (filter === 'expiring') return tone === 'expiring'
  if (filter === 'expired') {
    return tone === 'expired' || blockMode === 'expired' || Boolean(policy?.expired)
  }
  return true
}

export function isConfigBlocked(policy?: ClientAccessPolicy): boolean {
  if (!policy) return false
  if (policy.is_blocked) return true
  const blockMode = (policy.block_mode || 'none').toLowerCase()
  return (
    blockMode === 'temp' ||
    blockMode === 'permanent' ||
    blockMode === 'expired' ||
    blockMode === 'traffic_limit' ||
    Boolean(policy.traffic_limit_exceeded)
  )
}

export function matchesPresenceFilter(
  config: VpnConfig,
  tab: ProtocolTab,
  filter: ClientPresenceFilter,
  policy: ClientAccessPolicy | undefined,
  connectionMap?: ClientConnectionMap | null,
): boolean {
  if (filter === 'all') return true
  if (filter === 'blocked') return isConfigBlocked(policy)
  const connected = isConfigConnected(config.client_name, tab, connectionMap)
  if (filter === 'online') return connected === true
  if (filter === 'offline') return connected === false
  return true
}

export function getPolicyForConfig(
  config: VpnConfig,
  policies: Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>,
): ClientAccessPolicy | undefined {
  const entry = policies[config.client_name]
  if (!entry) return undefined
  return config.vpn_type === 'openvpn' ? entry.openvpn : entry.wireguard
}

export type ConfigStatusVariant = 'success' | 'destructive' | 'warning' | 'secondary'

export function getConfigStatus(
  config: VpnConfig,
  tab: ProtocolTab,
  policy?: ClientAccessPolicy,
): { label: string; variant: ConfigStatusVariant } {
  const isBlocked = policy?.is_blocked ?? false
  const { tone } = buildAccessMeta(config, tab, policy)

  if (isBlocked || tone === 'expired') {
    return { label: isBlocked ? 'Заблокирован' : 'Истёк', variant: 'destructive' }
  }
  if (tone === 'expiring') {
    return { label: 'Истекает', variant: 'warning' }
  }
  return { label: 'Активный', variant: 'success' }
}

export function formatCreatedAt(value?: string | null): string {
  if (!value) return '—'
  return formatDate(value)
}

export function pickPrimaryFile(config: VpnConfig, tab?: ProtocolTab) {
  const scoped = tab ? profileFilesForTab(config, tab) : config.profile_files
  return pickVpnFile(config, tab) ?? pickAzFile(config, tab) ?? scoped[0]
}

export function getDownloadFilename(config: VpnConfig, file: ProfileFile): string {
  return getProfileDownloadFilename(config.client_name, file)
}

export function getProtocolBadgeVariant(tab: ProtocolTab): 'default' | 'secondary' | 'outline' {
  if (tab === 'openvpn') return 'default'
  if (tab === 'amneziawg') return 'secondary'
  return 'outline'
}

export type ClientConnectionMap = Record<string, { openvpn: boolean; wireguard: boolean }>

export function buildClientConnectionMap(
  openvpnClients: OpenVpnClient[],
  wireguardPeers: WireGuardPeer[],
): ClientConnectionMap {
  const map: ClientConnectionMap = {}

  for (const client of openvpnClients) {
    const key = client.common_name.trim().toLowerCase()
    if (!key) continue
    map[key] = { openvpn: true, wireguard: map[key]?.wireguard ?? false }
  }

  for (const peer of wireguardPeers) {
    const name = (peer.client_name || '').trim()
    if (!name) continue
    const key = name.toLowerCase()
    const prev = map[key]
    const wireguardOnline = isWireGuardOnline(peer) || (prev?.wireguard ?? false)
    map[key] = { openvpn: prev?.openvpn ?? false, wireguard: wireguardOnline }
  }

  return map
}

export function isConfigConnected(
  clientName: string,
  tab: ProtocolTab,
  connectionMap?: ClientConnectionMap | null,
): boolean | null {
  if (!connectionMap) return null
  const entry = connectionMap[clientName.trim().toLowerCase()]
  if (!entry) return false
  return tab === 'openvpn' ? entry.openvpn : entry.wireguard
}

export function formatBlockStatus(policy?: ClientAccessPolicy): {
  value: string
  tone: 'default' | 'warning' | 'danger'
} {
  if (!policy) {
    return { value: '—', tone: 'default' }
  }

  const blockMode = (policy.block_mode || 'none').toLowerCase()
  const isBlocked = policy.is_blocked ?? false

  if (blockMode === 'traffic_limit' || policy.traffic_limit_exceeded) {
    let value = 'превышен лимит трафика'
    if (policy.traffic_limit_unblock_label) {
      value += ` · ${policy.traffic_limit_unblock_label}`
    }
    return { value, tone: 'danger' }
  }
  if (blockMode === 'temp') {
    if (policy.block_duration_days != null) {
      return { value: `на ${policy.block_duration_days} дн.`, tone: 'danger' }
    }
    if (policy.blocked_days_left != null && policy.blocked_days_left >= 0) {
      return { value: `на ${policy.blocked_days_left} дн.`, tone: 'danger' }
    }
    return { value: 'временная', tone: 'danger' }
  }
  if (blockMode === 'permanent' || blockMode === 'expired') {
    return { value: 'до ручной разблокировки', tone: 'danger' }
  }
  if (isBlocked) {
    return { value: 'да', tone: 'danger' }
  }
  return { value: 'нет', tone: 'default' }
}
