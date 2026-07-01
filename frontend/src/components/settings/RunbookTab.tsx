import { useCallback, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Copy,
  Play,
  RefreshCw,
  Stethoscope,
  XCircle,
} from 'lucide-react'
import { ApiError, runSiteDiagnostics } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import type { SiteDiagnosticsReport, SiteDiagnosticsStatus, SiteDiagnosticsStep } from '@/types'
import { cn } from '@/lib/utils'

const STATUS_META: Record<
  SiteDiagnosticsStatus,
  { label: string; icon: typeof CheckCircle2; rowClass: string; badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  ok: {
    label: 'OK',
    icon: CheckCircle2,
    rowClass: 'border-emerald-500/30 bg-emerald-500/5',
    badgeVariant: 'default',
  },
  fail: {
    label: 'Ошибка',
    icon: XCircle,
    rowClass: 'border-destructive/40 bg-destructive/5',
    badgeVariant: 'destructive',
  },
  warn: {
    label: 'Внимание',
    icon: AlertTriangle,
    rowClass: 'border-amber-500/40 bg-amber-500/5',
    badgeVariant: 'outline',
  },
}

function StepCard({
  step,
  stepNumber,
  expanded,
  onToggle,
  pending,
}: {
  step: SiteDiagnosticsStep | { id: string; title: string; description: string }
  stepNumber: number
  expanded: boolean
  onToggle: () => void
  pending?: boolean
}) {
  const status = 'status' in step ? step.status : undefined
  const checks = 'checks' in step ? step.checks : []
  const done = status != null && status !== undefined
  const meta = status ? STATUS_META[status] : null
  const Icon = meta?.icon ?? Circle

  return (
    <div
      className={cn(
        'rounded-lg border transition-colors',
        done && meta ? meta.rowClass : 'bg-muted/20',
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={!done || checks.length === 0}
        className={cn(
          'flex w-full items-start gap-4 p-4 text-left',
          done && checks.length > 0 && 'hover:bg-muted/30',
        )}
      >
        <div className="flex shrink-0 flex-col items-center gap-1 pt-0.5">
          {pending ? (
            <Circle className="h-6 w-6 animate-pulse text-muted-foreground/50" />
          ) : (
            <Icon
              className={cn(
                'h-6 w-6',
                status === 'ok' && 'text-emerald-500',
                status === 'fail' && 'text-destructive',
                status === 'warn' && 'text-amber-500',
                !status && 'text-muted-foreground/50',
              )}
            />
          )}
          <span className="text-[10px] font-medium uppercase text-muted-foreground">Шаг {stepNumber}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium leading-snug">{step.title}</p>
            {meta && (
              <Badge variant={meta.badgeVariant} className="shrink-0">
                {meta.label}
              </Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
        </div>
        {done && checks.length > 0 && (
          <span className="mt-1 shrink-0 text-muted-foreground">
            {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          </span>
        )}
      </button>

      {expanded && checks.length > 0 && (
        <div className="space-y-2 border-t px-4 pb-4 pt-2">
          {checks.map((check, index) => {
            const checkMeta = STATUS_META[check.status]
            const CheckIcon = checkMeta.icon
            return (
              <div
                key={`${check.title}-${index}`}
                className={cn('flex items-start gap-3 rounded-md border p-3 text-sm', checkMeta.rowClass)}
              >
                <CheckIcon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="font-medium leading-snug">{check.title}</p>
                  {check.detail && <p className="text-muted-foreground">{check.detail}</p>}
                  {check.hint_ru && (
                    <p className="text-xs text-muted-foreground">
                      Подсказка: <span className="text-foreground">{check.hint_ru}</span>
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

const GUIDED_STEPS: Array<{ id: string; title: string; description: string }> = [
  {
    id: 'systemd',
    title: 'Автозапуск панели',
    description: 'Запускается ли панель при включении сервера',
  },
  {
    id: 'files',
    title: 'Нужные файлы',
    description: 'Настройки, база данных и скрипты на месте',
  },
  {
    id: 'https',
    title: 'HTTPS и домен',
    description: 'Защищённое соединение и адрес сайта',
  },
  {
    id: 'port',
    title: 'Порт приложения',
    description: 'Отвечает ли внутренний сервер панели',
  },
  {
    id: 'http',
    title: 'Проверка ответа',
    description: 'Открывается ли служебная страница здоровья',
  },
  {
    id: 'nginx',
    title: 'Обратный прокси',
    description: 'Правильно ли Nginx перенаправляет запросы',
  },
  {
    id: 'firewall',
    title: 'Защита сети',
    description: 'Доступны ли средства блокировки на сервере',
  },
  {
    id: 'summary',
    title: 'Итог',
    description: 'Сводка и что делать дальше',
  },
]

export default function RunbookTab() {
  const { success, error: notifyError } = useNotifications()
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState<SiteDiagnosticsReport | null>(null)
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)

  const run = useCallback(async () => {
    setRunning(true)
    setExpandedStep(null)
    try {
      const data = await runSiteDiagnostics()
      setReport(data)
      const firstProblem = data.steps.find((step) => step.status === 'fail' || step.status === 'warn')
      setExpandedStep(firstProblem?.id ?? data.steps[0]?.id ?? null)
      if (data.success) {
        success('Диагностика завершена без критических ошибок')
      } else {
        notifyError('Обнаружены проблемы запуска — см. шаги ниже')
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось выполнить диагностику')
    } finally {
      setRunning(false)
    }
  }, [notifyError, success])

  const copyJson = async () => {
    if (!report) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2))
      success('JSON скопирован в буфер обмена')
    } catch {
      notifyError('Не удалось скопировать JSON')
    }
  }

  const steps = report?.steps ?? GUIDED_STEPS

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Stethoscope size={18} />
          Проверка работы панели
        </CardTitle>
        <CardDescription>
          Автоматически проверит сервис, файлы, сайт и сеть — подскажет, если что-то настроено неправильно
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <SettingsAlert variant="info" title="Проверка сервера панели">
          Диагностика выполняется на компьютере, где установлена панель. Для VPN-узлов используйте разделы NOC и WARP.
        </SettingsAlert>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void run()} disabled={running}>
            {running ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
            {running ? 'Выполняется...' : 'Запустить диагностику'}
          </Button>
          {report && (
            <>
              <Button variant="outline" onClick={() => setShowJson((v) => !v)}>
                {showJson ? 'Скрыть JSON' : 'Показать JSON'}
              </Button>
              <Button variant="outline" onClick={() => void copyJson()}>
                <Copy size={16} />
                Копировать JSON
              </Button>
            </>
          )}
        </div>

        {running && <Spinner label="Проверяем компоненты панели..." className="py-8" />}

        {!running && (
          <div className="space-y-3">
            {steps.map((step, index) => (
              <StepCard
                key={step.id}
                step={step}
                stepNumber={index + 1}
                expanded={expandedStep === step.id}
                onToggle={() => setExpandedStep((current) => (current === step.id ? null : step.id))}
                pending={running}
              />
            ))}
          </div>
        )}

        {report && !running && report.recommended_commands.length > 0 && (
          <div className="rounded-lg border bg-muted/20 p-4">
            <p className="mb-2 text-sm font-medium">Рекомендуемые команды</p>
            <ul className="space-y-1 font-mono text-xs text-muted-foreground">
              {report.recommended_commands.map((cmd) => (
                <li key={cmd} className="rounded bg-muted/50 px-2 py-1">
                  {cmd}
                </li>
              ))}
            </ul>
          </div>
        )}

        {showJson && report && (
          <pre className="max-h-96 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs">
            {JSON.stringify(report, null, 2)}
          </pre>
        )}

        {!report && !running && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Circle size={16} />
            Нажмите «Запустить диагностику», чтобы пройти guided steps и получить JSON-отчёт.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
