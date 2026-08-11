import { Activity, Network, Shield, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import MetricCard from '@/components/noc/MetricCard'
import { Skeleton } from '@/components/ui/skeleton'
import type { Awg2HealthResponse, Awg2StatusResponse } from '@/types'
import { formatAwg2ClientCount, formatAwg2IfacePort } from './utils'

interface Awg2OverviewCardsProps {
  health: Awg2HealthResponse | null
  status: Awg2StatusResponse | null
  loading?: boolean
}

export default function Awg2OverviewCards({
  health,
  status,
  loading = false,
}: Awg2OverviewCardsProps) {
  const env = status?.services_env
  const azIfacePort = formatAwg2IfacePort(env?.AZ_IFACE, env?.AZ_PORT)
  const vpnIfacePort = formatAwg2IfacePort(env?.VPN_IFACE, env?.VPN_PORT)
  const missingCount = health?.missing_components?.length ?? 0
  const azSubnet = env?.AZ_SUBNET?.trim() || null
  const vpnSubnet = env?.VPN_SUBNET?.trim() || null

  if (loading && !health) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 rounded-xl border bg-card/80 p-3 shadow-sm">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-5 w-24" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Состояние"
        value={!health ? '—' : health.installed ? 'Установлен' : 'Не установлен'}
        sub={missingCount > 0 ? `${missingCount} компонентов` : azSubnet || vpnSubnet || 'слой AWG2'}
        icon={Activity}
        accent={health?.installed ? 'green' : health ? 'amber' : 'default'}
      />
      <Link
        to="/"
        className="block transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        title="Открыть Конфигурации"
      >
        <MetricCard
          label="Клиенты"
          value={formatAwg2ClientCount(status)}
          sub="Конфигурации → AmneziaWG 2.0"
          icon={Users}
          accent="cyan"
        />
      </Link>
      <MetricCard
        label="AntiZapret"
        value={azIfacePort}
        sub={azSubnet || 'iface · port'}
        icon={Shield}
        accent="amber"
      />
      <MetricCard
        label="VPN"
        value={vpnIfacePort}
        sub={vpnSubnet || 'iface · port'}
        icon={Network}
      />
    </div>
  )
}
