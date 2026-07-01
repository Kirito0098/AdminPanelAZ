import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { BellOff, BellRing, Plus, Trash2 } from 'lucide-react'
import {
  ApiError,
  createAlertRule,
  deleteAlertRule,
  getAlertMetrics,
  getAlertRules,
  getNodes,
  updateAlertRule,
} from '@/api/client'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { LABEL_COOLDOWN_MIN } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import type { AlertMetricInfo, AlertRule, Node } from '@/types'

const OPERATORS = [
  { id: 'gt', label: '>' },
  { id: 'gte', label: '≥' },
  { id: 'lt', label: '<' },
  { id: 'lte', label: '≤' },
  { id: 'eq', label: '=' },
] as const

const COOLDOWN_PRESETS = [15, 30, 60, 120] as const

const controlBtnClass = (active: boolean) =>
  cn(
    'inline-flex h-10 min-w-10 items-center justify-center rounded-lg border px-3 text-sm font-medium transition-all',
    active
      ? 'border-primary bg-primary/10 text-primary ring-1 ring-primary'
      : 'hover:border-muted-foreground/30 hover:bg-muted/50',
  )

function FormField({
  label,
  htmlFor,
  children,
  className,
}: {
  label: string
  htmlFor?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-2', className)}>
      <Label htmlFor={htmlFor} className="text-sm">
        {label}
      </Label>
      {children}
    </div>
  )
}
function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="md:col-span-2">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function ListRow({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card/50 p-3 transition-colors hover:bg-muted/30 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">{children}</div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </div>
  )
}

