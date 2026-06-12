import { Activity, ArrowDown, ArrowUp, Globe, Network } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatBytes } from './utils'

interface OverviewCardsProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  domainCount: number | null
  trafficToday: Record<string, unknown> | null
}

function readNumber(obj: Record<string, unknown> | null | undefined, ...keys: string[]): number | null {
  if (!obj) return null
  for (const key of keys) {
    const value = obj[key]
    if (typeof value === 'number') return value
  }
  return null
}

export default function OverviewCards({ health, status, domainCount, trafficToday }: OverviewCardsProps) {
  const statusData = status?.status ?? {}
  const outboundMode =
    typeof statusData.outbound_mode === 'string' ? statusData.outbound_mode : null
  const rx = readNumber(trafficToday, 'period_rx', 'rx', 'download')
  const tx = readNumber(trafficToday, 'period_tx', 'tx', 'upload')

  const cards = [
    {
      title: 'Состояние',
      icon: Activity,
      value: !health ? '—' : health.installed ? (health.active ? 'Активен' : 'Выключен') : 'Не установлен',
      sub: health?.version ? `v${health.version}` : outboundMode ? `Режим: ${outboundMode}` : undefined,
      tone: health?.active ? 'text-emerald-600 dark:text-emerald-400' : undefined,
    },
    {
      title: 'Домены',
      icon: Globe,
      value: domainCount == null ? '—' : String(domainCount),
      sub: 'в списке маршрутизации',
    },
    {
      title: 'Трафик сегодня ↑',
      icon: ArrowUp,
      value: rx == null ? '—' : formatBytes(rx),
      sub: 'исходящий через WARP',
    },
    {
      title: 'Трафик сегодня ↓',
      icon: ArrowDown,
      value: tx == null ? '—' : formatBytes(tx),
      sub: 'входящий через WARP',
    },
  ]

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.title}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">{card.title}</CardTitle>
            <card.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold tracking-tight ${card.tone ?? ''}`}>{card.value}</div>
            {card.sub && <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>}
          </CardContent>
        </Card>
      ))}
      {typeof statusData.fake_subnet === 'string' && (
        <Card className="sm:col-span-2 xl:col-span-4">
          <CardContent className="flex flex-wrap items-center gap-2 pt-6">
            <Network className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Fake-подсеть:</span>
            <Badge variant="outline" className="font-mono">
              {statusData.fake_subnet}
            </Badge>
            {outboundMode && <Badge variant="secondary">outbound: {outboundMode}</Badge>}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
