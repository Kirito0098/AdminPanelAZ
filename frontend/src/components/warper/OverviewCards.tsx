import { Activity, ArrowDown, ArrowUp, Globe, Network } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatBytes, formatOutboundMode, type WarperTab } from './utils'

interface OverviewCardsProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  domainCount: number | null
  trafficToday: Record<string, unknown> | null
  loading?: boolean
  onNavigate?: (tab: WarperTab) => void
}

function readNumber(obj: Record<string, unknown> | null | undefined, ...keys: string[]): number | null {
  if (!obj) return null
  for (const key of keys) {
    const value = obj[key]
    if (typeof value === 'number') return value
  }
  return null
}

export default function OverviewCards({
  health,
  status,
  domainCount,
  trafficToday,
  loading = false,
  onNavigate,
}: OverviewCardsProps) {
  const statusData = status?.status ?? {}
  const outboundMode =
    typeof statusData.outbound_mode === 'string' ? statusData.outbound_mode : null
  const subnetBlock =
    statusData.subnet && typeof statusData.subnet === 'object'
      ? (statusData.subnet as Record<string, unknown>)
      : null
  const fakeSubnet =
    subnetBlock && typeof subnetBlock.fake === 'string'
      ? subnetBlock.fake
      : typeof statusData.fake_subnet === 'string'
        ? statusData.fake_subnet
        : null
  const tx = readNumber(trafficToday, 'period_tx', 'tx', 'upload')
  const rx = readNumber(trafficToday, 'period_rx', 'rx', 'download')

  const cards: Array<{
    key: WarperTab
    title: string
    icon: typeof Activity
    value: string
    sub?: string
    accent: string
    tone?: string
  }> = [
    {
      key: 'monitoring',
      title: 'Состояние',
      icon: Activity,
      value: !health ? '—' : health.installed ? (health.active ? 'Активен' : 'Выключен') : 'Не установлен',
      sub: health?.version
        ? `v${health.version}`
        : outboundMode
          ? formatOutboundMode(outboundMode)
          : undefined,
      accent: health?.active
        ? 'border-l-emerald-500'
        : health?.installed
          ? 'border-l-amber-500'
          : 'border-l-muted-foreground/30',
      tone: health?.active ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      key: 'domains',
      title: 'Домены',
      icon: Globe,
      value: domainCount == null ? '—' : String(domainCount),
      sub: 'в маршрутизации',
      accent: 'border-l-primary',
    },
    {
      key: 'monitoring',
      title: 'Исходящий',
      icon: ArrowUp,
      value: tx == null ? '—' : formatBytes(tx),
      sub: 'сегодня через WARP',
      accent: 'border-l-sky-500',
    },
    {
      key: 'monitoring',
      title: 'Входящий',
      icon: ArrowDown,
      value: rx == null ? '—' : formatBytes(rx),
      sub: 'сегодня через WARP',
      accent: 'border-l-violet-500',
    },
  ]

  if (loading && !health) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="border-l-4 border-l-muted">
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-20" />
              <Skeleton className="mt-2 h-3 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card, index) => (
          <Card
            key={`${card.key}-${card.title}-${index}`}
            className={cn(
              'border-l-4 transition-colors',
              card.accent,
              onNavigate && 'cursor-pointer hover:bg-muted/40',
            )}
            onClick={onNavigate ? () => onNavigate(card.key) : undefined}
            onKeyDown={
              onNavigate
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onNavigate(card.key)
                    }
                  }
                : undefined
            }
            role={onNavigate ? 'button' : undefined}
            tabIndex={onNavigate ? 0 : undefined}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{card.title}</CardTitle>
              <card.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className={cn('text-2xl font-bold tracking-tight', card.tone)}>{card.value}</div>
              {card.sub && <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>}
            </CardContent>
          </Card>
        ))}
      </div>

      {fakeSubnet && (
        <Card className="border-dashed">
          <CardContent className="flex flex-wrap items-center gap-2 py-4">
            <Network className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Fake-подсеть</span>
            <code className="rounded-md bg-muted px-2 py-0.5 font-mono text-sm">{fakeSubnet}</code>
            {outboundMode && (
              <span className="text-sm text-muted-foreground">
                · режим <strong>{formatOutboundMode(outboundMode)}</strong>
              </span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
