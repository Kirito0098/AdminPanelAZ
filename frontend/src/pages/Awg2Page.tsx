import { Download, Eye, Shield } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getAwg2Health, getAwg2Status } from '@/api/client'
import Awg2Hero from '@/components/awg2/Awg2Hero'
import Awg2OverviewCards from '@/components/awg2/Awg2OverviewCards'
import BackupTab from '@/components/awg2/BackupTab'
import Awg2HelpStub from '@/components/awg2/Awg2HelpStub'
import Awg2InstallPrompt from '@/components/awg2/Awg2InstallPrompt'
import ObfuscationTab from '@/components/awg2/ObfuscationTab'
import { formatAwg2NodeLabel, type Awg2Tab } from '@/components/awg2/utils'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNode } from '@/context/NodeContext'
import type { Awg2HealthResponse, Awg2StatusResponse } from '@/types'

export default function Awg2Page() {
  const { activeNode } = useNode()
  const [tab, setTab] = useState<Awg2Tab>('obfuscation')
  const [health, setHealth] = useState<Awg2HealthResponse | null>(null)
  const [status, setStatus] = useState<Awg2StatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const healthData = await getAwg2Health()
      setHealth(healthData)
      if (healthData.installed) {
        const statusData = await getAwg2Status().catch(() => null)
        setStatus(statusData)
      } else {
        setStatus(null)
      }
    } catch (err) {
      setHealth(null)
      setStatus(null)
      setLoadError(err instanceof Error ? err.message : 'Не удалось загрузить AZ-AWG2')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, activeNode?.id])

  const nodeLabel = formatAwg2NodeLabel(health, activeNode)
  const ready = Boolean(health?.installed)

  return (
    <div className="space-y-6">
      <Awg2Hero
        health={health}
        loading={loading}
        nodeLabel={nodeLabel}
        onRefresh={() => void load()}
        onUpdated={() => void load()}
      />

      {loadError && (
        <SettingsAlert variant="danger" title="Ошибка загрузки">
          {loadError}
        </SettingsAlert>
      )}

      {ready && (
        <SettingsAlert variant="info" title="Данные активного узла">
          Слой AmneziaWG 2.0 управляется на{' '}
          <strong>{activeNode?.name ?? nodeLabel}</strong>
          {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
          Клиенты — на странице{' '}
          <Link to="/" className="font-medium text-foreground underline-offset-2 hover:underline">
            Конфигурации
          </Link>{' '}
          (вкладка AmneziaWG 2.0). install-base и перезагрузка — только по SSH.
        </SettingsAlert>
      )}

      {ready && <Awg2OverviewCards health={health} status={status} loading={loading} />}

      {ready ? (
        <Tabs value={tab} onValueChange={(v) => setTab(v as Awg2Tab)} className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <TabsList className="flex h-auto w-full flex-wrap gap-1 bg-muted/50 p-1 sm:inline-flex sm:w-auto">
              <TabsTrigger value="obfuscation" className="gap-1.5">
                <Eye className="h-4 w-4" />
                Обфускация
              </TabsTrigger>
              <TabsTrigger value="backup" className="gap-1.5">
                <Download className="h-4 w-4" />
                Бэкап
              </TabsTrigger>
              <TabsTrigger value="help" className="gap-1.5">
                <Shield className="h-4 w-4" />
                Справка
              </TabsTrigger>
            </TabsList>
            <Button asChild variant="outline" size="sm">
              <Link to="/">Конфигурации · AmneziaWG 2.0</Link>
            </Button>
          </div>

          <TabsContent value="obfuscation" className="mt-0 focus-visible:outline-none">
            <ObfuscationTab health={health} />
          </TabsContent>

          <TabsContent value="backup" className="mt-0 focus-visible:outline-none">
            <BackupTab onRestored={() => void load()} />
          </TabsContent>

          <TabsContent value="help" className="mt-0 focus-visible:outline-none">
            <Awg2HelpStub health={health} />
          </TabsContent>
        </Tabs>
      ) : !loading ? (
        <Awg2InstallPrompt health={health} activeNode={activeNode} onInstalled={() => void load()} />
      ) : null}
    </div>
  )
}
