import { Eye, RefreshCw, Server, Shield, Users } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { getAwg2Health, getAwg2Status } from '@/api/client'
import ClientsTab from '@/components/awg2/ClientsTab'
import Awg2HelpStub from '@/components/awg2/Awg2HelpStub'
import Awg2InstallPrompt from '@/components/awg2/Awg2InstallPrompt'
import ObfuscationTab from '@/components/awg2/ObfuscationTab'
import { formatAwg2NodeLabel } from '@/components/awg2/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { useNode } from '@/context/NodeContext'
import { cn } from '@/lib/utils'
import type { Awg2HealthResponse, Awg2StatusResponse } from '@/types'

type Awg2Tab = 'clients' | 'obfuscation' | 'help'

function statusMeta(health: Awg2HealthResponse | null) {
  if (!health) {
    return { label: 'Нет данных', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
  if (!health.installed) {
    return { label: 'Не установлен', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  return { label: 'Установлен', variant: 'success' as const, dot: 'bg-emerald-500' }
}

export default function Awg2Page() {
  const { activeNode } = useNode()
  const [tab, setTab] = useState<Awg2Tab>('clients')
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
  const meta = statusMeta(health)

  return (
    <div className="space-y-5">
      <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-card via-card to-muted/30 p-5 shadow-sm">
        <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-primary/5" />
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Shield className="h-6 w-6" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-semibold tracking-tight">AZ-AWG2</h1>
                {loading ? (
                  <Skeleton className="h-6 w-24 rounded-full" />
                ) : (
                  <Badge variant={meta.variant} className="gap-1.5">
                    <span className={cn('h-2 w-2 rounded-full', meta.dot)} />
                    {meta.label}
                  </Badge>
                )}
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
                <Server className="h-3.5 w-3.5 shrink-0" />
                <span>{nodeLabel}</span>
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5 self-start sm:self-auto" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
        </div>
      </div>

      {loadError && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {loadError}
        </div>
      )}

      {ready ? (
        <div className="space-y-4">
          {status?.services_env && (
            <div className="rounded-xl border bg-card/50 p-4 text-sm">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Слой на узле</p>
              <dl className="grid gap-2 sm:grid-cols-2">
                {status.services_env.AZ_IFACE && (
                  <div>
                    <dt className="text-muted-foreground">AntiZapret iface</dt>
                    <dd className="font-mono text-xs">{status.services_env.AZ_IFACE}</dd>
                  </div>
                )}
                {status.services_env.VPN_IFACE && (
                  <div>
                    <dt className="text-muted-foreground">VPN iface</dt>
                    <dd className="font-mono text-xs">{status.services_env.VPN_IFACE}</dd>
                  </div>
                )}
                {status.services_env.AZ_PORT && (
                  <div>
                    <dt className="text-muted-foreground">AntiZapret port</dt>
                    <dd className="font-mono text-xs">{status.services_env.AZ_PORT}</dd>
                  </div>
                )}
                {status.services_env.VPN_PORT && (
                  <div>
                    <dt className="text-muted-foreground">VPN port</dt>
                    <dd className="font-mono text-xs">{status.services_env.VPN_PORT}</dd>
                  </div>
                )}
              </dl>
              <p className="mt-3 text-muted-foreground">
                Клиенты и обфускация — во вкладках ниже. Если нужно обновить слой, используйте команду установки.
              </p>
            </div>
          )}
          <Tabs value={tab} onValueChange={(value) => setTab(value as Awg2Tab)} className="space-y-4">
            <TabsList className="flex h-auto w-full flex-wrap gap-1 bg-muted/50 p-1">
              <TabsTrigger value="clients" className="gap-1.5">
                <Users className="h-4 w-4" />
                <span>Клиенты</span>
              </TabsTrigger>
              <TabsTrigger value="obfuscation" className="gap-1.5">
                <Eye className="h-4 w-4" />
                <span>Обфускация</span>
              </TabsTrigger>
              <TabsTrigger value="help" className="gap-1.5">
                <Shield className="h-4 w-4" />
                <span>Справка</span>
              </TabsTrigger>
            </TabsList>

            <TabsContent value="clients" className="mt-0 focus-visible:outline-none">
              <ClientsTab health={health} />
            </TabsContent>

            <TabsContent value="obfuscation" className="mt-0 focus-visible:outline-none">
              <ObfuscationTab health={health} />
            </TabsContent>

            <TabsContent value="help" className="mt-0 focus-visible:outline-none">
              <Awg2HelpStub health={health} />
            </TabsContent>
          </Tabs>
        </div>
      ) : !loading ? (
        <Awg2InstallPrompt health={health} activeNode={activeNode} />
      ) : null}
    </div>
  )
}
