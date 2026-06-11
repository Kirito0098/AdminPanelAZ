import type { VpnConfig } from '@/types'

export type ProfileFile = VpnConfig['profile_files'][number]

const CLIENT_NAME_RE = /^[a-zA-Z0-9_-]{1,32}$/
const AZ_PROFILE_DIR = /\/(?:openvpn|wireguard|amneziawg)\/antizapret(?:[-/]|$)/

function sanitizeClientName(clientName: string): string {
  const name = clientName.trim()
  return CLIENT_NAME_RE.test(name) ? name : 'client'
}

function parseProfileLocation(path: string): { protocol: string; variant: string } {
  const normalized = path.replace(/\\/g, '/')
  const marker = '/client/'
  const idx = normalized.indexOf(marker)
  if (idx === -1) return { protocol: '', variant: '' }
  const tail = normalized.slice(idx + marker.length).split('/')
  return { protocol: tail[0] ?? '', variant: tail[1] ?? '' }
}

function isAzProfile(variant: string, path: string): boolean {
  if (variant.includes('antizapret')) return true
  return AZ_PROFILE_DIR.test(path.replace(/\\/g, '/'))
}

function openvpnSuffix(variant: string, path: string): string {
  const normalized = `${variant} ${path}`.toLowerCase()
  if (normalized.includes('-udp')) return '-udp'
  if (normalized.includes('-tcp')) return '-tcp'
  return ''
}

export function buildProfileDownloadFilename(
  clientName: string,
  file: Pick<ProfileFile, 'protocol' | 'variant' | 'path'>,
): string {
  const safeName = sanitizeClientName(clientName)
  const location = parseProfileLocation(file.path)
  const protocol = (file.protocol || location.protocol).toLowerCase()
  const variant = file.variant || location.variant
  const profilePrefix = isAzProfile(variant, file.path) ? 'AZ' : 'VPN'

  if (protocol === 'openvpn') {
    return `${profilePrefix}-${safeName}${openvpnSuffix(variant, file.path)}.ovpn`
  }
  if (protocol === 'wireguard') {
    return `WG-${profilePrefix}-${safeName}.conf`
  }
  if (protocol === 'amneziawg') {
    return `AWG-${profilePrefix}-${safeName}.conf`
  }

  const fallback = file.path.split('/').pop()
  return fallback || `${profilePrefix}-${safeName}.txt`
}

export function getProfileDownloadFilename(clientName: string, file: ProfileFile): string {
  return file.download_filename || buildProfileDownloadFilename(clientName, file)
}

export function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      return utf8Match[1].trim()
    }
  }
  const quotedMatch = /filename="([^"]+)"/i.exec(header)
  if (quotedMatch?.[1]) return quotedMatch[1]
  const plainMatch = /filename=([^;]+)/i.exec(header)
  return plainMatch?.[1]?.trim() ?? null
}
