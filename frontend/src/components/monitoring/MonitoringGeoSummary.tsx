import { useMemo } from 'react'
import { Building2, MapPin } from 'lucide-react'
import { Cell, Pie, PieChart, Tooltip } from 'recharts'
import { ChartResponsive } from '@/components/monitoring/ChartResponsive'
import {
  buildGeoPieSlices,
  collectMonitoringGeoConnections,
  type GeoPieSlice,
} from '@/components/monitoring/ConnectionAddress'
import MonitoringChartCard, { MonitoringChartEmpty } from '@/components/monitoring/MonitoringChartCard'
import {
  MONITORING_CHART_HEIGHT,
  getMonitoringSliceColor,
  getMonitoringSliceDotClass,
  monitoringChartTooltipProps,
} from '@/components/monitoring/monitoringChartTheme'
import { cn } from '@/lib/utils'
import type { OpenVpnClient, WireGuardPeer } from '@/types'

type MonitoringGeoSummaryProps = {
  openvpnClients: OpenVpnClient[]
  wireguardPeers: WireGuardPeer[]
  showOpenVpn: boolean
  showWireGuard: boolean
  isWireGuardOnline: (peer: WireGuardPeer) => boolean
  onlineOnly?: boolean
}

type GeoDonutCardProps = {
  title: string
  description: string
  icon: typeof MapPin
  slices: GeoPieSlice[]
  total: number
}

function GeoDonutLegend({ slices, total }: { slices: GeoPieSlice[]; total: number }) {
  return (
    <ul className="min-w-0 flex-1 space-y-2">
      {slices.map((slice, index) => {
        const percent = total > 0 ? Math.round((slice.value / total) * 100) : 0
        const othersCount = slice.breakdown?.length ?? 0
        return (
          <li key={slice.name} className="flex items-start gap-2 text-sm">
            <span className={cn('mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full', getMonitoringSliceDotClass(index))} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium leading-snug">
                {slice.name}
                {othersCount > 0 && (
                  <span className="font-normal text-muted-foreground"> · {othersCount} пров.</span>
                )}
              </p>
              <p className="text-xs text-muted-foreground tabular-nums">
                {slice.value} · {percent}%
              </p>
              {slice.breakdown && slice.breakdown.length > 0 && (
                <div className="mt-1.5 max-h-28 space-y-0.5 overflow-y-auto border-l border-border/60 pl-2 text-[11px] text-muted-foreground">
                  {slice.breakdown.map((entry) => (
                    <p key={entry.name} className="truncate leading-snug">
                      {entry.name} · {entry.value}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function GeoDonutCard({ title, description, icon, slices, total }: GeoDonutCardProps) {
  if (total === 0) {
    return (
      <MonitoringChartCard title={title} description={description} icon={icon}>
        <MonitoringChartEmpty>Нет подключений для сводки</MonitoringChartEmpty>
      </MonitoringChartCard>
    )
  }

  if (slices.length === 0) {
    return (
      <MonitoringChartCard title={title} description={description} icon={icon}>
        <MonitoringChartEmpty>Геоданные пока не определены</MonitoringChartEmpty>
      </MonitoringChartCard>
    )
  }

  return (
    <MonitoringChartCard title={title} description={description} icon={icon}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="monitoring-chart-frame relative mx-auto w-full max-w-[260px] shrink-0">
          <ChartResponsive className="h-full">
            {({ width, height }) => (
          <PieChart width={width} height={height}>
              <Pie
                data={slices}
                cx="50%"
                cy="50%"
                innerRadius={58}
                outerRadius={88}
                paddingAngle={3}
                dataKey="value"
              >
                {slices.map((_, index) => (
                  <Cell key={index} fill={getMonitoringSliceColor(index)} />
                ))}
              </Pie>
              <Tooltip
                {...monitoringChartTooltipProps}
                formatter={(value: number, _name, item) => {
                  const percent = total > 0 ? Math.round((value / total) * 100) : 0
                  const slice = item.payload as GeoPieSlice
                  if (slice.breakdown?.length) {
                    const detail = slice.breakdown.map((b) => `${b.name} (${b.value})`).join(', ')
                    return [`${value} (${percent}%) — ${detail}`, slice.name]
                  }
                  return [`${value} (${percent}%)`, slice.name]
                }}
              />
            </PieChart>
            )}
          </ChartResponsive>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold tabular-nums">{total}</span>
            <span className="text-xs text-muted-foreground">подключений</span>
          </div>
        </div>
        <GeoDonutLegend slices={slices} total={total} />
      </div>
    </MonitoringChartCard>
  )
}

export default function MonitoringGeoSummary({
  openvpnClients,
  wireguardPeers,
  showOpenVpn,
  showWireGuard,
  isWireGuardOnline,
  onlineOnly = true,
}: MonitoringGeoSummaryProps) {
  const geoConnections = useMemo(
    () =>
      collectMonitoringGeoConnections(openvpnClients, wireguardPeers, {
        showOpenVpn,
        showWireGuard,
        isWireGuardOnline,
        onlineOnly,
      }),
    [openvpnClients, wireguardPeers, showOpenVpn, showWireGuard, isWireGuardOnline, onlineOnly],
  )

  const citySlices = useMemo(() => buildGeoPieSlices(geoConnections, 'city'), [geoConnections])
  const ispSlices = useMemo(() => buildGeoPieSlices(geoConnections, 'isp'), [geoConnections])
  const total = geoConnections.length

  if (total === 0) return null

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <GeoDonutCard
        title="По городам"
        description="Распределение активных подключений"
        icon={MapPin}
        slices={citySlices}
        total={total}
      />
      <GeoDonutCard
        title="По провайдерам"
        description="Топ ISP; состав «Прочие» — в легенде справа"
        icon={Building2}
        slices={ispSlices}
        total={total}
      />
    </div>
  )
}
