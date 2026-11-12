import { useState } from 'react'
import { Activity, FileText, Stethoscope } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { Node, WarperHealthResponse, WarperStatusResponse } from '@/types'
import DoctorSection from './DoctorSection'
import LogsTab from './LogsTab'
import StatusSection from './StatusSection'
import TrafficTab from './TrafficTab'
import WarperSection from './WarperSection'

interface MonitoringTabProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  loadError: string | null
  activeNode: Node | null
}

type MonitorView = 'overview' | 'logs' | 'doctor'

export default function MonitoringTab({ health, status, loadError, activeNode }: MonitoringTabProps) {
  const [view, setView] = useState<MonitorView>('overview')

  return (
    <div className="space-y-4">
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
            <StatusSection health={health} status={status} activeNode={activeNode} />
            <div className="my-5 border-t" />
            <div className="mb-4">
              <h4 className="text-sm font-medium">Трафик WARP</h4>
              <p className="text-xs text-muted-foreground">Статистика по периодам</p>
            </div>
            <TrafficTab health={health} />
          </WarperSection>
        </TabsContent>

        <TabsContent value="logs" className="mt-0 focus-visible:outline-none">
          <WarperSection
            title="Логи sing-box"
            icon={FileText}
            description="Последние строки журнала с фильтром по тексту"
          >
            <LogsTab health={health} />
          </WarperSection>
        </TabsContent>

        <TabsContent value="doctor" className="mt-0 focus-visible:outline-none">
          <WarperSection
            title="Диагностика AZ-WARP"
            icon={Stethoscope}
            description="Проверка sing-box, kresd и конфигурации"
          >
            <DoctorSection health={health} activeNode={activeNode} />
          </WarperSection>
        </TabsContent>
      </Tabs>
    </div>
  )
}
