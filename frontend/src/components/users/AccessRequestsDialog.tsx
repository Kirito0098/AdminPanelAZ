import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getUsers } from '@/api/client'
import {
  approveRequest,
  getRequestReceipt,
  getRequestsCount,
  listRequests,
  rejectRequest,
} from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import DatePickerField from '@/components/ui/DatePickerField'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { cn } from '@/lib/utils'
import type { AccessRequestResponse, User } from '@/types'

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
  /** Заявку на нового пользователя одобряем в диалоге создания абонента. */
  onApproveNewUser?: (request: AccessRequestResponse) => void
  /** Список абонентов изменился; при наличии списка родитель обновляет его без повторного запроса. */
  onUsersChanged: (list?: User[]) => void
}

/** Диалог «Заявки»: одобрение/отказ запросов абонентов и превью чека. */
export default function AccessRequestsDialog({
  open,
  onOpenChange,
  focusRequestId,
  onCountChange,
  onUsersChanged,
  onApproveNewUser,
}: AccessRequestsDialogProps) {
  const { pendingRequestsCount } = useNotificationCenter()
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()

  const [requests, setRequests] = useState<AccessRequestResponse[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
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

  const PAGE = 100

  const reloadRequests = useCallback(async () => {
    setRequestsLoading(true)
    try {
      const list = await listRequests({
        status: 'pending',
        q: query || undefined,
        limit: PAGE,
      })
      setRequests(list)
      setHasMore(list.length >= PAGE)
      getRequestsCount('pending')
        .then((count) => onCountChangeRef.current(count))
        .catch(() => onCountChangeRef.current(list.length))
    } catch {
      /* Список заявок не критичен: диалог покажет пустое состояние. */
    } finally {
      setRequestsLoading(false)
    }
  }, [query])

  const loadMoreRequests = async () => {
    if (loadingMore) return
    setLoadingMore(true)
    try {
      const list = await listRequests({
        status: 'pending',
        q: query || undefined,
        limit: PAGE,
        offset: requests.length,
      })
      setRequests((prev) => [...prev, ...list])
      setHasMore(list.length >= PAGE)
    } catch {
      notifyError('Не удалось догрузить заявки')
    } finally {
      setLoadingMore(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  // Новая заявка из Telegram (SSE-счётчик) появляется без перезагрузки страницы.
  useEffect(() => {
    void reloadRequests()
  }, [reloadRequests, pendingRequestsCount])

  // Открытие диалога всегда сопровождается свежим запросом списка.
  useEffect(() => {
    if (!open) return
    void reloadRequests()
  }, [open, reloadRequests])

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
    // new_user одобряется в диалоге создания абонента (onApproveNewUser).
    const telegramId = requests.find((r) => r.id === requestId)?.telegram_id
    setApprovingId(requestId)
    try {
      if (requestType === 'add_config') {
        await approveRequest(requestId, { count: 1 })
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
  const grouped = (
    [
      { key: 'new_user', title: 'Новый доступ' },
      { key: 'add_config', title: 'Дополнительный конфиг' },
      { key: 'extend_access', title: 'Продление доступа' },
    ] as const
  )
    .map((group) => ({
      ...group,
      items: requests.filter((r) => r.request_type === group.key),
    }))
    .filter((group) => group.items.length > 0)

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
        title="Заявки"
        description="Запросы из Telegram-бота: новый доступ, дополнительный конфиг или продление"
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
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по TG ID, нику или имени"
              className="h-9"
              aria-label="Поиск по заявкам"
            />
            <div className="space-y-2">
              {grouped.map((group) => (
                <div key={group.key} className="space-y-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.title} · {group.items.length}
                  </p>
                  {group.items.map((r) => {
                const approveDisabled = approvingId === r.id
                const title =
                  r.telegram_name ||
                  (r.telegram_username ? `@${r.telegram_username}` : r.telegram_id)
                const metaParts = [
                  r.telegram_username ? `@${r.telegram_username}` : null,
                  `TG ${r.telegram_id}`,
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
                          if (r.request_type === 'new_user' && onApproveNewUser) {
                            onApproveNewUser(r)
                          } else if (r.request_type === 'extend_access') {
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
              ))}
              {hasMore && (
                <Button
                  variant="outline"
                  className="self-center"
                  onClick={() => void loadMoreRequests()}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Загрузка…' : 'Загрузить ещё'}
                </Button>
              )}
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




