/**
 * Приложения для подключения в клиентском портале (Fider #41).
 *
 * Здесь только официальные ссылки по умолчанию; админ может переопределить
 * любую ячейку в «Настройки → VPN → Конфиги и доставка». Переопределения
 * приходят с порталом в поле ``app_links`` и мержатся поверх этих значений.
 */

export type PortalOsId = 'windows' | 'android' | 'ios' | 'mac' | 'linux'

export interface PortalAppLink {
  label: string
  url: string
}

/** Переопределения: протокол → платформа → URL. */
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

export const APP_DOWNLOADS: Record<string, Partial<Record<PortalOsId, PortalAppLink>>> = {
  openvpn: {
    windows: { label: 'OpenVPN Connect', url: 'https://openvpn.net/client/' },
    mac: { label: 'OpenVPN Connect', url: 'https://openvpn.net/client/' },
    linux: { label: 'OpenVPN', url: 'https://openvpn.net/community-downloads/' },
    android: {
      label: 'OpenVPN Connect',
      url: 'https://play.google.com/store/apps/details?id=net.openvpn.openvpn',
    },
    ios: { label: 'OpenVPN Connect', url: 'https://apps.apple.com/app/openvpn-connect/id590379981' },
  },
  wireguard: {
    windows: { label: 'WireGuard', url: 'https://www.wireguard.com/install/' },
    mac: { label: 'WireGuard', url: 'https://apps.apple.com/app/wireguard/id1451685025' },
    linux: { label: 'WireGuard', url: 'https://www.wireguard.com/install/' },
    android: {
      label: 'WireGuard',
      url: 'https://play.google.com/store/apps/details?id=com.wireguard.android',
    },
    ios: { label: 'WireGuard', url: 'https://apps.apple.com/app/wireguard/id1441195209' },
  },
  amneziawg: {
    windows: {
      label: 'AmneziaWG',
      url: 'https://github.com/amnezia-vpn/amneziawg-windows-client/releases',
    },
    mac: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    linux: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    android: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    ios: { label: 'AmneziaWG', url: 'https://apps.apple.com/app/amneziawg/id6478942365' },
  },
  amneziawg2: {
    windows: {
      label: 'AmneziaWG',
      url: 'https://github.com/amnezia-vpn/amneziawg-windows-client/releases',
    },
    mac: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    linux: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    android: { label: 'AmneziaWG', url: 'https://amnezia.org/en/downloads' },
    ios: { label: 'AmneziaWG', url: 'https://apps.apple.com/app/amneziawg/id6478942365' },
  },
}

/** Ссылка для пары протокол/платформа: переопределение админа важнее дефолта. */
export function resolveAppDownload(
  overrides: PortalAppLinks | null | undefined,
  protocol: string | undefined,
  os: PortalOsId,
): PortalAppLink | undefined {
  if (!protocol) return undefined
  const base = APP_DOWNLOADS[protocol]?.[os]
  const custom = overrides?.[protocol]?.[os]?.trim()
  if (!custom) return base
  return { label: base?.label ?? 'Приложение', url: custom }
}
