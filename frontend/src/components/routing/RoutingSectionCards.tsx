import { CloudDownload, FlaskConical, LayoutDashboard, Route } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { ROUTING_TAB_UPDATE, STAGE_BUILD, STAGE_DEPLOY, WORKFLOW_CHAIN } from './routingLabels'
import type { RoutingTab, RoutingWorkflowState } from './routingWorkflow'

interface RoutingSectionCardsProps {
  workflow: RoutingWorkflowState
  isAdmin: boolean
  activeTab: RoutingTab
  onNavigate: (tab: RoutingTab) => void
}

export default function RoutingSectionCards({
  workflow,
  isAdmin,
  activeTab,
  onNavigate,
}: RoutingSectionCardsProps) {
  const cards: Array<{
    key: RoutingTab
    title: string
    icon: typeof Route
    value: string
    sub: string
    accent: string
    tone?: string
    adminOnly?: boolean
  }> = [
    {
      key: 'overview',
      title: 'Обзор',
      icon: LayoutDashboard,
      value: `${workflow.enabledCount} активных`,
      sub: `${workflow.totalProviders} провайдеров · маршруты и статистика`,
      accent: activeTab === 'overview' ? 'border-l-primary' : 'border-l-muted-foreground/30',
    },
    {
      key: 'analysis',
      title: 'Анализ',
      icon: FlaskConical,
      value: 'DPI лог',
      sub: 'Рекомендации по CIDR из checker',
      accent: activeTab === 'analysis' ? 'border-l-primary' : 'border-l-muted-foreground/30',
    },
    {
      key: 'pipeline',
      title: ROUTING_TAB_UPDATE,
      icon: CloudDownload,
      value:
        workflow.currentStage != null && workflow.currentStage <= 3
          ? `Этап ${workflow.currentStage}`
          : 'Готов',
      sub:
        workflow.pendingCompileCount > 0
          ? `${workflow.pendingCompileCount} к ${STAGE_BUILD.toLowerCase()}`
          : workflow.pendingDeployCount > 0
            ? `${workflow.pendingDeployCount} к ${STAGE_DEPLOY.toLowerCase()}`
            : WORKFLOW_CHAIN,
      accent:
        workflow.currentStage != null && workflow.currentStage <= 3
          ? 'border-l-sky-500'
          : activeTab === 'pipeline'
            ? 'border-l-primary'
            : 'border-l-muted-foreground/30',
      tone:
        workflow.currentStage != null && workflow.currentStage <= 3
          ? 'text-sky-600 dark:text-sky-400'
          : workflow.currentStage == null
            ? 'text-emerald-600 dark:text-emerald-400'
            : undefined,
      adminOnly: true,
    },
    {
      key: 'providers',
      title: 'Провайдеры',
      icon: Route,
      value:
        workflow.onNodeCount > 0
          ? `${workflow.enabledCount}/${workflow.onNodeCount} вкл.`
          : 'Нет на узле',
      sub:
        workflow.pendingDeployCount > 0
          ? `${workflow.pendingDeployCount} ждут ${STAGE_DEPLOY.toLowerCase()}`
          : 'Включение списков для VPN',
      accent:
        workflow.currentStage === 4
          ? 'border-l-amber-500'
          : activeTab === 'providers'
            ? 'border-l-primary'
            : 'border-l-muted-foreground/30',
      tone: workflow.currentStage === 4 ? 'text-amber-600 dark:text-amber-400' : undefined,
    },
  ]

  const visible = cards.filter((c) => !c.adminOnly || isAdmin)

  return (
    <div className={cn('grid gap-3 sm:grid-cols-2', visible.length >= 4 ? 'xl:grid-cols-4' : visible.length === 3 ? 'lg:grid-cols-3' : '')}>
      {visible.map((card) => (
        <button
          key={card.key}
          type="button"
          onClick={() => onNavigate(card.key)}
          className="group text-left"
        >
          <Card
            className={cn(
              'h-full border-l-4 transition-colors hover:bg-muted/40',
              card.accent,
              activeTab === card.key && 'bg-muted/20',
            )}
          >
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {card.title}
                </span>
                <div className="rounded-md bg-muted p-1.5 text-muted-foreground group-hover:text-primary">
                  <card.icon size={14} />
                </div>
              </div>
              <div className={cn('mt-2 text-xl font-bold tracking-tight', card.tone)}>{card.value}</div>
              <p className="mt-1 text-xs text-muted-foreground">{card.sub}</p>
            </CardContent>
          </Card>
        </button>
      ))}
    </div>
  )
}
