import type { ClientAccessPolicy, VpnConfig } from '@/types'

export type ProtocolTab = 'openvpn' | 'wireguard' | 'amneziawg'
export type ClientFilter = 'all' | 'active' | 'expiring' | 'expired'

type ProfileFile = VpnConfig['profile_files'][number]

export function isAzProfile(file: ProfileFile): boolean {
  return file.variant.includes('antizapret') || file.path.includes('/antizapret')
}

export function isVpnProfile(file: ProfileFile): boolean {
  if (isAzProfile(file)) return false
  return file.variant.includes('vpn') || file.path.includes('/vpn/')
}

export function hasAzProfiles(config: VpnConfig): boolean {
  return config.profile_files.some(isAzProfile)
}

export function hasVpnProfiles(config: VpnConfig): boolean {
  return config.profile_files.some(isVpnProfile)
}

export function pickAzFile(config: VpnConfig): ProfileFile | undefined {
  return config.profile_files.find(isAzProfile)
}

export function pickVpnFile(config: VpnConfig): ProfileFile | undefined {
  return config.profile_files.find(isVpnProfile)
}

export function protocolLabel(tab: ProtocolTab): string {
  if (tab === 'openvpn') return 'OpenVPN'
  if (tab === 'amneziawg') return 'AmneziaWG'
  return 'WireGuard'
}

export function configMatchesTab(config: VpnConfig, tab: ProtocolTab): boolean {
  if (tab === 'openvpn') return config.vpn_type === 'openvpn'
  if (config.vpn_type !== 'wireguard') return false

  const hasWg = config.profile_files.some((f) => f.protocol === 'wireguard')
  const hasAm = config.profile_files.some((f) => f.protocol === 'amneziawg')
  if (!hasWg && !hasAm) return tab === 'wireguard'
  if (tab === 'wireguard') return hasWg
  return hasAm
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
  return d.toLocaleDateString('ru-RU')
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
    lines.push({ text: 'Трафик · Лимит не задан' })
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
  return new Date(value).toLocaleDateString('ru-RU')
}

export function pickPrimaryFile(config: VpnConfig) {
  return pickVpnFile(config) ?? pickAzFile(config) ?? config.profile_files[0]
}

export function getProtocolBadgeVariant(tab: ProtocolTab): 'default' | 'secondary' | 'outline' {
  if (tab === 'openvpn') return 'default'
  if (tab === 'amneziawg') return 'secondary'
  return 'outline'
}
