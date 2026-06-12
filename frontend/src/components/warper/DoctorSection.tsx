import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Info,
  RefreshCw,
  Stethoscope,
  XCircle,
} from 'lucide-react'
import { getWarperDoctor } from '@/api/client'
import StatusPanel from '@/components/noc/StatusPanel'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useNotifications } from '@/context/NotificationContext'
import type { Node, WarperDoctorItem, WarperHealthResponse } from '@/types'
import { formatNodeLabel } from './utils'

interface DoctorSectionProps {
  health: WarperHealthResponse | null
  activeNode: Node | null
  embedded?: boolean
  hideTitle?: boolean
}

type DoctorStatus = WarperDoctorItem['status']

const STATUS_META: Record<
  DoctorStatus,
  { label: string; icon: typeof CheckCircle2; rowClass: string; badgeVariant: 'default' | 'secondary' | 'destructive' | 'outline' }
> = {
  ok: {
    label: 'OK',
    icon: CheckCircle2,
    rowClass: 'border-emerald-500/30 bg-emerald-500/5',
    badgeVariant: 'default',
  },
  error: {
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
  info: {
    label: 'Инфо',
    icon: Info,
    rowClass: 'border-border bg-muted/20',
    badgeVariant: 'secondary',
  },
}

function normalizeStatus(value: unknown): DoctorStatus {
  const raw = String(value ?? 'info').toLowerCase()
  if (raw === 'ok' || raw === 'pass' || raw === 'success' || raw === 'true' || raw === '1') return 'ok'
  if (raw === 'error' || raw === 'fail' || raw === 'failed' || raw === 'false' || raw === '0') return 'error'
  if (raw === 'warn' || raw === 'warning') return 'warn'
  return 'info'
}

function itemText(item: WarperDoctorItem): string {
  return String(item.text ?? item.check ?? item.name ?? item.message ?? '—')
}

export default function DoctorSection({ health, activeNode, embedded = false, hideTitle = false }: DoctorSectionProps) {
  const { error: notifyError } = useNotifications()
  const [items, setItems] = useState<WarperDoctorItem[]>([])
  const [passed, setPassed] = useState<boolean | null>(null)
  const [summary, setSummary] = useState<Record<string, number> | null>(null)
  const [running, setRunning] = useState(false)
  const [hasRun, setHasRun] = useState(false)

  const runDoctor = useCallback(async () => {
    setRunning(true)
    try {
      const data = await getWarperDoctor()
      setItems(data.items ?? [])
      setPassed(data.passed ?? null)
      setSummary(data.summary ?? null)
      setHasRun(true)
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось выполнить диагностику')
    } finally {
      setRunning(false)
    }
  }, [notifyError])

  useEffect(() => {
    setItems([])
    setPassed(null)
    setSummary(null)
    setHasRun(false)
  }, [activeNode?.id])

  const counts = useMemo(() => {
    if (summary) {
      return {
        ok: summary.ok ?? 0,
        warn: summary.warn ?? 0,
        error: summary.error ?? 0,
        info: summary.info ?? 0,
      }
    }
    const acc = { ok: 0, warn: 0, error: 0, info: 0 }
    for (const item of items) {
      const key = normalizeStatus(item.status)
      acc[key] += 1
    }
    return acc
  }, [items, summary])

  const disabled = !health?.installed

  const body = (
    <>
      {!embedded && (
        <p className="mb-4 text-sm text-muted-foreground">
          Проверка sing-box, kresd и конфигурации на узле{' '}
          <strong>{formatNodeLabel(health, activeNode)}</strong>.
        </p>
      )}

      <Button type="button" size="sm" onClick={() => void runDoctor()} disabled={disabled || running}>
        {running ? (
          <>
            <RefreshCw className="mr-1.5 h-4 w-4 animate-spin" />
            Выполняется...
          </>
        ) : (
          <>
            <Stethoscope className="mr-1.5 h-4 w-4" />
            Запустить диагностику
          </>
        )}
      </Button>

      {running && (
        <div className="mt-4 flex justify-center py-6">
          <Spinner label="Проверяем компоненты AZ-WARP..." />
        </div>
      )}

      {hasRun && !running && (
        <div className="mt-4 space-y-4">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Нет данных диагностики.</p>
          ) : (
            <>
              <div
                className={`rounded-lg border p-4 ${
                  passed
                    ? 'border-emerald-500/40 bg-emerald-500/10'
                    : 'border-destructive/40 bg-destructive/10'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  {passed ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                  ) : (
                    <XCircle className="h-5 w-5 text-destructive" />
                  )}
                  <span className="font-medium">
                    {passed ? 'Все проверки пройдены' : 'Обнаружены проблемы'}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {counts.ok > 0 && <Badge variant="default">{counts.ok} OK</Badge>}
                  {counts.warn > 0 && <Badge variant="outline">{counts.warn} внимание</Badge>}
                  {counts.error > 0 && <Badge variant="destructive">{counts.error} ошибок</Badge>}
                  {counts.info > 0 && <Badge variant="secondary">{counts.info} инфо</Badge>}
                </div>
              </div>

              <div className="space-y-2">
                {items.map((item, index) => {
                  const status = normalizeStatus(item.status)
                  const meta = STATUS_META[status]
                  const Icon = meta.icon
                  const text = itemText(item)
                  return (
                    <div
                      key={`${text}-${index}`}
                      className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${meta.rowClass}`}
                    >
                      <Icon
                        className={`mt-0.5 h-4 w-4 shrink-0 ${
                          status === 'ok'
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : status === 'error'
                              ? 'text-destructive'
                              : status === 'warn'
                                ? 'text-amber-600 dark:text-amber-400'
                                : 'text-muted-foreground'
                        }`}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="leading-snug">{text}</p>
                      </div>
                      <Badge variant={meta.badgeVariant} className="shrink-0">
                        {meta.label}
                      </Badge>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>
      )}

      {!hasRun && !running && !disabled && (
        <div className={`flex items-center gap-2 text-sm text-muted-foreground ${embedded ? 'mt-3' : 'mt-6'}`}>
          <Circle className="h-4 w-4" />
          Нажмите «Запустить диагностику», чтобы увидеть результат проверок.
        </div>
      )}
    </>
  )

  if (embedded) {
    return (
      <div>
        {!hideTitle && <h3 className="mb-3 text-sm font-semibold">Диагностика</h3>}
        {body}
      </div>
    )
  }

  return (
    <StatusPanel title="Диагностика AZ-WARP" icon={Stethoscope}>
      {body}
    </StatusPanel>
  )
}
