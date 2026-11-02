import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  Download,
  Filter,
  PauseCircle,
  Search,
  Ticket,
  UserPlus,
  UserRound,
  Users,
  X,
} from 'lucide-react'
import { ApiError, deleteUser, updateUser } from '@/api/client'
import {
  createProvisionedUser,
  createUserFromExisting,
  deleteProvisionedUser,
  downloadBulkNodesReport,
  extendUserAccess,
  getProvisioning,
  resumeUser,
  resetUserTrafficCounter,
  suspendUser,
} from '@/api/users'
import { useAuth } from '@/context/AuthContext'
import AppDialog from '@/components/shared/AppDialog'
import DocsLink from '@/components/shared/DocsLink'
import ToolbarButton from '@/components/shared/ToolbarButton'
import MetricCard from '@/components/noc/MetricCard'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useUsersList } from '@/hooks/useUsersList'
import { DOCS } from '@/lib/docsUrls'
import { gridColsClass } from '@/lib/configCardViewPrefs'
import { triggerFileDownload } from '@/lib/triggerFileDownload'
import { cn } from '@/lib/utils'
import {
  loadUsersCardViewPrefs,
  saveUsersCardViewPrefs,
  type UsersCardViewPrefs,
} from '@/lib/usersCardViewPrefs'
import { PAGE_SIZE_OPTIONS, type UsersSortKey } from '@/lib/usersListPrefs'
import { REQUEST_PROTOCOLS } from '@/lib/accessRequests'
import type {
  User,
  UserUpdatePayload,
  UserProvisioningCard,
  UserProvisionSummary,
  BulkNodesAction,
} from '@/types'

import { UsersFilters } from '@/components/users/UsersFilters'
import UsersCardViewSettings from '@/components/users/UsersCardViewSettings'
import CreateUserDialog, {
  type CreateUserPayload,
} from '@/components/users/CreateUserDialog'
import BulkNodesDialog from '@/components/users/BulkNodesDialog'
import BulkUsersActionDialog from '@/components/users/BulkUsersActionDialog'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import SuspendUserDialog, { type SuspendUserPayload } from '@/components/users/SuspendUserDialog'
import AccessRequestsDialog from '@/components/users/AccessRequestsDialog'
import UsersBulkBar from '@/components/users/UsersBulkBar'
import SubscriberCard from '@/components/users/SubscriberCard'
import UserCard from '@/components/users/UserCard'

type SortKey = UsersSortKey

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'username', label: 'Имя' },
  { value: 'created_at', label: 'Дата создания' },
  { value: 'access_until', label: 'Срок доступа' },
  { value: 'traffic', label: 'Трафик' },
  { value: 'last_seen', label: 'Активность' },
]

type DeletableUser = {
  id: number
  username: string
  provision_state?: string | null
  client_base_name?: string | null
}

