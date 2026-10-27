import { Badge } from '@/components/ui/badge'
import { parseTimestamp } from '@/lib/datetime'
import { DOCS } from '@/lib/docsUrls'
import { cn } from '@/lib/utils'

type NocDataFreshnessProps = {
  timestamp?: string | null
  refreshIntervalSec?: number
  geoipMode?: 'local_mmdb' | 'ip_api' | 'none' | null
  dataSource?: string | null
  globalStats?: {
    dco_enabled: boolean | null
    max_bcast_mcast_queue: number | null
  } | null
  servedFromCache?: boolean
  className?: string
}

function dataAgeSec(timestamp?: string | null): number | null {
  const date = parseTimestamp(timestamp)
  if (!date) return null
  return Math.max(0, (Date.now() - date.getTime()) / 1000)
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
  if (source === 'db_fallback') return 'OVPN: сессии из БД'
  return 'Источник: н/д'
}

export default function NocDataFreshness({
  timestamp,
  refreshIntervalSec = 30,
  geoipMode,
  dataSource,
  globalStats,
  servedFromCache,
  className,
}: NocDataFreshnessProps) {
  const age = dataAgeSec(timestamp)
  const stale = age != null && age > refreshIntervalSec * 2

  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      <a
        href={DOCS.geoIp}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex"
        title="Инструкция GeoIP"
      >
        <Badge variant="outline" className="text-[10px] hover:border-primary/40">
          {geoipLabel(geoipMode)}
        </Badge>
      </a>
      <Badge variant={dataSource === 'management_socket' ? 'default' : 'secondary'} className="text-[10px]">
        {sourceLabel(dataSource)}
      </Badge>
      {globalStats?.dco_enabled != null && (
        <Badge
          variant={globalStats.dco_enabled ? 'default' : 'outline'}
          className="text-[10px]"
          title="Direct Crypto Offload: шифрование OpenVPN выполняется в ядре"
        >
          {globalStats.dco_enabled ? 'DCO: вкл' : 'DCO: выкл'}
        </Badge>
      )}
      {globalStats?.max_bcast_mcast_queue != null && (
        <Badge
          variant={globalStats.max_bcast_mcast_queue > 0 ? 'secondary' : 'outline'}
          className="text-[10px]"
          title="Максимальная длина очереди broadcast/multicast: рост = перегрузка"
        >
          очередь: {globalStats.max_bcast_mcast_queue}
        </Badge>
      )}
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
