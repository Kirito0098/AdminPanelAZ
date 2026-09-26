import { useCallback, useEffect, useState } from 'react'
import { Activity, Globe, Library, Network, Settings2 } from 'lucide-react'
import { getWarperDomains, getWarperHealth, getWarperStatus, getWarperTraffic } from '@/api/client'
import CatalogTab from '@/components/warper/CatalogTab'
import DomainsTab from '@/components/warper/DomainsTab'
import IpRangesTab from '@/components/warper/IpRangesTab'
import MonitoringTab from '@/components/warper/MonitoringTab'
import OverviewCards from '@/components/warper/OverviewCards'
import SettingsTab from '@/components/warper/SettingsTab'
import WarperAlerts from '@/components/warper/WarperAlerts'
import WarperHero from '@/components/warper/WarperHero'
import WarperInstallPrompt from '@/components/warper/WarperInstallPrompt'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import { useLatestRequest } from '@/hooks/useLatestRequest'
import { runLatest } from '@/lib/latestRequest'
import type { WarperDomainsResponse, WarperHealthResponse, WarperStatusResponse } from '@/types'
import { formatNodeLabel, type WarperTab } from '@/components/warper/utils'

export default function WarperPage() {
  const { activeNode } = useNode()
  const [tab, setTab] = useState<WarperTab>('domains')
  const [health, setHealth] = useState<WarperHealthResponse | null>(null)
  const [status, setStatus] = useState<WarperStatusResponse | null>(null)
  const [domainsPayload, setDomainsPayload] = useState<WarperDomainsResponse | null>(null)
  const [domainCount, setDomainCount] = useState<number | null>(null)
  const [trafficToday, setTrafficToday] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const activeNodeId = activeNode?.id ?? null
  const [loadedNodeId, setLoadedNodeId] = useState<number | null | undefined>(undefined)
  const requests = useLatestRequest(activeNodeId)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    await runLatest(
      requests,
      async () => {
        const healthData = await getWarperHealth()
        if (!healthData.installed) return { healthData, statusData: null, domainsData: null, trafficData: null }
        const [statusData, domainsData, trafficData] = await Promise.all([
          getWarperStatus().catch(() => null),
          getWarperDomains().catch(() => null),
          getWarperTraffic('today').catch(() => null),
        ])
        return { healthData, statusData, domainsData, trafficData }
      },
      {
        apply: ({ healthData, statusData, domainsData, trafficData }) => {
          setLoadedNodeId(activeNodeId)
          setHealth(healthData)
          setStatus(statusData)
          setDomainsPayload(domainsData)
          setDomainCount(domainsData?.domains?.length ?? null)
          setTrafficToday(trafficData?.data ?? null)
        },
        fail: (err) => {
          setLoadedNodeId(activeNodeId)
          setHealth(null)
          setStatus(null)
          setDomainsPayload(null)
          setDomainCount(null)
          setTrafficToday(null)
          setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить AZ-WARP')
        },
        settle: () => setLoading(false),
      },
    )
  }, [activeNodeId, requests])

  useEffect(() => {
    void load()
  }, [load])

  const nodeLabel = formatNodeLabel(health, activeNode)
  const warperReady = Boolean(health?.installed)

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

      {warperReady && (
        <OverviewCards
          health={health}
          status={status}
          domainCount={domainCount}
          trafficToday={trafficToday}
          loading={loading}
          onNavigate={setTab}
        />
      )}

      {warperReady ? (
      <Tabs value={tab} onValueChange={(v) => setTab(v as WarperTab)} className="space-y-4">
        <TabsList className="flex h-auto w-full snap-x snap-mandatory gap-1 overflow-x-auto bg-muted/50 p-1 [-ms-overflow-style:none] [scrollbar-width:none] sm:inline-flex sm:w-auto sm:overflow-visible sm:snap-none [&::-webkit-scrollbar]:hidden">
          <TabsTrigger value="domains" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Globe className="h-4 w-4" />
            <span>Домены</span>
          </TabsTrigger>
          <TabsTrigger value="catalog" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Library className="h-4 w-4" />
            <span>Каталог</span>
          </TabsTrigger>
          <TabsTrigger value="ip-ranges" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Network className="h-4 w-4" />
            <span className="sm:hidden">Подсети</span>
            <span className="hidden sm:inline">IP-подсети</span>
          </TabsTrigger>
          <TabsTrigger value="monitoring" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Activity className="h-4 w-4" />
            <span className="sm:hidden">Монит.</span>
            <span className="hidden sm:inline">Мониторинг</span>
          </TabsTrigger>
          <TabsTrigger value="settings" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Settings2 className="h-4 w-4" />
            <span className="sm:hidden">Настр.</span>
            <span className="hidden sm:inline">Настройки</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="domains" className="mt-0 focus-visible:outline-none">
          <DomainsTab
            health={health}
            initialDomains={loading || loadedNodeId !== activeNodeId ? undefined : domainsPayload}
            onDomainsChange={setDomainCount}
          />
        </TabsContent>

        <TabsContent value="catalog" className="mt-0 focus-visible:outline-none">
          <CatalogTab health={health} onDomainsChange={() => void load()} />
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
      ) : !loading ? (
        <WarperInstallPrompt health={health} activeNode={activeNode} />
      ) : null}
    </div>
  )
}