export default function UsersPage() {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user: authUser } = useAuth()
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const { backgroundTask, trackBackgroundTask } = useProgress()
  const {
    users,
    setUsers,
    loading,
    reloadUsers,
    filter,
    setFilter,
    search,
    setSearch,
    stale,
    setStale,
    sortKey,
    setSortKey,
    sortDir,
    setSortDir,
    setPage,
    pageSize,
    setPageSize,
    selectedIds,
    setSelectedIds,
    filteredUsers,
    totalPages,
    safePage,
    pagedUsers,
    bulkTargetIds,
    pagedUserIds,
    allPageSelected,
    somePageSelected,
    listMetrics,
  } = useUsersList()
  const [createOpen, setCreateOpen] = useState(false)
  const [requestsOpen, setRequestsOpen] = useState(false)
  const [requestsCount, setRequestsCount] = useState(0)
  const [focusRequestId, setFocusRequestId] = useState<number | null>(null)
  /** Уже обработанный deep-link (?requests=1 / ?request=<id>), чтобы не открывать диалог циклично. */
  const consumedRequestsParamRef = useRef<string | null>(null)
  const [bulkDialog, setBulkDialog] = useState<{
    open: boolean
    action: BulkNodesAction
    presetNodeId?: number
  }>({ open: false, action: 'add' })
  const [viewPrefs, setViewPrefs] = useState<UsersCardViewPrefs>(() => loadUsersCardViewPrefs())
  const [cardBusyId, setCardBusyId] = useState<number | null>(null)
  const [bulkActionOpen, setBulkActionOpen] = useState(false)
  const [unlockDialogUser, setUnlockDialogUser] = useState<User | null>(null)
  // Быстрая приостановка из карточки списка: причина и уведомление спрашиваем в диалоге.
  const [suspendTarget, setSuspendTarget] = useState<User | null>(null)

  const provisioningOn = isEnabled('user_provisioning')
  const availableRequestProtocols = useMemo(
    () =>
      REQUEST_PROTOCOLS.filter((p) => p.featureKeys.some((key) => isEnabled(key))),
    [isEnabled],
  )
  const unlockProtocols = availableRequestProtocols.map((p) => p.id) as (
    | 'openvpn'
    | 'wireguard'
    | 'amneziawg2'
  )[]

  /** Диалог заявок отдаёт готовый список после одобрения — без повторного запроса. */
  const handleUsersChanged = useCallback(
    (list?: User[]) => {
      if (list) setUsers(list)
      else void reloadUsers()
    },
    [reloadUsers],
  )

  const handleRequestsCount = useCallback((count: number) => {
    setRequestsCount(count)
  }, [])

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

  // Колокол: /users?requests=1, карточка в Telegram: /users?request=<id>.
  // Всегда перечитываем заявки — иначе диалог показывает снимок, снятый
  // при монтировании страницы, и пишет «Нет ожидающих заявок».
  useEffect(() => {
    if (!provisioningOn) return
    const rawRequests = searchParams.get('requests')
    const rawRequest = searchParams.get('request')
    if (rawRequests !== '1' && rawRequest == null) {
      consumedRequestsParamRef.current = null
      return
    }
    const key = `${rawRequests ?? ''}|${rawRequest ?? ''}`
    if (consumedRequestsParamRef.current === key) return
    consumedRequestsParamRef.current = key
    setRequestsOpen(true)
    if (rawRequest != null) {
      const parsed = Number.parseInt(rawRequest, 10)
      setFocusRequestId(Number.isFinite(parsed) && parsed > 0 ? parsed : null)
    }
    const next = new URLSearchParams(searchParams)
    next.delete('requests')
    next.delete('request')
    setSearchParams(next, { replace: true })
  }, [provisioningOn, searchParams, setSearchParams])

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

  const handleCreate = async (data: CreateUserPayload) => {
    try {
      if (data.mode === 'from_existing') {
        const created = await createUserFromExisting({
          username: data.username,
          config_ids: data.config_ids ?? [],
          config_quota: data.config_quota ?? null,
          access_until: data.access_until ?? null,
          panel_login_enabled: data.panel_login_enabled,
          password: data.password ?? null,
          telegram_id: data.telegram_id ?? null,
        })
        setCreateOpen(false)
        success(
          created.assigned_config_ids.length
            ? `«${data.username}» создан, привязано конфигов: ${created.assigned_config_ids.length}`
            : `«${data.username}» создан без конфигов`,
        )
        await reloadUsers()
        void navigate(`/users/${created.user.id}`, { replace: false })
        return
      }
      const created = await createProvisionedUser({
        username: data.username,
        client_base_name: data.client_base_name!,
        node_ids: data.node_ids!,
        protocols: data.protocols!,
        config_count: data.config_count!,
        config_quota: data.config_quota ?? null,
        access_until: data.access_until ?? null,
        panel_login_enabled: data.panel_login_enabled,
        password: data.password ?? null,
        telegram_id: data.telegram_id ?? null,
      })
      setCreateOpen(false)
      success(`Пользователь «${data.username}» создан — применяется план конфигов`)
      await reloadUsers()
      if (created.task_id) {
        trackBackgroundTask(created.task_id, {
          onComplete: () => {
            void reloadUsers()
            success(`План для «${data.username}» применён`)
          },
          onError: (_task, message) => notifyError(message),
        })
      }
      void navigate(`/users/${created.user.id}`, { replace: false })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания пользователя')
    }
  }

  const closeDetail = useCallback(() => {
    void navigate('/users', { replace: true })
  }, [navigate])

  const openDetail = useCallback(
    (id: number) => {
      void navigate(`/users/${id}`)
    },
    [navigate],
  )

  const detailId = useMemo(() => {
    if (!userId) return null
    const id = Number.parseInt(userId, 10)
    return Number.isFinite(id) && id > 0 ? id : null
  }, [userId])

  const handleDeleteUser = async (user: DeletableUser, opts?: { skipConfirm?: boolean }) => {
    if (!opts?.skipConfirm && !window.confirm(`Удалить пользователя «${user.username}»?`)) return
    try {
      if (user.provision_state === 'unmanaged' || !user.client_base_name) {
        await deleteUser(user.id)
      } else {
        await deleteProvisionedUser(user.id)
      }
      success(`Пользователь «${user.username}» удалён`)
      setUsers((prev) => prev.filter((u) => u.id !== user.id))
      if (detailId === user.id) closeDetail()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления пользователя')
    }
  }

  const handleRetryDelete = async (user: User) => {
    setCardBusyId(user.id)
    try {
      await deleteProvisionedUser(user.id)
      success(`Удаление «${user.username}» запущено заново`)
      window.setTimeout(() => void reloadUsers(), 2500)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось повторить удаление')
    } finally {
      setCardBusyId(null)
    }
  }

  const handleSuspend = async (user: User, data: SuspendUserPayload) => {
    setCardBusyId(user.id)
    try {
      await suspendUser(user.id, data)
      success(`Доступ «${user.username}» приостановлен`)
      await reloadUsers()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось приостановить доступ')
    } finally {
      setCardBusyId(null)
    }
  }

  const handleResume = async (user: User) => {
    setCardBusyId(user.id)
    try {
      await resumeUser(user.id, { notify_telegram: true })
      success(`Доступ «${user.username}» возобновлён`)
      await reloadUsers()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось возобновить доступ')
    } finally {
      setCardBusyId(null)
    }
  }

  const handleExtend = async (user: User, days: number) => {
    if (!window.confirm(`Продлить доступ «${user.username}» на ${days} дн.?`)) return
    setCardBusyId(user.id)
    try {
      await extendUserAccess(user.id, days)
      success(`Доступ «${user.username}» продлён на ${days} дн.`)
      await reloadUsers()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось продлить доступ')
    } finally {
      setCardBusyId(null)
    }
  }

  const handleResetTraffic = async (user: User) => {
    if (!window.confirm(`Сбросить счётчик трафика «${user.username}»?`)) return
    setCardBusyId(user.id)
    try {
      await resetUserTrafficCounter(user.id)
      success(`Счётчик трафика «${user.username}» сброшен`)
      await reloadUsers()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось сбросить счётчик трафика')
    } finally {
      setCardBusyId(null)
    }
  }

  const handleChangeViewPrefs = (next: UsersCardViewPrefs) => {
    setViewPrefs(next)
    saveUsersCardViewPrefs(next)
  }

  const handleExportCsv = () => {
    const header = [
      'id',
      'username',
      'role',
      'is_active',
      'provision_state',
      'client_base_name',
      'config_count',
      'protocols',
      'nodes',
      'access_until',
      'telegram_id',
      'suspended_at',
      'suspend_reason',
      'traffic_limit_bytes',
      'traffic_limit_blocked',
      'traffic_consumed_bytes',
      'last_seen_at',
      'note',
      'panel_login_enabled',
      'can_create_configs',
      'can_manage_configs',
      'created_at',
    ]
    const esc = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
    const protocolsOf = (user: User) =>
      (user.plan_protocols?.length ? user.plan_protocols : (user.desired_protocols ?? [])).join('|')
    const rows = users.map((user) =>
      [
        user.id,
        user.username,
        user.role,
        user.is_active,
        user.provision_state ?? '',
        user.client_base_name ?? '',
        user.plan_config_count ?? user.plan_config_indexes?.length ?? '',
        protocolsOf(user),
        user.plan_node_ids?.join('|') ?? '',
        user.access_until ?? '',
        user.telegram_id ?? '',
        user.suspended_at ?? '',
        user.suspend_reason ?? '',
        user.traffic_limit_bytes ?? '',
        user.traffic_limit_blocked ?? '',
        user.traffic_consumed_bytes ?? '',
        user.last_seen_at ?? '',
        user.note ?? '',
        user.panel_login_enabled ?? '',
        user.can_create_configs ?? '',
        user.can_manage_configs ?? '',
        user.created_at,
      ]
        .map(esc)
        .join(','),
    )
    const csv = [header.map((h) => `"${h}"`).join(','), ...rows].join('\n')
    triggerFileDownload(csv, `users-${new Date().toISOString().slice(0, 10)}.csv`)
    success('CSV экспортирован')
  }

  const handleSaveUser = async (
    userId: number,
    data: UserUpdatePayload,
    message?: string,
  ) => {
    try {
      const updated = await updateUser(userId, data)
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)))
      success(message ?? `Данные «${updated.username}» сохранены`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения пользователя')
    }
  }

  if (loading) return <Spinner label="Загрузка пользователей…" />

  return (
    <div className="space-y-4">
      <div className="relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-br from-primary/5 via-card to-card p-5 shadow-sm">
        <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary shadow-sm">
              <Users size={26} strokeWidth={2} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">Пользователи</h2>
                <DocsLink href={DOCS.users} />
              </div>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                Учётные записи панели и привязка к VPN-клиентам на узлах.
                {provisioningOn
                  ? ' Предоставление конфигов включено.'
                  : ' Модуль выключен в Настройках → Разделы.'}
              </p>
            </div>
          </div>

          <div className="flex w-full flex-wrap gap-2 lg:max-w-xl lg:justify-end">
            {provisioningOn && (
              <ToolbarButton
                variant="outline"
                className="relative bg-card/80"
                icon={<Ticket size={16} />}
                label={requestsCount > 0 ? `Заявки (${requestsCount})` : 'Заявки'}
                shortLabel="Заявки"
                onClick={() => setRequestsOpen(true)}
              />
            )}
            <ToolbarButton
              variant="outline"
              className="bg-card/80"
              icon={<Download size={16} />}
              label="Экспорт CSV"
              shortLabel="CSV"
              onClick={handleExportCsv}
            />
            <ToolbarButton
              size="lg"
              variant="default"
              icon={<UserPlus size={18} />}
              label="Создать пользователя"
              shortLabel="Создать"
              onClick={() => setCreateOpen(true)}
              disabled={!provisioningOn}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Всего"
          value={String(listMetrics.total)}
          sub={`${filteredUsers.length} на экране`}
          icon={Users}
          accent="cyan"
        />
        <MetricCard
          label="Активны"
          value={String(listMetrics.active24h)}
          sub="заходили за 24 часа"
          icon={Activity}
          accent="green"
        />
        <MetricCard
          label="С тарифом"
          value={String(listMetrics.withPlan)}
          sub="план конфигов на узлах"
          icon={Ticket}
          accent="green"
        />
        <MetricCard
          label="Срок / истекли"
          value={String(listMetrics.expiringOrExpired)}
          sub="истекают в 7 дней или уже истекли"
          icon={listMetrics.expiringOrExpired > 0 ? AlertTriangle : CalendarClock}
          accent={listMetrics.expiringOrExpired > 0 ? 'amber' : 'default'}
        />
        <MetricCard
          label="На паузе"
          value={String(listMetrics.suspended)}
          sub="приостановленный доступ"
          icon={PauseCircle}
          accent={listMetrics.suspended > 0 ? 'red' : 'default'}
        />
      </div>

      <div className="overflow-hidden rounded-2xl border border-border/80 bg-card shadow-sm">
        <div className="h-1 bg-gradient-to-r from-primary/80 via-primary/40 to-transparent" />
        <CardHeader className="border-b border-border/60 bg-muted/15 pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Users size={18} />
                Список пользователей
              </CardTitle>
              <CardDescription className="mt-1">
                {filteredUsers.length > 0
                  ? `${users.length} пользовател${users.length === 1 ? 'ь' : users.length < 5 ? 'я' : 'ей'} · ${filteredUsers.length} на экране`
                  : 'Пользователи не найдены'}
              </CardDescription>
            </div>
            <div className="flex w-full items-center gap-2 lg:max-w-md">
              <div className="relative min-w-0 flex-1">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск по логину, TG, заметке…"
                  className="h-10 bg-background pl-9 pr-9"
                  aria-label="Поиск пользователей"
                />
                {search.trim() !== '' ? (
                  <button
                    type="button"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setSearch('')}
                    title="Очистить поиск"
                  >
                    <X size={14} />
                  </button>
                ) : null}
              </div>
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="h-10 shrink-0 rounded-md border border-input bg-background px-2 text-sm"
                aria-label="Сортировка"
                title="Сортировка"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-10 w-10 shrink-0"
                onClick={() => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))}
                aria-label={sortDir === 'asc' ? 'По возрастанию' : 'По убыванию'}
                title={sortDir === 'asc' ? 'По возрастанию' : 'По убыванию'}
              >
                {sortDir === 'asc' ? '↑' : '↓'}
              </Button>
              <UsersCardViewSettings prefs={viewPrefs} onChange={handleChangeViewPrefs} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4 sm:p-5">
          <div className="space-y-3 rounded-xl border border-dashed bg-muted/15 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Filter size={13} />
                  Статус
                </span>
                <UsersFilters
                  filter={filter}
                  onFilterChange={setFilter}
                  stale={stale}
                  onStaleChange={setStale}
                />
              </div>
              {provisioningOn && filter !== 'deleting' && pagedUserIds.length > 0 ? (
                <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                  <Checkbox
                    checked={allPageSelected ? true : somePageSelected ? 'indeterminate' : false}
                    onCheckedChange={(checked) => {
                      const ids = new Set(pagedUserIds)
                      if (checked === true) {
                        setSelectedIds((prev) => {
                          const next = new Set(prev)
                          for (const id of ids) next.add(id)
                          return [...next]
                        })
                      } else {
                        setSelectedIds((prev) => prev.filter((id) => !ids.has(id)))
                      }
                    }}
                    aria-label="Выбрать всех на странице"
                  />
                  Выбрать всех на странице ({pagedUserIds.length})
                </label>
              ) : null}
            </div>
          </div>

          {provisioningOn && filter !== 'deleting' && (
            <UsersBulkBar
              selectedCount={selectedIds.length}
              busy={
                backgroundTask?.task_type === 'bulk_user_nodes' &&
                ['queued', 'running'].includes(backgroundTask.status)
              }
              task={backgroundTask?.task_type === 'bulk_user_nodes' ? backgroundTask : null}
              onAction={(action) => setBulkDialog({ open: true, action })}
              onDownloadReport={(taskId) => void handleDownloadReport(taskId)}
              onBulkAction={() => setBulkActionOpen(true)}
            />
          )}

          {filteredUsers.length === 0 ? (
            <EmptyState
              icon={Users}
              title="Пока нет пользователей"
              description={
                filter === 'deleting'
                  ? 'Нет абонентов, ожидающих удаления.'
                  : search || filter !== 'all'
                    ? 'Измените фильтр или поисковый запрос'
                    : provisioningOn
                      ? 'Создайте первого абонента — панель сама выпустит конфиги на выбранных серверах.'
                      : 'Включите модуль «Пользователи (абоненты)» в настройках разделов, чтобы управлять абонентами VPN.'
              }
              className="py-10"
              action={
                provisioningOn && !search && filter === 'all' ? (
                  <Button
                    type="button"
                    onClick={() => setCreateOpen(true)}
                    aria-label="Создать первого пользователя"
                  >
                    <UserPlus size={15} />
                    Создать пользователя
                  </Button>
                ) : null
              }
            />
          ) : (
            <div className={cn('grid gap-3', gridColsClass(viewPrefs.gridCols))}>
              {pagedUsers.map((u) => (
                <SubscriberCard
                  key={u.id}
                  user={u}
                  selected={selectedIds.includes(u.id)}
                  showSelect={provisioningOn}
                  viewPrefs={viewPrefs}
                  actionBusy={cardBusyId === u.id}
                  onSuspend={() => setSuspendTarget(u)}
                  onResume={() => void handleResume(u)}
                  onDelete={() => void handleDeleteUser(u)}
                  onSelectChange={(checked) =>
                    setSelectedIds((prev) =>
                      checked ? [...prev, u.id] : prev.filter((id) => id !== u.id),
                    )
                  }
                  onOpen={() => openDetail(u.id)}
                  onExtend={handleExtend}
                  onResetTraffic={
                    u.traffic_limit_bytes && u.traffic_limit_bytes > 0
                      ? () => void handleResetTraffic(u)
                      : undefined
                  }
                  onCreateKey={
                    isEnabled('unlock_codes') ? () => setUnlockDialogUser(u) : undefined
                  }
                  onRetryDelete={
                    u.provision_state === 'pending_deletion'
                      ? () => void handleRetryDelete(u)
                      : undefined
                  }
                />
              ))}
            </div>
          )}
          {filteredUsers.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <span>На странице</span>
                <select
                  value={pageSize}
                  onChange={(e) => setPageSize(Number.parseInt(e.target.value, 10))}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                  aria-label="Размер страницы"
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={safePage <= 0}
                >
                  ‹
                </Button>
                <span>
                  {safePage + 1} / {totalPages}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={safePage >= totalPages - 1}
                >
                  ›
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </div>

      <AppDialog
        open={detailId != null}
        onOpenChange={(open) => {
          if (!open) closeDetail()
        }}
        title="Профиль абонента"
        description="Доступ, конфиги и учётная запись"
        icon={UserRound}
        size="xl"
        bodyClassName="px-0 py-0"
      >
        {detailId != null ? (
          <UserCardView
            key={detailId}
            userId={detailId}
            onBack={closeDetail}
            onSave={(id, data, message) => void handleSaveUser(id, data, message)}
            onDelete={(user) => void handleDeleteUser(user, { skipConfirm: true })}
          />
        ) : null}
      </AppDialog>

      {createOpen ? (
        <CreateUserDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          adminUserId={authUser?.id}
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

      {provisioningOn && (
        <BulkUsersActionDialog
          open={bulkActionOpen}
          onOpenChange={setBulkActionOpen}
          userIds={bulkTargetIds}
          onDone={() => {
            void reloadUsers()
            setSelectedIds([])
          }}
        />
      )}

      {suspendTarget && (
        <SuspendUserDialog
          open
          onOpenChange={(open) => {
            if (!open) setSuspendTarget(null)
          }}
          username={suspendTarget.username}
          busy={cardBusyId === suspendTarget.id}
          onConfirm={(data) => void handleSuspend(suspendTarget, data)}
        />
      )}


      {unlockDialogUser && (
        <UnlockCodeCreateDialog
          open={unlockDialogUser != null}
          onOpenChange={(open) => {
            if (!open) setUnlockDialogUser(null)
          }}
          availableProtocols={unlockProtocols}
          initialProtocols={unlockProtocols}
          boundUser={{ id: unlockDialogUser.id, username: unlockDialogUser.username }}
          telegramBound={Boolean(unlockDialogUser.telegram_id)}
          targetUserId={unlockDialogUser.id}
          onCreated={() => void reloadUsers()}
        />
      )}

      {provisioningOn && (
        <AccessRequestsDialog
          open={requestsOpen}
          onOpenChange={(open) => {
            setRequestsOpen(open)
            if (!open) setFocusRequestId(null)
          }}
          focusRequestId={focusRequestId}
          onCountChange={handleRequestsCount}
          onUsersChanged={handleUsersChanged}
        />
      )}
    </div>
  )
}

/** Карточка абонента внутри диалога (маршрут /users/:id). */
function UserCardView({
  userId,
  onBack,
  onSave,
  onDelete,
}: {
  userId: number
  onBack: () => void
  onSave: (id: number, data: Partial<UserUpdatePayload>, message?: string) => void
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
    setCard(null)
    void (async () => {
      try {
        const data = await getProvisioning(userId)
        if (!cancelled) setCard(data)
      } catch (err) {
        if (!cancelled) {
          notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку')
          onBack()
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [userId, notifyError, onBack])

  const provisionState = card?.user.provision_state

  useEffect(() => {
    if (provisionState !== 'pending') return

    const timer = window.setInterval(() => {
      void load()
    }, 1500)
    return () => window.clearInterval(timer)
  }, [provisionState, load])

  if (loading) return <Spinner label="Загрузка карточки…" className="py-16" />
  if (!card) return null

  return (
    <UserCard
      card={card}
      onSave={onSave}
      onDelete={onDelete}
      onRefresh={() => void load()}
    />
  )
}
