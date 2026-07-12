import { useState } from 'react'
import { Activity, FileText, Power, RefreshCw, Stethoscope } from 'lucide-react'
import { postWarperToggle } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useNotifications } from '@/context/NotificationContext'
import type { Node, WarperHealthResponse, WarperStatusResponse } from '@/types'
import { cn } from '@/lib/utils'
import DoctorSection from './DoctorSection'
import LogsTab from './LogsTab'
import StatusSection from './StatusSection'
import TrafficTab from './TrafficTab'
import WarperSection from './WarperSection'
import { formatOutboundMode, isWarperDisabled } from './utils'

interface MonitoringTabProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  loading: boolean
  loadError: string | null
  activeNode: Node | null
  onRefresh: () => void
  onToggled: () => void
}

type MonitorView = 'overview' | 'logs' | 'doctor'

function readSingboxRunning(status: WarperStatusResponse | null): boolean | null {
  const singbox = status?.status?.singbox
  if (!singbox || typeof singbox !== 'object') return null
  return typeof (singbox as Record<string, unknown>).running === 'boolean'
    ? ((singbox as Record<string, unknown>).running as boolean)
    : null
}

export default function MonitoringTab({
  health,
  status,
  loading,
  loadError,
  activeNode,
  onRefresh,
  onToggled,
}: MonitoringTabProps) {
  const { success, error: notifyError } = useNotifications()
  const [view, setView] = useState<MonitorView>('overview')
  const disabled = isWarperDisabled(health)

  const outboundMode =
    typeof status?.status?.outbound_mode === 'string' ? status.status.outbound_mode : null
  const singboxRunning = readSingboxRunning(status)

  async function handleToggle() {
    try {
      const result = await postWarperToggle()
      success(result.message ?? 'AZ-WARP переключён')
      onToggled()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить AZ-WARP')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {health?.installed && (
            <Badge variant={health.active ? 'success' : 'secondary'}>
              {health.active ? 'AZ-WARP активен' : 'AZ-WARP выключен'}
            </Badge>
          )}
          {outboundMode && <Badge variant="outline">Режим: {formatOutboundMode(outboundMode)}</Badge>}
          {singboxRunning != null && (
            <Badge variant={singboxRunning ? 'success' : 'secondary'}>
              sing-box {singboxRunning ? 'запущен' : 'остановлен'}
            </Badge>
          )}
          {health?.version && <Badge variant="outline">v{health.version}</Badge>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
          <Button
            type="button"
            size="sm"
            variant={health?.active ? 'secondary' : 'default'}
            onClick={() => void handleToggle()}
            disabled={loading || disabled}
          >
            <Power className="mr-1.5 h-4 w-4" />
            {health?.active ? 'Выключить' : 'Включить'}
          </Button>
        </div>
      </div>

      {loadError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {loadError}
        </p>
      )}

      <Tabs value={view} onValueChange={(value) => setView(value as MonitorView)} className="space-y-4">
        <TabsList className="flex h-auto w-full snap-x snap-mandatory gap-1 overflow-x-auto bg-muted/50 p-1 [-ms-overflow-style:none] [scrollbar-width:none] sm:inline-flex sm:w-auto sm:overflow-visible sm:snap-none [&::-webkit-scrollbar]:hidden">
          <TabsTrigger value="overview" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Activity className="h-4 w-4" />
            Обзор
          </TabsTrigger>
          <TabsTrigger value="logs" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <FileText className="h-4 w-4" />
            Логи
          </TabsTrigger>
          <TabsTrigger value="doctor" className="shrink-0 snap-start gap-1.5 data-[state=active]:shadow-sm">
            <Stethoscope className="h-4 w-4" />
            <span className="sm:hidden">Доктор</span>
            <span className="hidden sm:inline">Диагностика</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-0 space-y-4 focus-visible:outline-none">
          <WarperSection
            title="Обзор"
            icon={Activity}
            description="Состояние sing-box, kresd и статистика WARP"
          >
            <StatusSection
              embedded
              compact
              showMetrics
              health={health}
              status={status}
              loading={loading}
              loadError={null}
              activeNode={activeNode}
              onRefresh={onRefresh}
              onToggled={onToggled}
            />
            <div className="my-5 border-t" />
            <div className="mb-4">
              <h4 className="text-sm font-medium">Трафик WARP</h4>
              <p className="text-xs text-muted-foreground">Статистика по периодам</p>
            </div>
            <TrafficTab embedded health={health} hideTitle />
          </WarperSection>
        </TabsContent>

        <TabsContent value="logs" className="mt-0 focus-visible:outline-none">
          <WarperSection
            title="Логи sing-box"
            icon={FileText}
            description="Последние строки журнала с фильтром по тексту"
          >
            <LogsTab embedded health={health} hideTitle />
          </WarperSection>
        </TabsContent>

        <TabsContent value="doctor" className="mt-0 focus-visible:outline-none">
          <WarperSection
            title="Диагностика AZ-WARP"
            icon={Stethoscope}
            description="Проверка sing-box, kresd и конфигурации"
          >
            <DoctorSection embedded health={health} activeNode={activeNode} hideTitle />
          </WarperSection>
        </TabsContent>
      </Tabs>
    </div>
  )
}
