import { useCallback, useEffect, useState } from 'react'
import { Activity, Globe, Network, Settings2 } from 'lucide-react'
import { getWarperDomains, getWarperHealth, getWarperStatus, getWarperTraffic } from '@/api/client'
import DomainsTab from '@/components/warper/DomainsTab'
import IpRangesTab from '@/components/warper/IpRangesTab'
import MonitoringTab from '@/components/warper/MonitoringTab'
import OverviewCards from '@/components/warper/OverviewCards'
import SettingsTab from '@/components/warper/SettingsTab'
import WarperAlerts from '@/components/warper/WarperAlerts'
import WarperHero from '@/components/warper/WarperHero'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import type { WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatNodeLabel, type WarperTab } from '@/components/warper/utils'

export default function WarperPage() {
  const { activeNode } = useNode()
  const [tab, setTab] = useState<WarperTab>('domains')
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
    <div className="space-y-5">
      <WarperHero
        health={health}
        loading={loading}
        nodeLabel={nodeLabel}
        onRefresh={() => void load()}
        onToggled={() => void load()}
      />

      <WarperAlerts health={health} activeNode={activeNode} loadError={loadError} />

      <OverviewCards
        health={health}
        status={status}
        domainCount={domainCount}
        trafficToday={trafficToday}
        loading={loading}
        onNavigate={setTab}
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as WarperTab)} className="space-y-4">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1 bg-muted/50 p-1 sm:inline-flex sm:w-auto">
          <TabsTrigger value="domains" className="gap-1.5 data-[state=active]:shadow-sm">
            <Globe className="h-4 w-4" />
            <span>Домены</span>
          </TabsTrigger>
          <TabsTrigger value="ip-ranges" className="gap-1.5 data-[state=active]:shadow-sm">
            <Network className="h-4 w-4" />
            <span>IP-подсети</span>
          </TabsTrigger>
          <TabsTrigger value="monitoring" className="gap-1.5 data-[state=active]:shadow-sm">
            <Activity className="h-4 w-4" />
            <span>Мониторинг</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-1.5 data-[state=active]:shadow-sm">
            <Settings2 className="h-4 w-4" />
            <span>Настройки</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="domains" className="mt-0 focus-visible:outline-none">
          <DomainsTab health={health} onDomainsChange={setDomainCount} />
        </TabsContent>

        <TabsContent value="ip-ranges" className="mt-0 focus-visible:outline-none">
          <IpRangesTab health={health} />
        </TabsContent>

        <TabsContent value="monitoring" className="mt-0 focus-visible:outline-none">
          <MonitoringTab
            health={health}
            status={status}
            loading={loading}
            loadError={loadError}
            activeNode={activeNode}
            onRefresh={() => void load()}
            onToggled={() => void load()}
          />
        </TabsContent>

        <TabsContent value="settings" className="mt-0 focus-visible:outline-none">
          <SettingsTab health={health} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
