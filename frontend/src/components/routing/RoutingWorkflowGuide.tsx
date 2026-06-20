import { ArrowRight, Check, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { RoutingTab, RoutingWorkflowState } from './routingWorkflow'
import { ROUTING_TAB_UPDATE, STAGE_DEPLOY, WORKFLOW_CHAIN } from './routingLabels'
import { pluralProviders } from './utils'

interface RoutingWorkflowGuideProps {
  workflow: RoutingWorkflowState
  isAdmin: boolean
  pipelineBusy: boolean
  onNavigate: (tab: RoutingTab, anchor?: string) => void
}

function guideTitle(workflow: RoutingWorkflowState): string {
  if (workflow.currentStage == null) return 'Обновление завершено'
  if (workflow.currentStage === 3 && workflow.compileRecentlyCompleted) {
    return `Списки собраны — ${STAGE_DEPLOY.toLowerCase()} на узел`
  }
  return 'Текущий шаг обновления списков'
}

function guideHint(workflow: RoutingWorkflowState): string {
  if (workflow.currentStage == null) {
    return `${pluralProviders(workflow.enabledCount)} активно маршрутизируют трафик`
  }
  return workflow.nextAction?.hint ?? 'Следуйте этапам слева направо'
}

export default function RoutingWorkflowGuide({
  workflow,
  isAdmin,
  pipelineBusy,
  onNavigate,
}: RoutingWorkflowGuideProps) {
  const allDone = workflow.currentStage == null

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium">{guideTitle(workflow)}</div>
          <p className="text-xs text-muted-foreground">{guideHint(workflow)}</p>
        </div>
        {workflow.nextAction && (
          <Button
            size="sm"
            disabled={pipelineBusy && isAdmin}
            onClick={() => onNavigate(workflow.nextAction!.tab, workflow.nextAction!.anchor)}
          >
            {workflow.nextAction.label}
            <ArrowRight size={14} className="ml-1.5" />
          </Button>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {workflow.steps.map((step, index) => {
          const isClickable = step.tab !== 'overview' || step.anchor != null
          const showCheck = step.status === 'done' || step.status === 'warning'
          const StepIcon = step.status === 'warning' ? AlertTriangle : Check

          return (
            <button
              key={step.stage}
              type="button"
              disabled={!isClickable}
              onClick={() => isClickable && onNavigate(step.tab, step.anchor)}
              className={cn(
                'rounded-lg border p-3 text-left transition-colors',
                step.status === 'current' && 'border-primary bg-primary/5 ring-1 ring-primary/20',
                step.status === 'done' && 'border-emerald-500/30 bg-emerald-500/5',
                step.status === 'warning' && 'border-amber-500/40 bg-amber-500/10',
                step.status === 'pending' && 'border-dashed opacity-80',
                isClickable && 'hover:bg-muted/40 cursor-pointer',
                !isClickable && 'cursor-default',
              )}
            >
              <div className="flex items-start gap-2">
                <span
                  className={cn(
                    'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold',
                    step.status === 'current' && 'bg-primary text-primary-foreground',
                    step.status === 'done' && 'bg-emerald-600 text-white',
                    step.status === 'warning' && 'bg-amber-500 text-white',
                    step.status === 'pending' && 'bg-muted text-muted-foreground',
                  )}
                >
                  {showCheck ? <StepIcon size={12} /> : step.stage}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={cn(
                        'text-xs font-medium',
                        (step.status === 'current' || step.status === 'warning') && 'text-foreground',
                      )}
                    >
                      {step.label}
                    </span>
                    {index < workflow.steps.length - 1 && (
                      <ArrowRight size={12} className="hidden lg:inline text-muted-foreground/50" />
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground line-clamp-2">
                    {step.summary}
                  </p>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {!allDone && workflow.optionalCompileRemaining && workflow.currentStage === 3 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Этап 2 выполнен. Провайдеры без файла не блокируют {STAGE_DEPLOY.toLowerCase()} — их можно собрать позже.
        </p>
      )}
    </div>
  )
}
