import { MapPin } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { TableCell } from '@/components/ui/table'
import type { OpenVpnClient, WireGuardPeer } from '@/types'

export function getConnectionDisplayAddress(
  item: Pick<OpenVpnClient, 'display_address' | 'real_address'> | Pick<WireGuardPeer, 'display_address' | 'endpoint'>,
  fallbackKey: 'real_address' | 'endpoint' = 'real_address',
) {
  if ('display_address' in item && item.display_address) return item.display_address
  if (fallbackKey === 'endpoint' && 'endpoint' in item) return item.endpoint || '—'
  if ('real_address' in item) return item.real_address || '—'
  return '—'
}

export function getConnectionGeoLabel(
  item: Pick<OpenVpnClient, 'geo_label' | 'location_label' | 'isp'> |
    Pick<WireGuardPeer, 'geo_label' | 'location_label' | 'isp'>,
) {
  if (item.geo_label) return item.geo_label
  const parts = [item.location_label, item.isp].filter(Boolean)
  return parts.length > 0 ? parts.join(' · ') : null
}

type GeoConnection = Pick<OpenVpnClient, 'city' | 'location_label' | 'isp' | 'country'>

export function getConnectionCity(item: GeoConnection): string | null {
  if (item.city?.trim()) return item.city.trim()
  if (item.location_label?.trim()) {
    const [first] = item.location_label.split(',')
    return first?.trim() || null
  }
  return null
}

export function getConnectionIsp(item: GeoConnection): string | null {
  const raw = item.isp?.trim()
  return raw ? normalizeIspName(raw) : null
}

const ISP_CANONICAL_RULES: Array<[RegExp, string]> = [
  [/tele2|t2 russia/i, 'Tele2'],
  [/megafon/i, 'MegaFon'],
  [/\bmts\b|mobile telesystems/i, 'MTS'],
  [/rostelecom/i, 'Rostelecom'],
  [/beeline|vimpelcom/i, 'Beeline'],
  [/yota/i, 'Yota'],
  [/dom\.ru|ertelecom|domru/i, 'Dom.ru'],
  [/ttk|trans telekom/i, 'TTK'],
]

/** Collapse ip-api ISP variants (T2/Tele2, MTS PJSC, …) for chart grouping. */
export function normalizeIspName(isp: string): string {
  const trimmed = isp.trim()
  if (!trimmed) return trimmed

  for (const [pattern, canonical] of ISP_CANONICAL_RULES) {
    if (pattern.test(trimmed)) return canonical
  }

  return trimmed
    .replace(/\s*,?\s*(PJSC|LLC|JSC|Ltd\.?|Inc\.?|Groups)$/i, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export type GeoPieSlice = { name: string; value: number; breakdown?: Array<{ name: string; value: number }> }

const UNKNOWN_GEO_LABEL = 'Неизвестно'

export function buildGeoPieSlices(
  items: Array<{ city: string | null; isp: string | null }>,
  field: 'city' | 'isp',
  maxSlices = field === 'isp' ? 8 : 6,
): GeoPieSlice[] {
  const counts = new Map<string, number>()
  for (const item of items) {
    const raw = field === 'city' ? item.city : item.isp
    const name = raw?.trim() || UNKNOWN_GEO_LABEL
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  if (counts.size === 0) return []

  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ru'))
  if (sorted.length <= maxSlices) {
    return sorted.map(([name, value]) => ({ name, value }))
  }

  const top = sorted.slice(0, maxSlices - 1)
  const othersEntries = sorted.slice(maxSlices - 1)
  const otherValue = othersEntries.reduce((sum, [, value]) => sum + value, 0)
  return [
    ...top.map(([name, value]) => ({ name, value })),
    {
      name: 'Прочие',
      value: otherValue,
      breakdown: othersEntries.map(([name, value]) => ({ name, value })),
    },
  ]
}

export function collectMonitoringGeoConnections(
  openvpnClients: OpenVpnClient[],
  wireguardPeers: WireGuardPeer[],
  options: {
    showOpenVpn: boolean
    showWireGuard: boolean
    isWireGuardOnline: (peer: WireGuardPeer) => boolean
    onlineOnly?: boolean
  },
): Array<{ city: string | null; isp: string | null }> {
  const items: Array<{ city: string | null; isp: string | null }> = []

  if (options.showOpenVpn) {
    for (const client of openvpnClients) {
      items.push({
        city: getConnectionCity(client),
        isp: getConnectionIsp(client),
      })
    }
  }

  if (options.showWireGuard) {
    for (const peer of wireguardPeers) {
      if (options.onlineOnly && !options.isWireGuardOnline(peer)) continue
      items.push({
        city: getConnectionCity(peer),
        isp: getConnectionIsp(peer),
      })
    }
  }

  return items
}

type ConnectionAddressCellProps = {
  displayAddress?: string | null
  fallback?: string | null
  geoLabel?: string | null
}

export function ConnectionAddressCell({ displayAddress, fallback, geoLabel }: ConnectionAddressCellProps) {
  return (
    <TableCell>
      <div className="font-mono text-xs">{displayAddress || fallback || '—'}</div>
      {geoLabel && (
        <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <MapPin size={11} className="shrink-0" />
          {geoLabel}
        </div>
      )}
    </TableCell>
  )
}

export function NodeScopeBadge({ nodeName }: { nodeName?: string | null }) {
  if (!nodeName) return null
  return (
    <Badge variant="outline" className="text-[10px]">
      {nodeName}
    </Badge>
  )
}
