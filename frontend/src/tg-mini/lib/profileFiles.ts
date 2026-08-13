import { isAzProfile, isVpnProfile } from '@/lib/configCardUtils'
import type { TgMiniConfigFile } from '@/types'

export type ProfileRoute = 'antizapret' | 'vpn'

type ProfileFileLike = {
  path: string
  variant: string
  protocol: string
  filename: string
}

function toProfileFileLike(file: TgMiniConfigFile): ProfileFileLike {
  return {
    path: file.path,
    variant: file.variant ?? '',
    protocol: file.protocol ?? '',
    filename: file.filename ?? '',
  }
}

export function profileRouteForFile(file: TgMiniConfigFile): ProfileRoute {
  const adapted = toProfileFileLike(file)
  if (isAzProfile(adapted)) return 'antizapret'
  if (isVpnProfile(adapted)) return 'vpn'
  return 'vpn'
}

export function splitProfileFilesByRoute(files: TgMiniConfigFile[]) {
  const antizapret: TgMiniConfigFile[] = []
  const vpn: TgMiniConfigFile[] = []

  for (const file of files) {
    if (profileRouteForFile(file) === 'antizapret') {
      antizapret.push(file)
    } else {
      vpn.push(file)
    }
  }

  return { antizapret, vpn }
}

export function profileRouteLabel(route: ProfileRoute): string {
  return route === 'antizapret' ? 'AntiZapret' : 'VPN'
}

export function profileRouteHint(route: ProfileRoute): string {
  return route === 'antizapret'
    ? 'Только заблокированные сайты и сервисы'
    : 'Весь трафик через VPN-сервер'
}

/** Short “who is this file for” hint under .conf / .vpn (and similar). */
export function profileFormatHint(file: TgMiniConfigFile): string | null {
  const name = (file.download_filename || file.filename || file.path || '').toLowerCase()
  const protocol = (file.protocol || '').toLowerCase()

  if (name.endsWith('.vpn') || name.includes('vpnuri') || name.endsWith('-vpnuri.txt')) {
    return 'Формат AmneziaVPN (часто vpn://…) — импорт в приложение AmneziaVPN'
  }

  if (name.endsWith('.conf')) {
    if (protocol === 'amneziawg2' || protocol === 'amneziawg' || /awg|amnezia/.test(name)) {
      return 'Нативный конфиг AmneziaWG — приложение AmneziaWG, awg-quick и т.п.'
    }
    if (protocol === 'wireguard' || name.startsWith('wg-')) {
      return 'Конфиг WireGuard — приложение WireGuard / wg-quick'
    }
  }

  if (name.endsWith('.ovpn') || protocol === 'openvpn') {
    return 'Профиль OpenVPN — приложение OpenVPN Connect'
  }

  return null
}