function PanelEmpty({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof BellRing
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-muted-foreground/20 bg-muted/10 px-4 py-10 text-center">
      <Icon className="mb-2 h-8 w-8 text-muted-foreground/70" />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-md text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

export default function AlertRulesCard() {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [rules, setRules] = useState<AlertRule[]>([])
  const [metrics, setMetrics] = useState<AlertMetricInfo[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [name, setName] = useState('')
  const [metric, setMetric] = useState('ovpn_online_total')
  const [operator, setOperator] = useState('gt')
  const [threshold, setThreshold] = useState(50)
  const [nodeId, setNodeId] = useState<string>('')
  const [cooldownMinutes, setCooldownMinutes] = useState(30)

  const selectedMetric = useMemo(
    () => metrics.find((item) => item.id === metric),
    [metrics, metric],
  )

  const enabledCount = useMemo(() => rules.filter((r) => r.enabled).length, [rules])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [rulesData, metricsData, nodesData] = await Promise.all([
        getAlertRules(),
        getAlertMetrics(),
        getNodes(),
      ])
      setRules(rulesData)
      setMetrics(metricsData)
      setNodes(nodesData)
      if (metricsData.length > 0 && !metricsData.some((item) => item.id === metric)) {
        setMetric(metricsData[0].id)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить правила уведомлений')
    } finally {
      setLoading(false)
    }
  }, [metric, notifyError])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const metricLabel = (id: string) => metrics.find((item) => item.id === id)?.label || id
  const operatorLabel = (id: string) => OPERATORS.find((item) => item.id === id)?.label || id
  const nodeLabel = (id: number | null) => {
    if (!id) return null
    return nodes.find((n) => n.id === id)?.name || `узел #${id}`
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      notifyError('Укажите название правила')
      return
    }
    if (selectedMetric?.requires_node && !nodeId) {
      notifyError('Выберите узел для этой метрики')
      return
    }
    setSaving(true)
    try {
      const created = await createAlertRule({
        name: name.trim(),
        metric,
        operator,
        threshold,
        cooldown_minutes: cooldownMinutes,
        node_id: nodeId ? Number(nodeId) : null,
      })
      setRules((prev) => [...prev, created])
      setName('')
      success('Правило уведомления создано')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания правила')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (rule: AlertRule, enabled: boolean) => {
    try {
      const updated = await updateAlertRule(rule.id, { enabled })
      setRules((prev) => prev.map((item) => (item.id === rule.id ? updated : item)))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления правила')
    }
  }

  const handleDelete = (rule: AlertRule) => {
    confirm({
      title: 'Удалить правило?',
      description: <>Правило «{rule.name}» будет удалено без возможности восстановления.</>,
      confirmLabel: 'Удалить',
      destructive: true,
      onConfirm: async () => {
        try {
          await deleteAlertRule(rule.id)
          setRules((prev) => prev.filter((item) => item.id !== rule.id))
          success('Правило удалено')
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления правила')
        }
      },
    })
  }

  if (loading) {
    return <Spinner label="Загрузка правил уведомлений..." className="py-12 md:col-span-2" />
  }

  return (
    <div className="space-y-4 md:col-span-2">
      <ConfirmDialogHost dialogProps={dialogProps} />

      <SectionHeading
        title="Свои правила"
        description="Дополнительные условия поверх порогов CPU и RAM — например, число клиентов или недоступность узла"
      />

      <Card className="overflow-hidden shadow-sm">
        <div className="h-1 bg-gradient-to-r from-violet-500/70 to-violet-500/15" />
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <BellRing size={18} />
              Правила уведомлений
            </CardTitle>
            <CardDescription className="mt-1.5">
              При срабатывании сообщение уходит в Telegram — как и при высокой нагрузке
            </CardDescription>
          </div>
          <Badge variant={enabledCount > 0 ? 'default' : 'secondary'} className="shrink-0">
            {enabledCount} / {rules.length} вкл.
          </Badge>
        </CardHeader>
        <CardContent className="space-y-5">
          <InlineProgressBar active={saving} label="Создание правила..." />

          <form onSubmit={handleCreate} className="space-y-4 rounded-xl border bg-muted/15 p-4">
            <p className="text-sm font-medium">Новое правило</p>

            <FormField label="Название" htmlFor="alert-name">
              <Input
                id="alert-name"
                className="h-10"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Например: много клиентов OpenVPN"
              />
            </FormField>

            <div
              className={cn(
                'grid gap-4',
                selectedMetric?.requires_node ? 'md:grid-cols-2' : 'grid-cols-1',
              )}
            >
              <FormField label="Что отслеживать">
                <Select value={metric} onValueChange={setMetric}>
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder="Выберите метрику" />
                  </SelectTrigger>
                  <SelectContent>
                    {metrics.map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormField>

              {selectedMetric?.requires_node && (
                <FormField label="Сервер VPN">
                  <Select value={nodeId || undefined} onValueChange={setNodeId}>
                    <SelectTrigger className="h-10">
                      <SelectValue placeholder="Выберите узел" />
                    </SelectTrigger>
                    <SelectContent>
                      {nodes.map((node) => (
                        <SelectItem key={node.id} value={String(node.id)}>
                          {node.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormField>
              )}
            </div>

            <FormField label="Условие срабатывания">
              <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-background/60 p-3">
                <div className="flex flex-wrap gap-2">
                  {OPERATORS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setOperator(item.id)}
                      className={controlBtnClass(operator === item.id)}
                      aria-label={`Сравнение: ${item.label}`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2 border-border sm:border-l sm:pl-3">
                  <Label htmlFor="alert-threshold" className="shrink-0 text-xs text-muted-foreground">
                    порог
                  </Label>
                  <Input
                    id="alert-threshold"
                    type="number"
                    className="h-10 w-24"
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                {metricLabel(metric)} {operatorLabel(operator)} {threshold}
              </p>
            </FormField>

            <FormField label={LABEL_COOLDOWN_MIN}>
              <div className="flex flex-wrap items-center gap-2">
                {COOLDOWN_PRESETS.map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setCooldownMinutes(value)}
                    className={controlBtnClass(cooldownMinutes === value)}
                  >
                    {value} мин
                  </button>
                ))}
                <div className="flex h-10 items-center gap-2 rounded-lg border bg-background px-3">
                  <Input
                    id="alert-cooldown"
                    type="number"
                    min={1}
                    max={1440}
                    className="h-8 w-14 border-0 bg-transparent p-0 shadow-none focus-visible:ring-0"
                    value={cooldownMinutes}
                    onChange={(e) => setCooldownMinutes(Number(e.target.value))}
                  />
                  <span className="text-xs text-muted-foreground">мин</span>
                </div>
              </div>
            </FormField>

            <SettingsAlert variant="info" title="Примеры">
              «Клиентов OpenVPN больше 50» · «Сервер не отвечает дольше 5 минут»
            </SettingsAlert>

            <div className="flex justify-end">
              <Button type="submit" disabled={saving} className="gap-1.5">
                <Plus size={16} />
                {saving ? 'Создание...' : 'Добавить правило'}
              </Button>
            </div>
          </form>

          {rules.length === 0 ? (
            <PanelEmpty
              icon={BellOff}
              title="Пока нет своих правил"
              description="Работают только пороги CPU и RAM выше. Добавьте правило, если нужны оповещения по клиентам или доступности узлов."
            />
          ) : (
            <ul className="space-y-2">
              {rules.map((rule) => (
                <li key={rule.id}>
                  <ListRow
                    action={
                      <>
                        <div className="flex items-center gap-2 rounded-lg border bg-card/80 px-3 py-1.5">
                          <Switch
                            id={`rule-${rule.id}`}
                            checked={rule.enabled}
                            onCheckedChange={(checked) => void handleToggle(rule, checked)}
                          />
                          <Label htmlFor={`rule-${rule.id}`} className="cursor-pointer text-xs">
                            {rule.enabled ? 'Вкл.' : 'Выкл.'}
                          </Label>
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="border-destructive/30 text-destructive hover:bg-destructive/10"
                          onClick={() => handleDelete(rule)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </>
                    }
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{rule.name}</span>
                      <Badge variant={rule.enabled ? 'default' : 'outline'} className="text-[10px]">
                        {rule.enabled ? 'Активно' : 'Пауза'}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {metricLabel(rule.metric)} {operatorLabel(rule.operator)} {rule.threshold}
                      {rule.node_id ? ` · ${nodeLabel(rule.node_id)}` : ''}
                      {rule.cooldown_minutes ? ` · пауза ${rule.cooldown_minutes} мин` : ''}
                    </p>
                    {rule.last_triggered_at && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Последнее срабатывание: {formatDateTime(rule.last_triggered_at)}
                      </p>
                    )}
                  </ListRow>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
