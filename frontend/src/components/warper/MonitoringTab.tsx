import { Activity, BarChart3, FileText, Stethoscope } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Node, WarperHealthResponse, WarperStatusResponse } from '@/types'
import DoctorSection from './DoctorSection'
import LogsTab from './LogsTab'
import StatusSection from './StatusSection'
import TrafficTab from './TrafficTab'
import { cn } from '@/lib/utils'

interface MonitoringTabProps {
  health: WarperHealthResponse | null
  status: WarperStatusResponse | null
  loading: boolean
  loadError: string | null
  activeNode: Node | null
  onRefresh: () => void
  onToggled: () => void
}

function MonitorSection({
  title,
  icon: Icon,
  children,
  className,
}: {
  title: string
  icon: LucideIcon
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn('rounded-lg border bg-card/50 p-4', className)}>
      <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
          <Icon className="h-4 w-4" />
        </span>
        {title}
      </h3>
      {children}
    </section>
  )
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
  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-5">
        <MonitorSection title="Состояние и управление" icon={Activity} className="xl:col-span-3">
          <StatusSection
            embedded
            health={health}
            status={status}
            loading={loading}
            loadError={loadError}
            activeNode={activeNode}
            onRefresh={onRefresh}
            onToggled={onToggled}
          />
        </MonitorSection>
        <MonitorSection title="Трафик WARP" icon={BarChart3} className="xl:col-span-2">
          <TrafficTab embedded health={health} hideTitle />
        </MonitorSection>
      </div>

      <MonitorSection title="Логи sing-box" icon={FileText}>
        <LogsTab embedded health={health} hideTitle />
      </MonitorSection>

      <MonitorSection title="Диагностика" icon={Stethoscope}>
        <DoctorSection embedded health={health} activeNode={activeNode} hideTitle />
      </MonitorSection>
    </div>
  )
}
