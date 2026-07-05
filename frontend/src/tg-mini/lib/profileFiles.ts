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
