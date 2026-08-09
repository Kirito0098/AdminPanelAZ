import { useCallback, useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  ClipboardList,
  Copy,
  FileCheck,
  Flame,
  Globe,
  Layers,
  Loader2,
  Network,
  Play,
  RefreshCw,
  Server,
  Shield,
  Stethoscope,
  Terminal,
  XCircle,
} from 'lucide-react'
import { ApiError, runSiteDiagnostics } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { SettingsCollapsible, SettingsMetaLine, SettingsToolbar } from '@/components/settings/SettingsChrome'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNotifications } from '@/context/NotificationContext'
import type { SiteDiagnosticsReport, SiteDiagnosticsStatus, SiteDiagnosticsStep } from '@/types'
import { cn } from '@/lib/utils'

const STATUS_META: Record<
  SiteDiagnosticsStatus,
  {
    label: string
    icon: typeof CheckCircle2
    rowClass: string
    badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
    iconClass: string
  }
> = {
  ok: {
    label: 'OK',
    icon: CheckCircle2,
    rowClass: 'border-emerald-500/30 bg-emerald-500/5',
    badgeVariant: 'success',
    iconClass: 'text-emerald-600 dark:text-emerald-400',
  },
  fail: {
    label: 'Ошибка',
    icon: XCircle,
    rowClass: 'border-destructive/40 bg-destructive/5',
    badgeVariant: 'destructive',
    iconClass: 'text-destructive',
  },
  warn: {
    label: 'Внимание',
    icon: AlertTriangle,
    rowClass: 'border-amber-500/40 bg-amber-500/5',
    badgeVariant: 'warning',
    iconClass: 'text-amber-600 dark:text-amber-400',
  },
}

