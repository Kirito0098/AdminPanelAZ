import { useCallback, useEffect, useState } from 'react'
import { Cloud, RefreshCw } from 'lucide-react'
import { getWarperDomains, getWarperHealth, getWarperStatus, getWarperTraffic } from '@/api/client'
import DomainsTab from '@/components/warper/DomainsTab'
import DoctorSection from '@/components/warper/DoctorSection'
import IpRangesTab from '@/components/warper/IpRangesTab'
import LogsTab from '@/components/warper/LogsTab'
import OverviewCards from '@/components/warper/OverviewCards'
import SettingsTab from '@/components/warper/SettingsTab'
import StatusSection from '@/components/warper/StatusSection'
import TrafficTab from '@/components/warper/TrafficTab'
import WarperAlerts from '@/components/warper/WarperAlerts'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import type { WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatNodeLabel } from '@/components/warper/utils'

export default function WarperPage() {
  const { activeNode } = useNode()
  const [health, setHealth] = useState<WarperHealthResponse | null>(null)
  const [status, setStatus] = useState<WarperStatusResponse | null>(null)
  const [domainCount, setDomainCount] = useState<number | null>(null)
  const [trafficToday, setTrafficToday] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const healthData = await getWarperHealth()
      setHealth(healthData)

      if (healthData.installed) {
        const [statusData, domainsData, trafficData] = await Promise.all([
          getWarperStatus().catch(() => null),
          getWarperDomains().catch(() => null),
          getWarperTraffic('today').catch(() => null),
        ])
        setStatus(statusData)
        setDomainCount(domainsData?.domains?.length ?? null)
        setTrafficToday(trafficData?.data ?? null)
      } else {
        setStatus(null)
        setDomainCount(null)
        setTrafficToday(null)
      }
    } catch (err) {
      setHealth(null)
      setStatus(null)
      setDomainCount(null)
      setTrafficToday(null)
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить AZ-WARP')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const nodeLabel = formatNodeLabel(health, activeNode)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Cloud className="h-7 w-7 text-primary" />
            AZ-WARP
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Точечная маршрутизация доменов и подсетей через Cloudflare WARP на узле{' '}
            <strong>{nodeLabel}</strong>. Управление sing-box, fake-IP и списками маршрутизации.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void load()} disabled={loading} className="shrink-0">
          <RefreshCw className={`mr-1.5 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Обновить всё
        </Button>
      </div>

      <WarperAlerts health={health} activeNode={activeNode} loadError={loadError} />

      <OverviewCards
        health={health}
        status={status}
        domainCount={domainCount}
        trafficToday={trafficToday}
      />

      <Tabs defaultValue="domains" className="space-y-4">
        <TabsList className="flex h-auto flex-wrap justify-start gap-1">
          <TabsTrigger value="domains">Домены</TabsTrigger>
          <TabsTrigger value="ip-ranges">IP-подсети</TabsTrigger>
          <TabsTrigger value="traffic">Трафик</TabsTrigger>
          <TabsTrigger value="status">Статус</TabsTrigger>
          <TabsTrigger value="settings">Настройки</TabsTrigger>
          <TabsTrigger value="logs">Логи</TabsTrigger>
          <TabsTrigger value="doctor">Диагностика</TabsTrigger>
        </TabsList>

        <TabsContent value="domains">
          <DomainsTab health={health} onDomainsChange={setDomainCount} />
        </TabsContent>

        <TabsContent value="ip-ranges">
          <IpRangesTab health={health} />
        </TabsContent>

        <TabsContent value="traffic">
          <TrafficTab health={health} />
        </TabsContent>

        <TabsContent value="status">
          <StatusSection
            health={health}
            status={status}
            loading={loading}
            loadError={loadError}
            activeNode={activeNode}
            onRefresh={() => void load()}
            onToggled={() => void load()}
          />
        </TabsContent>

        <TabsContent value="settings">
          <SettingsTab health={health} />
        </TabsContent>

        <TabsContent value="logs">
          <LogsTab health={health} />
        </TabsContent>

        <TabsContent value="doctor">
          <DoctorSection health={health} activeNode={activeNode} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
