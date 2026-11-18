/**
 * Приложения для подключения в клиентском портале (Fider #41).
 *
 * Единственный источник ссылок — бэкенд: официальные значения приходят в поле
 * ``app_links`` публичного пейлоада портала уже смерженными с настройками
 * админа («Настройки → VPN → Выдача VPN-профилей»). Здесь только подписи
 * приложений и подстановка нужной ячейки под выбранную платформу.
 */

export type PortalOsId = 'windows' | 'android' | 'ios' | 'mac' | 'linux'

export interface PortalAppLink {
  label: string
  url: string
}

/** Ссылки: протокол → платформа → URL (с бэкенда, уже с учётом настроек). */
export type PortalAppLinks = Record<string, Partial<Record<PortalOsId, string>>>

export const PORTAL_OS_OPTIONS: { id: PortalOsId; label: string }[] = [
  { id: 'windows', label: 'Windows' },
  { id: 'android', label: 'Android' },
  { id: 'ios', label: 'iOS' },
  { id: 'mac', label: 'macOS' },
  { id: 'linux', label: 'Linux' },
]

export const PORTAL_APP_PROTOCOLS: { id: string; label: string; hint: string }[] = [
  { id: 'openvpn', label: 'OpenVPN', hint: 'OpenVPN Connect' },
  { id: 'wireguard', label: 'WireGuard', hint: 'официальный клиент' },
  { id: 'amneziawg', label: 'AmneziaWG', hint: 'стоковый AWG 1.5' },
  { id: 'amneziawg2', label: 'AWG 2.0', hint: 'AmneziaWG 2.0' },
]

const APP_LABELS: Record<string, string> = {
  openvpn: 'OpenVPN Connect',
  wireguard: 'WireGuard',
  amneziawg: 'AmneziaWG',
  amneziawg2: 'AmneziaWG',
}

/** Ссылка для пары протокол/платформа из пейлоада портала. */
export function resolveAppDownload(
  links: PortalAppLinks | null | undefined,
  protocol: string | undefined,
  os: PortalOsId,
): PortalAppLink | undefined {
  if (!protocol) return undefined
  const url = links?.[protocol]?.[os]?.trim()
  if (!url) return undefined
  return { label: APP_LABELS[protocol] ?? 'Приложение', url }
}
