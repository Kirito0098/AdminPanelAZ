import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import {
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
import {
  ApiError,
  deleteUser,
  getUsers,
  updateUser,
} from '@/api/client'
import { getNodes } from '@/api/nodes'
import {
  createProvisionedUser,
  createUserFromExisting,
  deleteProvisionedUser,
  downloadBulkNodesReport,
  extendUserAccess,
  getProvisioning,
  getRequestReceipt,
  listPresets,
  listRequests,
  approveRequest,
  rejectRequest,
  resumeUser,
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
import { Label } from '@/components/ui/label'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotificationCenter } from '@/context/NotificationCenterContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { DOCS } from '@/lib/docsUrls'
import { gridColsClass } from '@/lib/configCardViewPrefs'
import { triggerFileDownload } from '@/lib/triggerFileDownload'
import { cn } from '@/lib/utils'
import {
  loadUsersCardViewPrefs,
  saveUsersCardViewPrefs,
  type UsersCardViewPrefs,
} from '@/lib/usersCardViewPrefs'
import { loadUsersListPrefs, saveUsersListPrefs, type UsersSortKey } from '@/lib/usersListPrefs'
import type {
  AccessRequestResponse,
  Node,
  PresetResponse,
  User,
  UserUpdatePayload,
  UserProvisioningCard,
  UserProvisionSummary,
  BulkNodesAction,
} from '@/types'

const REQUEST_PROTOCOLS: { id: string; label: string; featureKeys: string[] }[] = [
  { id: 'wireguard', label: 'WireGuard', featureKeys: ['wireguard', 'amneziawg'] },
  { id: 'openvpn', label: 'OpenVPN', featureKeys: ['openvpn'] },
  { id: 'amneziawg2', label: 'AmneziaWG 2.0', featureKeys: ['awg2'] },
]
import { USERS_FILTER_IDS, UsersFilters } from '@/components/users/UsersFilters'
import UsersCardViewSettings from '@/components/users/UsersCardViewSettings'
import CreateUserDialog, {
  type CreateUserPayload,
} from '@/components/users/CreateUserDialog'
import BulkNodesDialog from '@/components/users/BulkNodesDialog'
import BulkUsersActionDialog from '@/components/users/BulkUsersActionDialog'
import UnlockCodeCreateDialog from '@/components/dashboard/UnlockCodeCreateDialog'
import SuspendUserDialog, { type SuspendUserPayload } from '@/components/users/SuspendUserDialog'
import UsersBulkBar from '@/components/users/UsersBulkBar'
import SubscriberCard from '@/components/users/SubscriberCard'
import UserCard from '@/components/users/UserCard'

const REQUEST_TYPE_LABELS: Record<string, string> = {
  new_user: 'Новый пользователь',
  add_config: 'Дополнительный конфиг',
  extend_access: 'Продление доступа',
}

type SortKey = UsersSortKey

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'username', label: 'Имя' },
  { value: 'created_at', label: 'Дата создания' },
  { value: 'access_until', label: 'Срок доступа' },
  { value: 'traffic', label: 'Трафик' },
  { value: 'last_seen', label: 'Активность' },
]

const PAGE_SIZE_OPTIONS = [20, 50, 100] as const
const PAGE_SIZE_STORAGE_KEY = 'users-cards:pageSize'

