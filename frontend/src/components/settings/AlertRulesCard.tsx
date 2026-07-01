import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { BellRing, Plus, Trash2 } from 'lucide-react'
import {
  ApiError,
  createAlertRule,
  deleteAlertRule,
  getAlertMetrics,
  getAlertRules,
  getNodes,
  updateAlertRule,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotifications } from '@/context/NotificationContext'
import { formatDateTime } from '@/lib/datetime'
import { LABEL_COOLDOWN_MIN } from '@/lib/uiLabels'
import type { AlertMetricInfo, AlertRule, Node } from '@/types'

const OPERATORS = [
  { id: 'gt', label: '>' },
  { id: 'gte', label: '≥' },
  { id: 'lt', label: '<' },
  { id: 'lte', label: '≤' },
  { id: 'eq', label: '=' },
]

export default function AlertRulesCard() {
  const { success, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [rules, setRules] = useState<AlertRule[]>([])
  const [metrics, setMetrics] = useState<AlertMetricInfo[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [name, setName] = useState('')
  const [metric, setMetric] = useState('ovpn_online_total')
  const [operator, setOperator] = useState('gt')
  const [threshold, setThreshold] = useState(50)
  const [nodeId, setNodeId] = useState<number | ''>('')
  const [cooldownMinutes, setCooldownMinutes] = useState(30)

  const selectedMetric = useMemo(
    () => metrics.find((item) => item.id === metric),
    [metrics, metric],
  )

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

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      notifyError('Укажите название правила')
      return
    }
    if (selectedMetric?.requires_node && nodeId === '') {
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
        node_id: nodeId === '' ? null : nodeId,
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

  const handleToggle = async (rule: AlertRule) => {
    try {
      const updated = await updateAlertRule(rule.id, { enabled: !rule.enabled })
      setRules((prev) => prev.map((item) => (item.id === rule.id ? updated : item)))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка обновления правила')
    }
  }

  const handleDelete = async (ruleId: number) => {
    try {
      await deleteAlertRule(ruleId)
      setRules((prev) => prev.filter((item) => item.id !== ruleId))
      success('Правило удалено')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления правила')
    }
  }

  if (loading) {
    return <Spinner label="Загрузка правил уведомлений..." className="py-8" />
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BellRing size={18} />
          Свои правила уведомлений
        </CardTitle>
        <CardDescription>
          Дополнительные условия: например, слишком много клиентов в сети или сервер долго недоступен
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <form onSubmit={handleCreate} className="space-y-4 rounded-lg border p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="alert-name">Название</Label>
              <Input
                id="alert-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Например: много клиентов OpenVPN"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="alert-metric">Что отслеживать</Label>
              <select
                id="alert-metric"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                {metrics.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="alert-operator">Сравнение</Label>
              <select
                id="alert-operator"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={operator}
                onChange={(e) => setOperator(e.target.value)}
              >
                {OPERATORS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="alert-threshold">Пороговое значение</Label>
              <Input
                id="alert-threshold"
                type="number"
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="alert-cooldown">{LABEL_COOLDOWN_MIN}</Label>
              <Input
                id="alert-cooldown"
                type="number"
                min={1}
                max={1440}
                value={cooldownMinutes}
                onChange={(e) => setCooldownMinutes(Number(e.target.value))}
              />
            </div>
            {selectedMetric?.requires_node && (
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="alert-node">Сервер VPN</Label>
                <select
                  id="alert-node"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  value={nodeId}
                  onChange={(e) => setNodeId(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">Выберите узел</option>
                  {nodes.map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <SettingsAlert variant="info" title="Примеры">
            «Клиентов OpenVPN больше 50» · «Сервер не отвечает дольше 5 минут»
          </SettingsAlert>
          <Button type="submit" disabled={saving}>
            <Plus size={16} />
            {saving ? 'Сохранение...' : 'Добавить правило'}
          </Button>
        </form>

        <div className="space-y-3">
          {rules.length === 0 ? (
            <p className="text-sm text-muted-foreground">Пока нет своих правил — используются только пороги нагрузки выше.</p>
          ) : (
            rules.map((rule) => (
              <div
                key={rule.id}
                className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{rule.name}</span>
                    <Badge variant={rule.enabled ? 'default' : 'secondary'}>
                      {rule.enabled ? 'включено' : 'выключено'}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {metrics.find((item) => item.id === rule.metric)?.label || rule.metric}{' '}
                    {OPERATORS.find((item) => item.id === rule.operator)?.label || rule.operator}{' '}
                    {rule.threshold}
                    {rule.node_id ? ` · сервер #${rule.node_id}` : ''}
                    {rule.cooldown_minutes ? ` · пауза ${rule.cooldown_minutes} мин` : ''}
                  </p>
                  {rule.last_triggered_at && (
                    <p className="text-xs text-muted-foreground">
                      Последнее срабатывание: {formatDateTime(rule.last_triggered_at)}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" onClick={() => void handleToggle(rule)}>
                    {rule.enabled ? 'Выключить' : 'Включить'}
                  </Button>
                  <Button type="button" variant="destructive" onClick={() => void handleDelete(rule.id)}>
                    <Trash2 size={16} />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}
