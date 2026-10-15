import { useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, Plus, Save, X } from 'lucide-react'
import { ApiError, updateTelegramRelay } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { ConfirmDialogHost } from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useNotifications } from '@/context/NotificationContext'
import { useConfirmDialog } from '@/hooks/useConfirmDialog'
import { formatDateTime } from '@/lib/datetime'
import type { TelegramRelayCheck, TelegramSettings } from '@/types'

interface TelegramRelayCardProps {
  settings: TelegramSettings
  onSaved: (updated: TelegramSettings) => void
}

function relayStatus(settings: TelegramSettings): string {
  if (!settings.interactive_enabled) return 'Опрос начнётся, когда включите ответы на команды'
  if (settings.relay_last_ok_at) {
    const via = settings.relay_last_node ? ` через ${settings.relay_last_node}` : ''
    return `Последний опрос${via}: ${formatDateTime(settings.relay_last_ok_at)}`
  }
  return 'Ждём первый опрос — обычно до минуты'
}

export default function TelegramRelayCard({ settings, onSaved }: TelegramRelayCardProps) {
  const { success, error: notifyError } = useNotifications()
  const { confirm, dialogProps } = useConfirmDialog()
  const savedKey = settings.relay_node_ids.join(',')
  const [order, setOrder] = useState<number[]>(settings.relay_node_ids)
  const [checks, setChecks] = useState<TelegramRelayCheck[]>([])
  const [saving, setSaving] = useState(false)
  const [turnedOn, setTurnedOn] = useState(false)

  useEffect(() => setOrder(savedKey ? savedKey.split(',').map(Number) : []), [savedKey])

  const nodeById = new Map(settings.relay_nodes.map((node) => [node.id, node]))
  const checkById = new Map(checks.map((check) => [check.id, check]))
  const addable = settings.relay_nodes.filter((node) => !node.unavailable_reason && !order.includes(node.id))
  const changed = order.join(',') !== savedKey
  const enabled = turnedOn || settings.relay_node_ids.length > 0

  const move = (index: number, delta: number) => {
    const next = [...order]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    setOrder(next)
  }

  const save = async (nodeIds: number[]) => {
    setSaving(true)
    try {
      const updated = await updateTelegramRelay(nodeIds)
      setChecks(updated.relay_check)
      onSaved(updated)
      success(nodeIds.length ? 'Telegram подключён через узлы' : 'Бот снова работает напрямую — подключите его к панели')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  const toggle = (checked: boolean) => {
    if (checked || !settings.relay_node_ids.length) {
      setTurnedOn(checked)
      setOrder(settings.relay_node_ids)
      return
    }
    confirm({
      title: 'Выключить связь через узел?',
      description: 'Бот вернётся на прямую связь с Telegram, список узлов очистится.',
      alert: {
        variant: 'warning',
        title: 'Если панель в РФ, бот может замолчать',
        children: 'После выключения подключите бота к панели на вкладке «Команды бота».',
      },
      confirmLabel: 'Выключить',
      destructive: true,
      onConfirm: async () => {
        setTurnedOn(false)
        await save([])
      },
    })
  }

  return (
    <div className="space-y-4">
      <ConfirmDialogHost dialogProps={dialogProps} />
      <div className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <Label htmlFor="telegramRelayEnabled" className="cursor-pointer font-medium">
            Связь с Telegram через узлы
          </Label>
          <p className="text-xs text-muted-foreground">
            {enabled
              ? 'Запрос идёт через первый узел списка, при отказе — через следующий. Панель сама забирает сообщения, входящий доступ из интернета не нужен.'
              : 'Выключено — бот работает с Telegram напрямую.'}
          </p>
        </div>
        <Switch id="telegramRelayEnabled" checked={enabled} disabled={saving} onCheckedChange={toggle} />
      </div>

      {enabled ? (
        <>
          {order.length === 0 ? (
            <p className="text-sm text-muted-foreground">Добавьте хотя бы один узел и сохраните.</p>
          ) : (
            <ol className="space-y-1.5">
              {order.map((nodeId, index) => {
                const node = nodeById.get(nodeId)
                const check = checkById.get(nodeId)
                return (
                  <li key={nodeId} className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2">
                    <span className="w-5 text-sm tabular-nums text-muted-foreground">{index + 1}.</span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{node?.name ?? `Узел #${nodeId} (удалён)`}</span>
                    {check ? (
                      <Badge variant={check.ok ? 'success' : 'secondary'}>{check.ok ? 'Работает' : 'Не ответил'}</Badge>
                    ) : null}
                    <div className="flex gap-1">
                      <Button type="button" size="icon" variant="ghost" aria-label="Выше" disabled={saving || index === 0} onClick={() => move(index, -1)}>
                        <ArrowUp size={15} />
                      </Button>
                      <Button type="button" size="icon" variant="ghost" aria-label="Ниже" disabled={saving || index === order.length - 1} onClick={() => move(index, 1)}>
                        <ArrowDown size={15} />
                      </Button>
                      <Button type="button" size="icon" variant="ghost" aria-label="Убрать" disabled={saving} onClick={() => setOrder(order.filter((id) => id !== nodeId))}>
                        <X size={15} />
                      </Button>
                    </div>
                    {node?.unavailable_reason ? (
                      <p className="basis-full text-xs text-destructive">{node.unavailable_reason}</p>
                    ) : null}
                    {check && !check.ok ? <p className="basis-full text-xs text-muted-foreground">{check.error}</p> : null}
                  </li>
                )
              })}
            </ol>
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            {addable.length > 0 ? (
              <Select value="" onValueChange={(value) => setOrder([...order, Number(value)])} disabled={saving}>
                <SelectTrigger className="sm:max-w-xs" aria-label="Добавить узел">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <Plus size={15} />
                    <SelectValue placeholder="Добавить узел" />
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {addable.map((node) => (
                    <SelectItem key={node.id} value={String(node.id)}>
                      {node.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            <Button type="button" size="sm" variant="outline" onClick={() => void save(order)} disabled={saving || !changed || !order.length}>
              <Save size={15} />
              {saving ? 'Проверяем узлы...' : 'Сохранить'}
            </Button>
          </div>

          {settings.relay_nodes.every((node) => node.unavailable_reason) ? (
            <p className="text-xs text-muted-foreground">
              Подходящих узлов нет: нужен удалённый VPN-узел с mTLS или SSH-транспортом и агентом 1.13.0 или новее.
            </p>
          ) : null}
        </>
      ) : null}

      {settings.relay_node_ids.length > 0 ? (
        settings.relay_last_error ? (
          <SettingsAlert variant="danger" title="Узлы не достучались до Telegram">
            {settings.relay_last_error}
          </SettingsAlert>
        ) : (
          <p className="text-xs text-muted-foreground">{relayStatus(settings)}</p>
        )
      ) : null}
    </div>
  )
}