function loadPageSize(): number {
  try {
    const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE_KEY)
    const n = raw ? Number.parseInt(raw, 10) : NaN
    return (PAGE_SIZE_OPTIONS as readonly number[]).includes(n) ? n : 20
  } catch {
    return 20
  }
}

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
  const { pendingRequestsCount } = useNotificationCenter()
  const { backgroundTask, trackBackgroundTask } = useProgress()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [initialListPrefs] = useState(() => loadUsersListPrefs(USERS_FILTER_IDS))
  const [filter, setFilter] = useState<string>(initialListPrefs.filter)
  const [search, setSearch] = useState('')
  // Фильтрация идёт по отложенному значению: поле ввода остаётся мгновенным,
  // а пересчёт списка не блокирует ввод на сотнях карточек.
  const deferredSearch = useDeferredValue(search)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [requestsOpen, setRequestsOpen] = useState(false)
  // Превью чека заявки: blob-URL живёт до закрытия диалога.
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null)
  const [requests, setRequests] = useState<AccessRequestResponse[]>([])
  const [requestsLoading, setRequestsLoading] = useState(false)
  const [focusRequestId, setFocusRequestId] = useState<number | null>(null)
  /** Уже обработанный deep-link (?requests=1 / ?request=<id>), чтобы не открывать диалог циклично. */
  const consumedRequestsParamRef = useRef<string | null>(null)
  const [requestPresets, setRequestPresets] = useState<PresetResponse[]>([])
  const [requestNodes, setRequestNodes] = useState<Node[]>([])
  const [approvePresetId, setApprovePresetId] = useState<number | null>(null)
  const [approveNodeIds, setApproveNodeIds] = useState<number[]>([])
  const [approveProtocols, setApproveProtocols] = useState<string[]>([])
  const [approveUsername, setApproveUsername] = useState('')
  const [approveAccessDays, setApproveAccessDays] = useState('')
  const [approvingId, setApprovingId] = useState<number | null>(null)
  const [bulkDialog, setBulkDialog] = useState<{
    open: boolean
    action: BulkNodesAction
    presetNodeId?: number
  }>({ open: false, action: 'add' })
  const [viewPrefs, setViewPrefs] = useState<UsersCardViewPrefs>(() => loadUsersCardViewPrefs())
  const [cardBusyId, setCardBusyId] = useState<number | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>(initialListPrefs.sortKey)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(initialListPrefs.sortDir)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState<number>(() => loadPageSize())
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
  const hasNewUserRequests = requests.some((r) => r.request_type === 'new_user')
  const canApproveNewUser =
    approvePresetId != null ||
    (approveNodeIds.length > 0 && approveProtocols.length > 0)

  const reloadUsers = useCallback(async () => {
    try {
      const list = await getUsers({ includeDeleting: true })
      setUsers(list)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось загрузить пользователей')
    }
  }, [notifyError])

  const reloadRequests = useCallback(async () => {
    if (!provisioningOn) return
    setRequestsLoading(true)
    try {
      const list = await listRequests({ status: 'pending' })
      setRequests(list)
    } catch {
      /* вложенная опциональна */
    } finally {
      setRequestsLoading(false)
    }
  }, [provisioningOn])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const list = await getUsers({ includeDeleting: true })
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

  // Список заявок перечитываем при каждом изменении pending-счётчика из SSE:
  // новая заявка из Telegram появляется в диалоге без перезагрузки страницы.
  useEffect(() => {
    void reloadRequests()
  }, [reloadRequests, pendingRequestsCount])

  // Смена фильтра сбрасывает выбор и страницу — иначе в область попадут скрытые пользователи.
  useEffect(() => {
    setSelectedIds([])
    setPage(0)
  }, [filter, search])

  // Фильтр и сортировку запоминаем между заходами; поиск — нет (временный запрос).
  useEffect(() => {
    saveUsersListPrefs({ filter, sortKey, sortDir })
  }, [filter, sortKey, sortDir])

  // Смена сортировки/размера страницы тоже возвращает на первую страницу; размер запоминаем.
  useEffect(() => {
    setPage(0)
  }, [sortKey, sortDir, pageSize])

  useEffect(() => {
    try {
      window.localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(pageSize))
    } catch {
      /* ignore quota / private mode */
    }
  }, [pageSize])

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
    void reloadRequests()
    const next = new URLSearchParams(searchParams)
    next.delete('requests')
    next.delete('request')
    setSearchParams(next, { replace: true })
  }, [provisioningOn, searchParams, setSearchParams, reloadRequests])

  // Открытие диалога всегда сопровождается свежим запросом списка.
  useEffect(() => {
    if (!requestsOpen) return
    void reloadRequests()
  }, [requestsOpen, reloadRequests])

  // Подсветить и подскроллить заявку, к которой вела ссылка из Telegram.
  useEffect(() => {
    if (!requestsOpen || focusRequestId == null) return
    document
      .getElementById(`access-request-${focusRequestId}`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [requestsOpen, focusRequestId, requests])

  // План для одобрения new_user: шаблон или узлы+протоколы.
  useEffect(() => {
    if (!requestsOpen || !provisioningOn) return
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
  }, [requestsOpen, provisioningOn, availableRequestProtocols])

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
      const list = await getUsers({ includeDeleting: true })
      setUsers(list)
      await reloadRequests()
      const userRow = telegramId
        ? list.find((u) => u.telegram_id === telegramId)
        : undefined
      if (userRow?.active_task_id) {
        trackBackgroundTask(userRow.active_task_id, {
          onComplete: () => {
            void reloadUsers()
            success('Конфиги для заявки применены')
          },
          onError: (_task, message) => notifyError(message),
        })
      } else {
        window.setTimeout(() => {
          void reloadUsers()
        }, 2500)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка одобрения')
      // Решение не принято: перечитываем список, чтобы заявка осталась на экране.
      await reloadRequests()
    } finally {
      setApprovingId(null)
    }
  }

  const handleRejectRequest = async (requestId: number) => {
    try {
      await rejectRequest(requestId, { ban: false })
      success('Заявка отклонена')
      await reloadRequests()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка отказа')
    }
  }

  const filteredUsers = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase()
    let list = users.filter((u) => {
      if (!q) return true
      const hay = [
        u.username,
        String(u.id),
        u.telegram_id ?? '',
        u.client_base_name ?? '',
        u.owned_config_base_name ?? '',
        u.note ?? '',
      ]
        .join('\u0000')
        .toLowerCase()
      return hay.includes(q)
    })
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    const weekLater = new Date(now)
    weekLater.setDate(weekLater.getDate() + 7)
    // «Удаляется» — отдельный список: обычные фильтры удаляемых не показывают.
    const deleting = filter === 'deleting'
    list = list.filter((u) => (u.provision_state === 'pending_deletion') === deleting)
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
    const dir = sortDir === 'asc' ? 1 : -1
    return list.sort((a, b) => {
      if (sortKey === 'traffic') {
        return dir * ((a.traffic_consumed_bytes ?? 0) - (b.traffic_consumed_bytes ?? 0))
      }
      const field =
        sortKey === 'last_seen'
          ? 'last_seen_at'
          : (sortKey as 'username' | 'created_at' | 'access_until')
      const av = a[field] ?? ''
      const bv = b[field] ?? ''
      return dir * String(av).localeCompare(String(bv), 'ru')
    })
  }, [users, filter, deferredSearch, sortKey, sortDir])

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / pageSize))
  const safePage = Math.min(page, totalPages - 1)
  const pagedUsers = filteredUsers.slice(safePage * pageSize, (safePage + 1) * pageSize)

  // Массовые действия: выбранные галочками, иначе — весь отфильтрованный список.
  const bulkTargetIds = selectedIds.length > 0 ? selectedIds : filteredUsers.map((u) => u.id)

  // «Выбрать всех на странице»: состояние чекбокса по текущей странице пагинации.
  const pagedUserIds = pagedUsers.map((u) => u.id)
  const selectedOnPage = pagedUserIds.filter((id) => selectedIds.includes(id)).length
  const allPageSelected = pagedUserIds.length > 0 && selectedOnPage === pagedUserIds.length
  const somePageSelected = selectedOnPage > 0 && !allPageSelected

  const listMetrics = useMemo(() => {
    const now = Date.now()
    const week = now + 7 * 86400000
    let withPlan = 0
    let expiringOrExpired = 0
    let suspended = 0
    for (const u of users) {
      if (u.client_base_name && u.provision_state && u.provision_state !== 'unmanaged') withPlan += 1
      if (u.suspended_at) suspended += 1
      if (u.access_until) {
        const t = new Date(u.access_until).getTime()
        if (t < now || t <= week) expiringOrExpired += 1
      }
    }
    return {
      total: users.length,
      withPlan,
      expiringOrExpired,
      suspended,
    }
  }, [users])
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

  const handleOpenReceipt = async (requestId: number) => {
    try {
      const blob = await getRequestReceipt(requestId)
      setReceiptUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(blob)
      })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Не удалось открыть чек')
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
                label={requests.length > 0 ? `Заявки (${requests.length})` : 'Заявки'}
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

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Всего"
          value={String(listMetrics.total)}
          sub={`${filteredUsers.length} на экране`}
          icon={Users}
          accent="cyan"
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
                <UsersFilters filter={filter} onFilterChange={setFilter} />
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

      {receiptUrl && (
        <AppDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              URL.revokeObjectURL(receiptUrl)
              setReceiptUrl(null)
            }
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
        <AppDialog
          open={requestsOpen}
          onOpenChange={(open) => {
            setRequestsOpen(open)
            if (!open) setFocusRequestId(null)
          }}
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
                          onClick={() => void handleApproveRequest(r.id, r.request_type)}
                          disabled={approveDisabled}
                        >
                          {approvingId === r.id ? '…' : 'Одобрить'}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="destructive"
                          onClick={() => void handleRejectRequest(r.id)}
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