const STEP_ICONS: Record<string, LucideIcon> = {
  systemd: Server,
  files: FileCheck,
  https: Shield,
  port: Network,
  http: Globe,
  nginx: Layers,
  firewall: Flame,
  summary: ClipboardList,
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
    title: 'Доступность панели',
    description:
      'Проверяет ответ панели. За Nginx — через домен по HTTPS; без Nginx — напрямую на localhost',
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

function StepCard({
  step,
  stepNumber,
  expanded,
  onToggle,
  pending,
  isLast,
}: {
  step: SiteDiagnosticsStep | { id: string; title: string; description: string }
  stepNumber: number
  expanded: boolean
  onToggle: () => void
  pending?: boolean
  isLast?: boolean
}) {
  const status = 'status' in step ? step.status : undefined
  const checks = 'checks' in step ? step.checks : []
  const done = status != null
  const meta = status ? STATUS_META[status] : null
  const StatusIcon = meta?.icon ?? Circle
  const StepIcon = STEP_ICONS[step.id] ?? Stethoscope
  const singleCheck = done && checks.length === 1
  const expandable = done && checks.length > 1
  const showChecks = done && checks.length > 0 && (expanded || singleCheck)

  return (
    <div className="relative flex gap-4">
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'relative z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border shadow-sm',
            pending && 'border-border bg-muted/50',
            done && status === 'ok' && 'border-emerald-500/30 bg-emerald-500/10',
            done && status === 'warn' && 'border-amber-500/30 bg-amber-500/10',
            done && status === 'fail' && 'border-destructive/30 bg-destructive/10',
            !done && !pending && 'border-border bg-card',
          )}
        >
          {pending ? (
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          ) : done ? (
            <StatusIcon className={cn('h-5 w-5', meta?.iconClass)} />
          ) : (
            <StepIcon className="h-5 w-5 text-muted-foreground" />
          )}
        </div>
        {!isLast && <div className="mt-2 w-px flex-1 bg-border/80" />}
      </div>

      <div className="min-w-0 flex-1 pb-6">
        <div
          className={cn(
            'overflow-hidden rounded-xl border transition-colors',
            done && meta ? meta.rowClass : 'border-border/80 bg-card/60',
          )}
        >
          <button
            type="button"
            onClick={onToggle}
            disabled={!expandable}
            className={cn(
              'flex w-full items-start gap-3 p-4 text-left',
              expandable && 'hover:bg-muted/20',
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Шаг {stepNumber}
                </span>
                {meta && (
                  <Badge variant={meta.badgeVariant} className="text-[10px]">
                    {meta.label}
                  </Badge>
                )}
                {checks.length > 0 && (
                  <Badge variant="outline" className="text-[10px]">
                    {checks.length} проверок
                  </Badge>
                )}
              </div>
              <p className="mt-1 text-base font-semibold leading-snug">{step.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{step.description}</p>
            </div>
            {expandable && (
              <span className="mt-1 shrink-0 text-muted-foreground">
                {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
              </span>
            )}
          </button>

          {showChecks && (
            <div
              className={cn(
                'space-y-2 border-t bg-muted/10 px-4 pb-4 pt-3',
                singleCheck && 'border-t-0 bg-transparent px-4 pb-4 pt-0',
              )}
            >
              {checks.map((check, index) => {
                const checkMeta = STATUS_META[check.status]
                const CheckIcon = checkMeta.icon
                return (
                  <div
                    key={`${check.title}-${index}`}
                    className={cn('flex items-start gap-3 rounded-lg border p-4 text-sm', checkMeta.rowClass)}
                  >
                    <CheckIcon className={cn('mt-0.5 h-4 w-4 shrink-0', checkMeta.iconClass)} />
                    <div className="min-w-0 flex-1 space-y-2">
                      <p className="font-medium leading-snug text-foreground">{check.title}</p>
                      {check.detail && (
                        <p className="whitespace-pre-wrap text-[15px] leading-7 text-muted-foreground [overflow-wrap:anywhere]">
                          {check.detail}
                        </p>
                      )}
                      {check.hint_ru && (
                        <p className="rounded-md border border-dashed bg-background/60 px-3 py-2.5 text-sm leading-relaxed text-muted-foreground">
                          <span className="font-medium text-foreground">Что можно сделать: </span>
                          {check.hint_ru}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function RunbookTab() {
  const { success, error: notifyError } = useNotifications()
  const [running, setRunning] = useState(false)
  const [report, setReport] = useState<SiteDiagnosticsReport | null>(null)
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [commandsOpen, setCommandsOpen] = useState(true)

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

  const copyCommand = async (cmd: string) => {
    try {
      await navigator.clipboard.writeText(cmd)
      success('Команда скопирована')
    } catch {
      notifyError('Не удалось скопировать команду')
    }
  }

  const steps = report?.steps ?? GUIDED_STEPS

  const heroState = useMemo(() => {
    if (running) return 'running' as const
    if (!report) return 'idle' as const
    if (report.summary.fail > 0) return 'fail' as const
    if (report.summary.warn > 0) return 'warn' as const
    return 'ok' as const
  }, [running, report])

  const heroCopy = {
    idle: {
      title: 'Готово к проверке',
      description: 'Запустите диагностику — панель проверит сервис, файлы, сайт и сеть на этом сервере.',
      badge: null,
    },
    running: {
      title: 'Выполняется диагностика',
      description: 'Подождите несколько секунд — идёт проверка компонентов панели.',
      badge: 'В процессе',
    },
    ok: {
      title: 'Всё работает штатно',
      description: 'Критических проблем не найдено. Панель и окружение настроены корректно.',
      badge: 'Успешно',
    },
    warn: {
      title: 'Есть предупреждения',
      description: 'Серьёзных сбоев нет, но стоит обратить внимание на отмеченные шаги.',
      badge: 'Внимание',
    },
    fail: {
      title: 'Обнаружены проблемы',
      description: 'Один или несколько шагов завершились с ошибкой — раскройте шаги ниже для подсказок.',
      badge: 'Требует внимания',
    },
  }[heroState]

  return (
    <div className="space-y-4">
      <SettingsToolbar
        title="Диагностика запуска"
        meta={
          report ? (
            <SettingsMetaLine
              items={[
                { label: 'успешно', value: report.summary.ok },
                { label: 'предупреждений', value: report.summary.warn },
                { label: 'ошибок', value: report.summary.fail },
                { label: 'сервис', value: report.service_name },
              ]}
            />
          ) : (
            'Проверка сервиса, файлов, сайта и сети на этом сервере'
          )
        }
        actions={
          <>
            {heroCopy.badge && (
              <Badge
                variant={
                  heroState === 'ok'
                    ? 'success'
                    : heroState === 'warn'
                      ? 'warning'
                      : heroState === 'fail'
                        ? 'destructive'
                        : 'secondary'
                }
              >
                {heroCopy.badge}
              </Badge>
            )}
            <Button size="sm" className="gap-2" onClick={() => void run()} disabled={running}>
              {running ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? 'Проверяем...' : report ? 'Запустить снова' : 'Запустить диагностику'}
            </Button>
            {report && (
              <>
                <Button variant="outline" size="sm" onClick={() => setShowJson((v) => !v)} disabled={running}>
                  {showJson ? 'Скрыть JSON' : 'JSON-отчёт'}
                </Button>
                <Button variant="outline" size="sm" className="gap-2" onClick={() => void copyJson()} disabled={running}>
                  <Copy size={14} />
                  Копировать
                </Button>
              </>
            )}
          </>
        }
      />

      <p className="text-sm text-muted-foreground">{heroCopy.description}</p>

      <SettingsAlert variant="info" title="Где выполняется проверка">
        Диагностика запускается на сервере панели. Для VPN-узлов и WARP используйте соответствующие разделы NOC.
      </SettingsAlert>

      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Шаги проверки</CardTitle>
          <CardDescription>
            {report
              ? 'Раскройте шаг с ошибкой или предупреждением — там будут подсказки, что исправить'
              : 'После запуска здесь появятся результаты по каждому этапу'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!report && !running ? (
            <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed bg-muted/10 px-6 py-12 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Stethoscope size={32} />
              </div>
              <div className="max-w-md space-y-1">
                <p className="text-base font-semibold">Диагностика ещё не запускалась</p>
                <p className="text-sm text-muted-foreground">
                  Нажмите «Запустить диагностику» — проверим systemd, файлы, HTTPS, порт, Nginx и firewall.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-0">
              {steps.map((step, index) => (
                <StepCard
                  key={step.id}
                  step={step}
                  stepNumber={index + 1}
                  expanded={expandedStep === step.id}
                  onToggle={() => setExpandedStep((current) => (current === step.id ? null : step.id))}
                  pending={running}
                  isLast={index === steps.length - 1}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {report && !running && report.summary.fail > 0 && report.recommended_commands.length > 0 && (
        <SettingsCollapsible
          open={commandsOpen}
          onOpenChange={setCommandsOpen}
          title="Рекомендуемые команды"
          description="Выполните на сервере панели от имени администратора, если подсказки выше указывают на сбой"
          icon={<Terminal size={16} />}
        >
          {report.recommended_commands.map((cmd) => (
            <div
              key={cmd}
              className="flex items-start gap-2 rounded-lg border bg-card/60 p-3 font-mono text-xs sm:text-sm"
            >
              <code className="min-w-0 flex-1 whitespace-pre-wrap break-all leading-relaxed text-foreground">
                {cmd}
              </code>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0"
                onClick={() => void copyCommand(cmd)}
                aria-label="Копировать команду"
              >
                <Copy size={16} />
              </Button>
            </div>
          ))}
        </SettingsCollapsible>
      )}

      {showJson && report && (
        <Card className="overflow-hidden shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">JSON-отчёт</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto rounded-xl border bg-muted/30 p-4 font-mono text-xs leading-relaxed">
              {JSON.stringify(report, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
