import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type NocDataFreshnessProps = {
  timestamp?: string | null
  refreshIntervalSec?: number
  geoipMode?: 'local_mmdb' | 'ip_api' | 'none' | null
  dataSource?: string | null
  servedFromCache?: boolean
  className?: string
}

function dataAgeSec(timestamp?: string | null): number | null {
  if (!timestamp) return null
  const ms = Date.parse(timestamp)
  if (Number.isNaN(ms)) return null
  return Math.max(0, (Date.now() - ms) / 1000)
}

function formatAge(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}с назад`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}м назад`
  return `${Math.floor(m / 60)}ч ${m % 60}м назад`
}

function geoipLabel(mode?: string | null): string {
  if (mode === 'local_mmdb') return 'GeoIP: локально'
  if (mode === 'none') return 'GeoIP: выкл.'
  return 'GeoIP: ip-api'
}

function sourceLabel(source?: string | null): string {
  if (source === 'management_socket') return 'OVPN: management socket'
  if (source === 'status_log') return 'OVPN: status log'
  if (source === 'federated') return 'Сводка: все узлы'
  return 'Источник: н/д'
}

export default function NocDataFreshness({
  timestamp,
  refreshIntervalSec = 30,
  geoipMode,
  dataSource,
  servedFromCache,
  className,
}: NocDataFreshnessProps) {
  const age = dataAgeSec(timestamp)
  const stale = age != null && age > refreshIntervalSec * 2

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      <Badge variant="outline" className="text-[10px]" title="См. docs/GeoIP.md">
        {geoipLabel(geoipMode)}
      </Badge>
      <Badge variant={dataSource === 'management_socket' ? 'default' : 'secondary'} className="text-[10px]">
        {sourceLabel(dataSource)}
      </Badge>
      {servedFromCache && (
        <Badge variant="outline" className="border-amber-500/40 text-[10px] text-amber-700 dark:text-amber-400">
          кэш
        </Badge>
      )}
      {age != null && (
        <Badge
          variant="outline"
          className={cn(
            'text-[10px]',
            stale && 'border-amber-500/50 text-amber-700 dark:text-amber-400',
          )}
        >
          {stale ? `stale · ${formatAge(age)}` : `данные ${formatAge(age)}`}
        </Badge>
      )}
    </div>
  )
}
