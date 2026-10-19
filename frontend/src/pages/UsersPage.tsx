import { useCallback, useEffect, useMemo, useState } from 'react'
import { Navigate, useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { MoreHorizontal, Ticket, UserPlus, Users } from 'lucide-react'
import {
  ApiError,
  deleteUser,
  getUsers,
  updateUser,
} from '@/api/client'
import {
  createProvisionedUser,
  deleteProvisionedUser,
  downloadBulkNodesReport,
  getProvisioning,
  listRequests,
  approveRequest,
  rejectRequest,
} from '@/api/users'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { formatDate } from '@/lib/datetime'
import { triggerFileDownload } from '@/lib/triggerFileDownload'
import type {
  User,
  UserUpdatePayload,
  UserProvisioningCard,
  UserProvisionSummary,
  BulkNodesAction,
} from '@/types'
import { UsersFilters } from '@/components/users/UsersFilters'
import CreateUserDialog from '@/components/users/CreateUserDialog'
import BulkNodesDialog from '@/components/users/BulkNodesDialog'
import UsersBulkBar from '@/components/users/UsersBulkBar'
import UserCard from '@/components/users/UserCard'

export default function UsersPage() {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const { backgroundTask, trackBackgroundTask } = useProgress()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [requestsOpen, setRequestsOpen] = useState(false)
  const [requests, setRequests] = useState<{ id: number; request_type: string; telegram_id: string; telegram_name: string | null; status: string; created_at: string }[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [bulkDialog, setBulkDialog] = useState<{
    open: boolean
    action: BulkNodesAction
    presetNodeId?: number
  }>({ open: false, action: 'add' })

  const provisioningOn = isEnabled('user_provisioning')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const list = await getUsers()
        if (!cancelled) setUsers(list)
      } catch (err) {
        if (!cancelled) notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить пользователей')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [notifyError])

  useEffect(() => {
    if (!provisioningOn) return
    let cancelled = false
    const loadRequests = async () => {
      setRequestsLoading(true)
      try {
        const list = await listRequests({ status: 'pending' })
        if (!cancelled) setRequests(list)
      } catch {
        /* вложенная опциональна */
      } finally {
        if (!cancelled) setRequestsLoading(false)
      }
    }
    void loadRequests()
    return () => {
      cancelled = true
    }
  }, [provisioningOn, notifyError])

  // Смена фильтра сбрасывает выбор — иначе в область попадут скрытые пользователи.
  useEffect(() => {
    setSelectedIds([])
  }, [filter, search])

  // Вход с карточки сервера: /users?bulkAddNode={id}
  useEffect(() => {
    const raw = searchParams.get('bulkAddNode')
    const id = Number.parseInt(raw ?? '', 10)
    if (!Number.isFinite(id) || id <= 0) return
    setBulkDialog({ open: true, action: 'add', presetNodeId: id })
    const next = new URLSearchParams(searchParams)
    next.delete('bulkAddNode')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const handleBulkStarted = (taskId: string) => {
    success('Массовая операция запущена')
    trackBackgroundTask(taskId, {
      onComplete: (task) => success(task.message || 'Массовая операция завершена'),
      onError: (_task, message) => notifyError(message),
    })
  }

  const handleDownloadReport = async (taskId: string) => {
    try {
      const res = await downloadBulkNodesReport(taskId)
      const blob = await res.blob()
      triggerFileDownload(blob, `bulk-nodes-${taskId}.json`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось скачать отчёт')
    }
  }

  const handleApproveRequest = async (requestId: number, presetId?: number) => {
    try {
      await approveRequest(requestId, { preset_id: presetId ?? undefined })
      setRequests((prev) => prev.filter((r) => r.id !== requestId))
      success('Заявка одобрена')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка одобрения')
    }
  }

  const handleRejectRequest = async (requestId: number) => {
    try {
      await rejectRequest(requestId, { ban: false })
      setRequests((prev) => prev.filter((r) => r.id !== requestId))
      success('Заявка отклонена')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отказа')
    }
  }

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    let list = users.filter((u) => {
      if (!q) return true
      return u.username.toLowerCase().includes(q) || String(u.id).includes(q)
    })
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    const weekLater = new Date(now)
    weekLater.setDate(weekLater.getDate() + 7)
    switch (filter) {
      case 'attention':
        list = list.filter(
          (u) => u.provision_state === 'partial' || u.provision_state === 'pending',
        )
        break
      case 'unmanaged':
        list = list.filter((u) => u.provision_state === 'unmanaged')
        break
      case 'expiring':
        list = list.filter((u) => {
          if (!u.access_until) return false
          const d = new Date(u.access_until)
          return d >= now && d <= weekLater
        })
        break
      case 'expired':
        list = list.filter((u) => {
          if (!u.access_until) return false
          return new Date(u.access_until) < now
        })
        break
      case 'suspended':
        list = list.filter((u) => Boolean(u.suspended_at))
        break
      case 'inactive':
        list = list.filter((u) => u.is_active === false)
        break
      default:
        break
    }
    return list.sort((a, b) => a.username.localeCompare(b.username, 'ru'))
  }, [users, filter, search])

  const handleCreate = async (data: {
    username: string
    client_base_name: string
    node_ids: number[]
    protocols: string[]
    config_count: number
    config_quota?: number | null
    access_until?: string | null
    panel_login_enabled: boolean
    password?: string | null
    telegram_id?: string | null
    preset_id?: number | null
  }) => {
    try {
      const created = await createProvisionedUser({
        username: data.username,
        client_base_name: data.client_base_name,
        node_ids: data.node_ids,
        protocols: data.protocols,
        config_count: data.config_count,
        config_quota: data.config_quota ?? null,
        access_until: data.access_until ?? null,
        panel_login_enabled: data.panel_login_enabled,
        password: data.password ?? null,
        telegram_id: data.telegram_id ?? null,
      })
      setCreateOpen(false)
      success(`Пользователь «${data.username}» создан — применяется план конфигов`)
      void navigate(`/users/${created.user.id}`, { replace: false })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания пользователя')
    }
  }

  const handleDeleteUser = async (user: UserProvisionSummary) => {
    if (!window.confirm(`Удалить пользователя «${user.username}"?`)) return
    try {
      if (user.provision_state === 'unmanaged' || !user.client_base_name) {
        await deleteUser(user.id)
      } else {
        await deleteProvisionedUser(user.id)
      }
      success(`Пользователь «${user.username}» удалён`)
      setUsers((prev) => prev.filter((u) => u.id !== user.id))
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления пользователя')
    }
  }

  const handleSaveUser = async (userId: number, data: UserUpdatePayload) => {
    try {
      const updated = await updateUser(userId, data)
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)))
      success(`Данные «${updated.username}» сохранены`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения пользователя')
    }
  }

  if (loading) return <Spinner label="Загрузка пользователей…" />

  // Отдельная карточка абонента по маршруту /users/:id
  if (userId) {
    const targetId = Number.parseInt(userId, 10)
    return (
      <div className="flex flex-col gap-4">
        <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void navigate('/users', { replace: true })}
          >
            Назад к списку
          </Button>
        </CardHeader>
        <UserCardView
          userId={targetId}
          onBack={() => void navigate('/users', { replace: true })}
          onSave={(id, data) => void handleSaveUser(id, data)}
          onDelete={(user) => void handleDeleteUser(user)}
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-3 sm:space-y-0 sm:pb-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users size={18} />
              Пользователи
            </CardTitle>
            <CardDescription className="mt-1">
              {filteredUsers.length} пользовател{filteredUsers.length === 1 ? 'ь' : filteredUsers.length < 5 ? 'я' : 'й'} ·{
                ' '
              }
              {provisioningOn ? 'Предоставление конфигов включено' : 'Модуль выключен в Настройках → Разделы'}
            </CardDescription>
          </div>
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            disabled={!provisioningOn}
            aria-label="Создать пользователя"
          >
            <UserPlus size={15} />
            Создать пользователя
          </Button>
          {provisioningOn && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setRequestsOpen(true)}
              aria-label="Заявки на доступ"
              className="relative"
            >
              <Ticket size={14} />
              Заявки
              {requests.length > 0 && (
                <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center">
                  <Badge variant="destructive" className="text-[10px] px-1.5">
                    {requests.length}
                  </Badge>
                </span>
              )}
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 min-w-0 sm:w-80">
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по логину…"
                className="h-10 bg-background pl-9 pr-9"
                aria-label="Поиск пользователей"
              />
              {search ? (
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  onClick={() => setSearch('')}
                  aria-label="Очистить поиск"
                >
                  <MoreHorizontal size={14} />
                </button>
              ) : null}
            </div>
            <UsersFilters filter={filter} onFilterChange={setFilter} />
          </div>

          {provisioningOn && (
            <UsersBulkBar
              selectedCount={selectedIds.length}
              busy={backgroundTask?.task_type === 'bulk_user_nodes' && ['queued', 'running'].includes(backgroundTask.status)}
              task={backgroundTask?.task_type === 'bulk_user_nodes' ? backgroundTask : null}
              onAction={(action) => setBulkDialog({ open: true, action })}
              onDownloadReport={(taskId) => void handleDownloadReport(taskId)}
            />
          )}

          {filteredUsers.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Пока нет пользователей"
              description={
                provisioningOn
                  ? 'Создайте первого абонента — панель sama выпустит конфиги на выбранных серверах.'
                  : 'Включите модуль «Пользователи (абоненты)» в настройках разделов, чтобы управлять абонентами VPN.'
              }
              className="py-10"
              action={
                provisioningOn ? (
                  <Button type="button" onClick={() => setCreateOpen(true)} aria-label="Создать первого пользователя">
                    <UserPlus size={15} />
                    Создать пользователя
                  </Button>
                ) : null
              }
            />
          ) : (
            <div className="overflow-x-auto border rounded-lg">
              <table className="min-w-full align-middle text-sm">
                <thead>
                  <tr className="text-muted-foreground bg-muted/50">
                    {provisioningOn && (
                      <th className="w-8 p-3 text-left">
                        <Checkbox
                          checked={
                            filteredUsers.length > 0 &&
                            filteredUsers.every((u) => selectedIds.includes(u.id))
                          }
                          onCheckedChange={(next) =>
                            setSelectedIds(
                              next ? filteredUsers.map((u) => u.id) : [],
                            )
                          }
                          aria-label="Выбрать всех"
                        />
                      </th>
                    )}
                    <th className="p-3 text-left">Пользователь</th>
                    <th className="p-3 text-left">Узлы</th>
                    <th className="p-3 text-left">Протоколы</th>
                    <th className="p-3 text-left">Срок доступа</th>
                    <th className="p-3 text-left">Режим</th>
                    <th className="p-3 text-left">Задача</th>
                    <th className="p-3 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u) => {
                    const nodeLabels = (u.plan_node_ids ?? []).map((n) => String(n)).join(', ') || '—'
                    const protocols = (u.plan_protocols ?? []).length
                      ? (u.plan_protocols ?? []).join(', ')
                      : '—'
                    let termText = '—'
                    let termTone: 'default' | 'warning' | 'danger' = 'default'
                    if (u.access_until) {
                      const d = new Date(u.access_until)
                      if (d < new Date()) {
                        termText = `Истёк ${formatDate(u.access_until)}`
                        termTone = 'danger'
                      } else if (d <= new Date(Date.now() + 7 * 86400000)) {
                        termText = `До ${formatDate(u.access_until)}`
                        termTone = 'warning'
                      } else {
                        termText = formatDate(u.access_until)
                      }
                    }
                    const stateLabel = {
                      unmanaged: 'Без набора',
                      pending: 'Применяется',
                      partial: 'Требует внимания',
                      ok: 'OK',
                    }[u.provision_state ?? 'unmanaged'] || u.provision_state
                    return (
                      <tr key={u.id} className="border-b hover:bg-muted/50 group">
                        {provisioningOn && (
                          <td className="p-3">
                            <Checkbox
                              checked={selectedIds.includes(u.id)}
                              onCheckedChange={(next) =>
                                setSelectedIds((prev) =>
                                  next ? [...prev, u.id] : prev.filter((id) => id !== u.id),
                                )
                              }
                              aria-label={`Выбрать ${u.username}`}
                            />
                          </td>
                        )}
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">{u.username}</span>
                            <Badge variant={u.role === 'admin' ? 'default' : 'secondary'} className="text-[10px]">
                              {u.role === 'admin' ? 'Админ' : 'Абонент'}
                            </Badge>
                          </div>
                          <p className="mt-0.5 text-[11px] text-muted-foreground">
                            {u.client_base_name ? `Базовое имя: ${u.client_base_name}` : 'Базовое имя не задано'}
                            {u.telegram_id ? ` · TG ${u.telegram_id}` : ''}
                          </p>
                        </td>
                        <td className="p-3 text-[11px] text-muted-foreground">{nodeLabels}</td>
                        <td className="p-3 text-[11px] font-mono">{protocols}</td>
                        <td className="p-3">
                          <Badge
                            variant={termTone === 'danger' ? 'destructive' : termTone === 'warning' ? 'warning' : 'secondary'}
                            className="text-[11px]"
                          >
                            {termText}
                          </Badge>
                        </td>
                        <td className="p-3">
                          <Badge variant="outline" className="text-[11px]">
                            {stateLabel}
                          </Badge>
                          {u.plan_config_count != null && u.plan_config_count > 0 && (
                            <span className="ml-1 text-[11px] text-muted-foreground">
                              {u.plan_config_count} им.
                            </span>
                          )}
                        </td>
                        <td className="p-3">
                          {u.active_task_id ? (
                            <div className="flex items-center gap-2 text-xs">
                              <span className="text-muted-foreground">Выполняется…</span>
                            </div>
                          ) : (
                            <span className="text-[11px] text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => void navigate(`/users/${u.id}`, { replace: false })}
                              aria-label={`Карточка ${u.username}`}
                            >
                              <MoreHorizontal size={14} />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {createOpen ? (
        <CreateUserDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreate={handleCreate}
        />
      ) : null}

      {provisioningOn && (
        <BulkNodesDialog
          open={bulkDialog.open}
          onOpenChange={(open) => setBulkDialog((prev) => ({ ...prev, open }))}
          presetNodeId={bulkDialog.presetNodeId}
          presetAction={bulkDialog.action}
          selectedUserIds={selectedIds}
          listFilter={{ state: filter, q: search }}
          onStarted={handleBulkStarted}
        />
      )}

      {provisioningOn && requestsOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setRequestsOpen(false)} />
          <div className="relative bg-background w-full max-w-2xl p-4 max-h-[80vh] overflow-y-auto shadow-xl rounded-lg border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Заявки на доступ</h2>
              <Button type="button" variant="ghost" size="sm" onClick={() => setRequestsOpen(false)}>
                Закрыть
              </Button>
            </div>
            {requestsLoading ? (
              <Spinner label="Загрузка заявок…" />
            ) : requests.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">Нет ожидающих заявок</div>
            ) : (
              <div className="space-y-2">
                {requests.map((r) => (
                  <div key={r.id} className="flex items-center justify-between gap-3 rounded-lg border p-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-sm">{r.telegram_name || r.telegram_id}</p>
                      <p className="text-xs text-muted-foreground">
                        TG {r.telegram_id} · {r.request_type} · {new Date(r.created_at).toLocaleString('ru-RU')}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="default"
                        onClick={() => void handleApproveRequest(r.id)}
                        disabled={r.request_type === 'new_user'}
                      >
                        Одобрить
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        onClick={() => void handleRejectRequest(r.id)}
                      >
                        Отклонить
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Роутуемая карточка абонента (открывается по /users/:id). */
function UserCardView({
  userId,
  onBack,
  onSave,
  onDelete,
}: {
  userId: number
  onBack: () => void
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onDelete: (user: UserProvisionSummary) => void
}) {
  const [card, setCard] = useState<UserProvisioningCard | null>(null)
  const [loading, setLoading] = useState(true)
  const { error: notifyError } = useNotifications()

  const load = useCallback(async () => {
    try {
      const data = await getProvisioning(userId)
      setCard(data)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку')
    }
  }, [userId, notifyError])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void (async () => {
      try {
        const data = await getProvisioning(userId)
        if (!cancelled) setCard(data)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [userId, notifyError])

  if (loading) return <Spinner label="Загрузка карточки…" />
  if (!card) return <Navigate to="/users" replace />

  return (
    <UserCard
      card={card}
      onBack={onBack}
      onSave={onSave}
      onDelete={onDelete}
      onRefresh={() => void load()}
    />
  )
}
