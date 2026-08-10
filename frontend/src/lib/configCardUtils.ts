import type { ClientAccessPolicy, ClientPoliciesResponseEntry, OpenVpnClient, VpnConfig, WireGuardPeer } from '@/types'
import { formatDate } from '@/lib/datetime'
import { getProfileDownloadFilename } from '@/lib/profileDownloadName'
import { isWireGuardOnline } from '@/lib/wireguardStatus'

export type ProtocolTab = 'openvpn' | 'wireguard' | 'amneziawg' | 'amneziawg2'
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

function profileProtocolForTab(tab: ProtocolTab): ProfileFile['protocol'] {
  if (tab === 'openvpn') return 'openvpn'
  if (tab === 'amneziawg') return 'amneziawg'
  if (tab === 'amneziawg2') return 'amneziawg2'
  return 'wireguard'
}

function profileFilesForTab(config: VpnConfig, tab: ProtocolTab): ProfileFile[] {
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

function preferPrimaryConf(files: ProfileFile[]): ProfileFile | undefined {
  if (!files.length) return undefined
  return (
    files.find((file) => file.path.toLowerCase().endsWith('-am.conf')) ||
    files.find((file) => file.path.toLowerCase().endsWith('.conf')) ||
    files[0]
  )
}

export function pickAzFile(config: VpnConfig, tab?: ProtocolTab): ProfileFile | undefined {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return preferPrimaryConf(files.filter(isAzProfile))
}

export function pickVpnFile(config: VpnConfig, tab?: ProtocolTab): ProfileFile | undefined {
  const files = tab ? profileFilesForTab(config, tab) : config.profile_files
  return preferPrimaryConf(files.filter(isVpnProfile))
}

export function protocolLabel(tab: ProtocolTab): string {
  if (tab === 'openvpn') return 'OpenVPN'
  if (tab === 'amneziawg') return 'AmneziaWG'
  if (tab === 'amneziawg2') return 'AmneziaWG 2.0'
  return 'WireGuard'
}

function hasProtocolProfiles(
  config: VpnConfig,
  protocol: 'amneziawg' | 'amneziawg2' | 'wireguard' | 'openvpn',
): boolean {
  if (!config.profile_files?.length) return false
  return config.profile_files.some((file) => file.protocol === protocol)
}

export function configMatchesTab(config: VpnConfig, tab: ProtocolTab): boolean {
  if (tab === 'amneziawg2') {
    return config.vpn_type === 'amneziawg2' || hasProtocolProfiles(config, 'amneziawg2')
  }
  if (config.vpn_type === 'amneziawg2') return false
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

function formatDateShort(value?: string | null): string {
  if (!value) return 'не ограничено'
  const d = parseAccessExpiresAt(value)
  if (!d) return value.split(' ')[0] || value
  return formatDate(d, undefined, value.split(' ')[0] || value)
}

export function formatAccessExpiryBadge(accessExpiresAt?: string | null): string | null {
  if (!accessExpiresAt) return null
  const remaining = formatAccessRemaining(accessExpiresAt)
  if (!remaining) return null
  return remaining === 'срок истёк' ? 'истёк' : `истекает ${remaining}`
}

/** Backend sends naive UTC timestamps; without a zone suffix Date.parse would read them as local. */
export function parseCertExpiresAt(value?: string | null): Date | null {
  if (!value) return null
  const raw = value.trim()
  if (!raw) return null
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)
  const parsed = Date.parse(`${raw.replace(' ', 'T')}${hasZone ? '' : 'Z'}`)
  return Number.isNaN(parsed) ? null : new Date(parsed)
}

/** Days left on the real certificate, or null while the node has not been read yet. */
export function certDaysLeft(config: VpnConfig): number | null {
  const expiresAt = parseCertExpiresAt(config.cert_expires_at)
  if (!expiresAt) return config.cert_days_left ?? null
  const ms = expiresAt.getTime() - Date.now()
  return ms <= 0 ? 0 : Math.floor(ms / 86400000)
}

export function formatCertExpiry(config: VpnConfig): string {
  const daysLeft = certDaysLeft(config)
  if (daysLeft == null) {
    return config.cert_expire_days != null ? `выпущен на ${config.cert_expire_days} дн.` : '—'
  }
  const expiresAt = parseCertExpiresAt(config.cert_expires_at)
  const until = expiresAt ? formatDate(expiresAt, undefined, '') : ''
  if (daysLeft <= 0) return until ? `истёк ${until}` : 'истёк'
  return until ? `${daysLeft} дн. (до ${until})` : `${daysLeft} дн.`
}

export interface AccessMetaLine {
  text: string
}

/** Pick consumed traffic for the OpenVPN UDP/TCP group toggle (display only). */
export function resolveDisplayedTraffic(
  policy: ClientAccessPolicy | undefined,
  openvpnGroup?: string | null,
): { bytes: number; human: string | null | undefined } {
  if (!policy) {
    return { bytes: 0, human: null }
  }
  if (openvpnGroup === 'GROUP_UDP') {
    return {
      bytes: policy.traffic_consumed_udp_bytes ?? 0,
      human: policy.traffic_consumed_udp_human,
    }
  }
  if (openvpnGroup === 'GROUP_TCP') {
    return {
      bytes: policy.traffic_consumed_tcp_bytes ?? 0,
      human: policy.traffic_consumed_tcp_human,
    }
  }
  return {
    bytes: policy.traffic_consumed_bytes ?? 0,
    human: policy.traffic_consumed_human,
  }
}

export function buildAccessMeta(
  config: VpnConfig,
  tab: ProtocolTab,
  policy?: ClientAccessPolicy,
  openvpnGroup?: string | null,
): { lines: AccessMetaLine[]; tone: 'active' | 'expiring' | 'expired' } {
  const lines: AccessMetaLine[] = []
  const blockMode = (policy?.block_mode || 'none').toLowerCase()
  const isBlocked = policy?.is_blocked ?? false
  let tone: 'active' | 'expiring' | 'expired' = 'active'
  const accessExpiresAt = policy?.expires_at ?? config.expires_at
  const displayed =
    tab === 'openvpn' ? resolveDisplayedTraffic(policy, openvpnGroup) : resolveDisplayedTraffic(policy, null)

  if (config.vpn_type === 'openvpn') {
    lines.push({ text: `Сертификат: ${formatCertExpiry(config)}` })
  } else if (accessExpiresAt) {
    lines.push({ text: `Отключение: ${formatDateShort(accessExpiresAt)}` })
    const remaining = formatAccessRemaining(accessExpiresAt)
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
    if (displayed.human) {
      const left = policy.traffic_bytes_left_human ? `, осталось ${policy.traffic_bytes_left_human}` : ''
      lines.push({ text: `Трафик: ${displayed.human}${left}` })
    }
    if (policy.traffic_limit_exceeded) {
      tone = 'expired'
    }
  } else if (!isBlocked) {
    const hasTraffic = Boolean(displayed.human && displayed.bytes > 0)
    lines.push({
      text: hasTraffic ? `Трафик: ${displayed.human} · лимит не задан` : 'Трафик · Лимит не задан',
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

  const daysLeft = config.vpn_type === 'openvpn' ? certDaysLeft(config) : null

  if (blockMode === 'temp' || blockMode === 'permanent' || blockMode === 'expired' || blockMode === 'traffic_limit' || isBlocked) {
    tone = 'expired'
  } else if (daysLeft != null && daysLeft <= 0) {
    tone = 'expired'
  } else if (daysLeft != null && daysLeft <= 30) {
    tone = 'expiring'
  } else if (policy?.access_days_left != null && policy.access_days_left <= 30) {
    tone = 'expiring'
  } else if (accessExpiresAt) {
    const expiresAt = parseAccessExpiresAt(accessExpiresAt)
    if (formatAccessRemaining(accessExpiresAt) === 'срок истёк') {
      tone = 'expired'
    } else if (expiresAt) {
      const remainingDays = (expiresAt.getTime() - Date.now()) / 86400000
      if (remainingDays <= 30) {
        tone = 'expiring'
      }
    }
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

function isConfigBlocked(policy?: ClientAccessPolicy): boolean {
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
  openvpnGroup?: string | null,
): boolean {
  if (filter === 'all') return true
  if (filter === 'blocked') return isConfigBlocked(policy)
  const connected = isConfigConnected(
    config.client_name,
    tab,
    connectionMap,
    tab === 'openvpn' ? openvpnGroup : null,
  )
  if (filter === 'online') return connected === true
  if (filter === 'offline') return connected === false
  return true
}

export function getPolicyForConfig(
  config: VpnConfig,
  policies: Record<string, ClientPoliciesResponseEntry>,
): ClientAccessPolicy | undefined {
  const entry = policies[config.client_name]
  if (!entry) return undefined
  if (config.vpn_type === 'openvpn') return entry.openvpn
  if (config.vpn_type === 'amneziawg2') return entry.amneziawg2 ?? entry.wireguard
  return entry.wireguard
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
  if (tab === 'amneziawg' || tab === 'amneziawg2') return 'secondary'
  return 'outline'
}

export type ClientConnectionEntry = {
  openvpn: boolean
  openvpnUdp: boolean
  openvpnTcp: boolean
  wireguard: boolean
  /** Issued/live tunnel IP (OpenVPN virtual_address / WG AllowedIPs). */
  localIp?: string | null
}

export type ClientConnectionMap = Record<string, ClientConnectionEntry>

/** Derive OpenVPN transport from a live status profile (e.g. antizapret-udp). */
export function openvpnTransportFromProfile(profile?: string | null): 'udp' | 'tcp' | null {
  const name = (profile || '').trim().toLowerCase()
  if (name.endsWith('-udp')) return 'udp'
  if (name.endsWith('-tcp')) return 'tcp'
  return null
}

function normalizeTunnelIp(raw?: string | null): string | null {
  if (!raw) return null
  const parts: string[] = []
  for (const chunk of raw.split(',')) {
    let token = chunk.trim()
    if (!token || token === '(none)' || token === 'none') continue
    token = token.split('/')[0]?.trim() || ''
    if (token.includes(':') && token.includes('.') && token.split(':').length === 2) {
      token = token.split(':')[0] || ''
    }
    if (token && !parts.includes(token)) parts.push(token)
  }
  return parts.length ? parts.join(', ') : null
}

function mergeLocalIp(prev: string | null | undefined, next: string | null): string | null {
  if (!next) return prev || null
  if (!prev) return next
  const parts = prev.split(', ').filter(Boolean)
  for (const part of next.split(', ')) {
    if (part && !parts.includes(part)) parts.push(part)
  }
  return parts.join(', ')
}

function emptyConnectionEntry(): ClientConnectionEntry {
  return { openvpn: false, openvpnUdp: false, openvpnTcp: false, wireguard: false, localIp: null }
}

export function buildClientConnectionMap(
  openvpnClients: OpenVpnClient[],
  wireguardPeers: WireGuardPeer[],
): ClientConnectionMap {
  const map: ClientConnectionMap = {}

  for (const client of openvpnClients) {
    const key = client.common_name.trim().toLowerCase()
    if (!key) continue
    const prev = map[key] ?? emptyConnectionEntry()
    const transport = openvpnTransportFromProfile(client.profile)
    map[key] = {
      ...prev,
      openvpn: true,
      openvpnUdp: prev.openvpnUdp || transport === 'udp',
      openvpnTcp: prev.openvpnTcp || transport === 'tcp',
      localIp: mergeLocalIp(prev.localIp, normalizeTunnelIp(client.virtual_address)),
    }
  }

  for (const peer of wireguardPeers) {
    const name = (peer.client_name || '').trim()
    if (!name) continue
    const key = name.toLowerCase()
    const prev = map[key] ?? emptyConnectionEntry()
    const wireguardOnline = isWireGuardOnline(peer) || prev.wireguard
    map[key] = {
      ...prev,
      wireguard: wireguardOnline,
      localIp: mergeLocalIp(prev.localIp, normalizeTunnelIp(peer.allowed_ips)),
    }
  }

  return map
}

export function getConfigLocalIp(
  clientName: string,
  connectionMap?: ClientConnectionMap | null,
  fallback?: string | null,
): string | null {
  const fromMap = connectionMap?.[clientName.trim().toLowerCase()]?.localIp
  const value = (fromMap || fallback || '').trim()
  return value || null
}

export function isConfigConnected(
  clientName: string,
  tab: ProtocolTab,
  connectionMap?: ClientConnectionMap | null,
  openvpnGroup?: string | null,
): boolean | null {
  if (!connectionMap) return null
  const entry = connectionMap[clientName.trim().toLowerCase()]
  if (!entry) return false
  if (tab !== 'openvpn') return entry.wireguard
  if (openvpnGroup === 'GROUP_UDP') return entry.openvpnUdp
  if (openvpnGroup === 'GROUP_TCP') return entry.openvpnTcp
  return entry.openvpn
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
