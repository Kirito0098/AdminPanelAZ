import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, getUsers } from '@/api/client'
import { getNodes } from '@/api/nodes'
import {
  approveRequest,
  getRequestReceipt,
  listPresets,
  listRequests,
  rejectRequest,
} from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import DatePickerField from '@/components/ui/DatePickerField'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { REQUEST_PROTOCOLS, REQUEST_TYPE_LABELS } from '@/lib/accessRequests'
import { cn } from '@/lib/utils'
import type { AccessRequestResponse, Node, PresetResponse, User } from '@/types'

/** Дата «сегодня + 30 дней» в формате YYYY-MM-DD для календаря продления. */
function defaultExtendDate(days = 30): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${mm}-${dd}`
}

export interface AccessRequestsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  focusRequestId: number | null
  /** Сколько ожидающих заявок — для бейджа в шапке страницы. */
  onCountChange: (count: number) => void
  /** Список абонентов изменился; при наличии списка родитель обновляет его без повторного запроса. */
  onUsersChanged: (list?: User[]) => void
}

/** Диалог «Заявки на доступ»: план для new_user, одобрение/отказ и превью чека. */
export default function AccessRequestsDialog({
  open,
  onOpenChange,
  focusRequestId,
  onCountChange,
  onUsersChanged,
}: AccessRequestsDialogProps) {
  const { isEnabled } = useFeatureModules()
  const { pendingRequestsCount } = useNotificationCenter()
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()

  const [requests, setRequests] = useState<AccessRequestResponse[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null)
  const [requestPresets, setRequestPresets] = useState<PresetResponse[]>([])
  const [requestNodes, setRequestNodes] = useState<Node[]>([])
  const [approvePresetId, setApprovePresetId] = useState<number | null>(null)
  const [approveNodeIds, setApproveNodeIds] = useState<number[]>([])
  const [approveProtocols, setApproveProtocols] = useState<string[]>([])
  const [approveUsername, setApproveUsername] = useState('')
  const [approveAccessDays, setApproveAccessDays] = useState('')
  const [approvingId, setApprovingId] = useState<number | null>(null)
  const [extendTarget, setExtendTarget] = useState<{ id: number; date: string } | null>(null)
  const [rejectTarget, setRejectTarget] = useState<{ id: number; reason: string } | null>(null)

  // Новый identity колбэка из родителя не должен перезапускать загрузку заявок.
  const onCountChangeRef = useRef(onCountChange)
  useEffect(() => {
    onCountChangeRef.current = onCountChange
  }, [onCountChange])

  const receiptUrlRef = useRef<string | null>(null)
  const setReceipt = useCallback((url: string | null) => {
    const prev = receiptUrlRef.current
    if (prev && prev !== url) URL.revokeObjectURL(prev)
    receiptUrlRef.current = url
    setReceiptUrl(url)
  }, [])
  useEffect(
    () => () => {
      if (receiptUrlRef.current) URL.revokeObjectURL(receiptUrlRef.current)
    },
    [],
  )

  const availableRequestProtocols = useMemo(
    () => REQUEST_PROTOCOLS.filter((p) => p.featureKeys.some((key) => isEnabled(key))),
    [isEnabled],
  )
  const hasNewUserRequests = requests.some((r) => r.request_type === 'new_user')
  const canApproveNewUser =
    approvePresetId != null || (approveNodeIds.length > 0 && approveProtocols.length > 0)
  const reloadRequests = useCallback(async () => {
    setRequestsLoading(true)
    try {
      const list = await listRequests({ status: 'pending' })
      setRequests(list)
      onCountChangeRef.current(list.length)
    } catch {
      /* Список заявок не критичен: диалог покажет пустое состояние. */
    } finally {
      setRequestsLoading(false)
    }
  }, [])

  // Новая заявка из Telegram (SSE-счётчик) появляется без перезагрузки страницы.
  useEffect(() => {
    void reloadRequests()
  }, [reloadRequests, pendingRequestsCount])

  // Открытие диалога всегда сопровождается свежим запросом списка.
  useEffect(() => {
    if (!open) return
    void reloadRequests()
  }, [open, reloadRequests])

  // План для одобрения new_user: шаблон или узлы+протоколы.
  useEffect(() => {
    if (!open) return
    let cancelled = false
    const load = async () => {
      try {
        const [presets, nodes] = await Promise.all([listPresets(), getNodes()])
        if (cancelled) return
        setRequestPresets(presets)
        setRequestNodes(nodes)
        const defaultPreset = presets.find((p) => p.is_default) ?? presets[0] ?? null
        setApprovePresetId(defaultPreset?.id ?? null)
        setApproveNodeIds(nodes.filter((n) => n.node_kind !== 'proxy').map((n) => n.id))
        setApproveProtocols((prev) => {
          const allowed = new Set(availableRequestProtocols.map((p) => p.id))
          const kept = prev.filter((id) => allowed.has(id))
          if (kept.length > 0) return kept
          return availableRequestProtocols[0] ? [availableRequestProtocols[0].id] : []
        })
      } catch {
        if (!cancelled) {
          setRequestPresets([])
          setRequestNodes([])
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [open, availableRequestProtocols])

  // Подсветить и подскроллить заявку, к которой вела ссылка из Telegram.
  useEffect(() => {
    if (!open || focusRequestId == null) return
    document
      .getElementById(`access-request-${focusRequestId}`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [open, focusRequestId, requests])

  // Превью чека не должно переживать закрытие диалога.
  useEffect(() => {
    if (!open) setReceipt(null)
  }, [open, setReceipt])

  const finishApprove = async (telegramId: string | undefined) => {
    const list = await getUsers({ includeDeleting: true })
    onUsersChanged(list)
    await reloadRequests()
    const userRow = telegramId ? list.find((u) => u.telegram_id === telegramId) : undefined
    if (userRow?.active_task_id) {
      trackBackgroundTask(userRow.active_task_id, {
        onComplete: () => {
          onUsersChanged()
          success('Конфиги для заявки применены')
        },
        onError: (_task, message) => notifyError(message),
      })
    } else {
      window.setTimeout(() => onUsersChanged(), 2500)
    }
  }

  const handleApproveExtend = async () => {
    if (!extendTarget) return
    const target = new Date(`${extendTarget.date}T23:59:59`)
    if (Number.isNaN(target.getTime())) {
      notifyError('Выберите дату продления')
      return
    }
    const requestId = extendTarget.id
    setApprovingId(requestId)
    try {
      await approveRequest(requestId, { access_until: target.toISOString() })
      success(`Доступ продлён до ${target.toLocaleDateString('ru-RU')}`)
      setExtendTarget(null)
      await finishApprove(requests.find((r) => r.id === requestId)?.telegram_id)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка продления')
      await reloadRequests()
    } finally {
      setApprovingId(null)
    }
  }

  const handleApproveRequest = async (requestId: number, requestType: string) => {
    if (requestType === 'new_user' && !canApproveNewUser) {
      notifyError('Выберите шаблон или узлы и протоколы')
      return
    }
    const telegramId = requests.find((r) => r.id === requestId)?.telegram_id
    const username = approveUsername.trim() || undefined
    let accessUntil: string | undefined
    const daysRaw = approveAccessDays.trim()
    if (daysRaw !== '') {
      const days = Number.parseInt(daysRaw, 10)
      if (!Number.isFinite(days) || days < 1) {
        notifyError('Срок в днях — целое число от 1')
        return
      }
      const until = new Date()
      until.setUTCDate(until.getUTCDate() + days)
      accessUntil = until.toISOString()
    }
    setApprovingId(requestId)
    try {
      if (requestType === 'new_user') {
        if (approvePresetId != null) {
          await approveRequest(requestId, {
            preset_id: approvePresetId,
            username,
            access_until: accessUntil,
          })
        } else {
          await approveRequest(requestId, {
            node_ids: approveNodeIds,
            protocols: approveProtocols,
            config_count: 1,
            username,
            access_until: accessUntil,
          })
        }
      } else if (requestType === 'add_config') {
        await approveRequest(requestId, { count: 1 })
      } else if (requestType === 'extend_access') {
        const days = daysRaw !== '' ? Number.parseInt(daysRaw, 10) : 30
        await approveRequest(requestId, {
          days: Number.isFinite(days) && days >= 1 ? days : 30,
        })
      } else {
        await approveRequest(requestId, {})
      }
      success('Заявка одобрена — создаётся абонент и конфиги')
      await finishApprove(telegramId)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка одобрения')
      // Решение не принято: перечитываем список, чтобы заявка осталась на экране.
      await reloadRequests()
    } finally {
      setApprovingId(null)
    }
  }

  const handleRejectRequest = async (requestId: number, reason?: string) => {
    try {
      await rejectRequest(requestId, { ban: false, reason: reason?.trim() || undefined })
      success('Заявка отклонена')
      setRejectTarget(null)
      await reloadRequests()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отказа')
    }
  }

  const handleOpenReceipt = async (requestId: number) => {
    try {
      const blob = await getRequestReceipt(requestId)
      setReceipt(URL.createObjectURL(blob))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось открыть чек')
    }
  }
  return (
    <>
      {receiptUrl && (
        <AppDialog
          open
          onOpenChange={(next) => {
            if (!next) setReceipt(null)
          }}
          title="Чек оплаты"
          description="Фото, которое прислал абонент в Telegram"
          size="xl"
        >
          <img
            src={receiptUrl}
            alt="Чек оплаты"
            className="mx-auto max-h-[70dvh] w-auto rounded-lg object-contain"
          />
        </AppDialog>
      )}

      <AppDialog
        open={open}
        onOpenChange={onOpenChange}
        title="Заявки на доступ"
        description="Запросы доступа из Telegram-бота: одобрите или отклоните"
        size="lg"
        className="w-[min(96vw,42rem)] max-w-2xl"
        bodyClassName="px-4 py-3 sm:px-6"
      >
        {requestsLoading ? (
          <Spinner label="Загрузка заявок…" />
        ) : requests.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Нет ожидающих заявок</div>
        ) : (
          <div className="space-y-4">
            {hasNewUserRequests && (
              <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
                <p className="text-sm font-medium">План для новых пользователей</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="approve-username">Логин (необязательно)</Label>
                    <Input
                      id="approve-username"
                      value={approveUsername}
                      onChange={(e) => setApproveUsername(e.target.value)}
                      placeholder="пусто → tg… или @ник"
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="approve-days">Срок, дней (необязательно)</Label>
                    <Input
                      id="approve-days"
                      type="number"
                      min={1}
                      step={1}
                      value={approveAccessDays}
                      onChange={(e) => setApproveAccessDays(e.target.value)}
                      placeholder="пусто → без срока"
                    />
                  </div>
                </div>
                {requestPresets.length > 0 ? (
                  <div className="space-y-1.5">
                    <Label htmlFor="approve-preset">Шаблон предоставления</Label>
                    <select
                      id="approve-preset"
                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                      value={approvePresetId ?? ''}
                      onChange={(e) => {
                        const raw = e.target.value
                        setApprovePresetId(raw === '' ? null : Number.parseInt(raw, 10))
                      }}
                    >
                      <option value="">Без шаблона — выбрать узлы ниже</option>
                      {requestPresets.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                          {p.is_default ? ' (по умолчанию)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    Шаблонов пока нет — укажите узлы и протоколы для создания абонента.
                  </p>
                )}
                {approvePresetId == null && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-2">
                      <Label>Узлы</Label>
                      {requestNodes.length === 0 ? (
                        <p className="text-xs text-muted-foreground">Нет узлов</p>
                      ) : (
                        requestNodes
                          .filter((n) => n.node_kind !== 'proxy')
                          .map((n) => (
                            <label key={n.id} className="flex items-center gap-2 text-sm">
                              <Checkbox
                                checked={approveNodeIds.includes(n.id)}
                                onCheckedChange={(checked) => {
                                  setApproveNodeIds((prev) =>
                                    checked
                                      ? prev.includes(n.id)
                                        ? prev
                                        : [...prev, n.id]
                                      : prev.filter((id) => id !== n.id),
                                  )
                                }}
                              />
                              {n.name}
                            </label>
                          ))
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label>Протоколы</Label>
                      {availableRequestProtocols.length === 0 ? (
                        <p className="text-xs text-muted-foreground">Нет включённых протоколов</p>
                      ) : (
                        availableRequestProtocols.map((p) => (
                          <label key={p.id} className="flex items-center gap-2 text-sm">
                            <Checkbox
                              checked={approveProtocols.includes(p.id)}
                              onCheckedChange={(checked) => {
                                setApproveProtocols((prev) =>
                                  checked
                                    ? prev.includes(p.id)
                                      ? prev
                                      : [...prev, p.id]
                                    : prev.filter((id) => id !== p.id),
                                )
                              }}
                            />
                            {p.label}
                          </label>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="space-y-2">
              {requests.map((r) => {
                const approveDisabled =
                  approvingId === r.id ||
                  (r.request_type === 'new_user' && !canApproveNewUser)
                const title =
                  r.telegram_name ||
                  (r.telegram_username ? `@${r.telegram_username}` : r.telegram_id)
                const metaParts = [
                  r.telegram_username ? `@${r.telegram_username}` : null,
                  `TG ${r.telegram_id}`,
                  REQUEST_TYPE_LABELS[r.request_type] ?? r.request_type,
                  new Date(r.created_at).toLocaleString('ru-RU'),
                ].filter(Boolean)
                return (
                  <div
                    key={r.id}
                    id={`access-request-${r.id}`}
                    className={cn(
                      'flex items-center justify-between gap-3 rounded-lg border p-3',
                      focusRequestId === r.id && 'border-primary ring-2 ring-primary/30',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{title}</p>
                      <p className="text-xs text-muted-foreground">{metaParts.join(' · ')}</p>
                    </div>
                    <div className="flex gap-1">
                      {r.receipt_file_id && (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => void handleOpenReceipt(r.id)}
                        >
                          Чек
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant="default"
                        onClick={() => {
                          if (r.request_type === 'extend_access') {
                            setExtendTarget({ id: r.id, date: defaultExtendDate() })
                          } else {
                            void handleApproveRequest(r.id, r.request_type)
                          }
                        }}
                        disabled={approveDisabled}
                      >
                        {approvingId === r.id ? '…' : 'Одобрить'}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        onClick={() => setRejectTarget({ id: r.id, reason: '' })}
                        disabled={approvingId === r.id}
                      >
                        Отклонить
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </AppDialog>

      {extendTarget && (
        <AppDialog
          open
          onOpenChange={(next) => {
            if (!next) setExtendTarget(null)
          }}
          title="Продлить доступ"
          description="До какой даты продлить доступ абонента по заявке"
          size="md"
          footer={
            <>
              <Button variant="outline" onClick={() => setExtendTarget(null)}>
                Отмена
              </Button>
              <Button onClick={() => void handleApproveExtend()} disabled={approvingId !== null}>
                {approvingId === extendTarget.id ? '…' : 'Одобрить'}
              </Button>
            </>
          }
        >
          <div className="space-y-2">
            <Label htmlFor="extend-until">Продлить до</Label>
            <DatePickerField
              id="extend-until"
              value={extendTarget.date}
              onChange={(value) => setExtendTarget({ ...extendTarget, date: value })}
              fromDate={new Date()}
            />
            <p className="text-xs text-muted-foreground">
              Продление добавляется к текущему сроку, если он ещё не истёк.
            </p>
          </div>
        </AppDialog>
      )}

      {rejectTarget && (
        <AppDialog
          open
          onOpenChange={(next) => {
            if (!next) setRejectTarget(null)
          }}
          title="Отклонить заявку"
          description="Причина уйдёт абоненту в Telegram; без неё он получит нейтральный ответ"
          size="md"
          footer={
            <>
              <Button variant="outline" onClick={() => setRejectTarget(null)}>
                Отмена
              </Button>
              <Button
                variant="destructive"
                onClick={() => void handleRejectRequest(rejectTarget.id, rejectTarget.reason)}
              >
                Отклонить
              </Button>
            </>
          }
        >
          <div className="space-y-2">
            <Label htmlFor="reject-reason">Причина отказа (необязательно)</Label>
            <Input
              id="reject-reason"
              value={rejectTarget.reason}
              onChange={(event) =>
                setRejectTarget({ ...rejectTarget, reason: event.target.value })
              }
              placeholder="Например: чек не читается"
              maxLength={256}
            />
          </div>
        </AppDialog>
      )}
    </>
  )
}




