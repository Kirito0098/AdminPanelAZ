import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  Copy,
  Globe,
  GitCompare,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Wand2,
} from 'lucide-react'
import {
  ApiError,
  applyNodeSyncGroupSharedDomain,
  createNodeSyncGroup,
  deleteNodeSyncGroup,
  getNodeSyncGroups,
  setupNodeSyncGroup,
  updateNodeSyncGroup,
  verifyNodeSyncGroup,
} from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import { HA_PRIMARY, HA_PUSH_FULL, HA_REPLICA, nodeStatusRu } from '@/lib/uiLabels'
import HaSyncResultDialog from '@/components/nodes/HaSyncResultDialog'
import HaVerifyResultDialog from '@/components/nodes/HaVerifyResultDialog'
import { parseHaSyncTaskResult, type HaSyncResultView } from '@/lib/haSyncSummary'
import { parseHaVerifyResult, type HaVerifyResultView } from '@/lib/haVerifySummary'
import { useBackgroundTaskPoll } from '@/hooks/useBackgroundTaskPoll'
import type { BackgroundTask, Node, NodeSyncGroup, NodeSyncVerifyResult, SyncStatus } from '@/types'

type NodeSyncGroupSectionProps = {
  nodes: Node[]
  onGroupsChanged?: (groups: NodeSyncGroup[]) => void
}

const AUTO_SYNC_POLL_MS = 30_000

/** Target auto-sync scope (roadmap §3). */
const AUTO_SYNC_OPERATIONS = [
  'Создание / удаление VPN-клиентов (копия WG conf + профилей и PKI OVPN с основного; shadow VpnConfig в режиме auto)',
  'Продление сертификата, блокировки (временные/постоянные), разблокировка, лимиты трафика, срок WG',
  'Отключение OpenVPN, метаданные клиента (описание, владелец)',
  'Массовая блокировка / продление / разблокировка, импорт CSV, шаблоны клиентов',
  'Файлы конфигурации AntiZapret: настройки (списки), редактор, файлы маршрутизации + doall',
  'Настройки setup (PUT antizapret-settings) и применение маршрутизации',
  'CIDR-провайдеры: правки файлов, сборка и развёртывание на реплику',
  'Политика узла по умолчанию (редактирование только на основном узле)',
] as const

function formatTimestamp(value?: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString()
}

type ReadinessBadge = { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }

function verifyBadge(group: NodeSyncGroup): ReadinessBadge {
  if (group.ready === true) return { label: 'Verify: готово', variant: 'default' }
  if (group.ready === false) return { label: 'Verify: расхождения', variant: 'destructive' }
  return { label: 'Verify: не проверено', variant: 'outline' }
}

function replicationBadge(group: NodeSyncGroup): ReadinessBadge {
  if (group.sync_status === 'pending') return { label: 'Репликация…', variant: 'secondary' }
  if (group.sync_status === 'failed') return { label: 'Репликация: ошибка', variant: 'destructive' }
  if (group.sync_status === 'synced') return { label: 'Репликация: OK', variant: 'default' }
  return { label: 'Репликация: —', variant: 'outline' }
}

function SyncGroupStatusBlock({
  group,
  onOpenVerifyReport,
}: {
  group: NodeSyncGroup
  onOpenVerifyReport: () => void
}) {
  const verify = verifyBadge(group)
  const replication = replicationBadge(group)

  return (
    <div>
      <div className="flex flex-wrap gap-1">
        <Badge variant={verify.variant}>{verify.label}</Badge>
        <Badge variant={replication.variant}>{replication.label}</Badge>
      </div>
      {(group.warnings ?? []).map((item) => (
        <p key={item} className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          {item}
        </p>
      ))}
      {formatTimestamp(group.last_sync_at) ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Синхронизация: {formatTimestamp(group.last_sync_at)}
        </p>
      ) : null}
      {formatTimestamp(group.last_verify_at) ? (
        <p className="text-xs text-muted-foreground">Проверка: {formatTimestamp(group.last_verify_at)}</p>
      ) : null}
      {group.last_verify_result ? (
        <button
          type="button"
          onClick={onOpenVerifyReport}
          className="mt-1 text-xs text-primary hover:underline"
        >
          Отчёт проверки
        </button>
      ) : null}
      {group.last_sync_error ? (
        <p className="mt-1 text-xs text-destructive">{group.last_sync_error}</p>
      ) : null}
    </div>
  )
}

type SyncGroupActionsProps = {
  group: NodeSyncGroup
  actionLoading: number | null
  compact?: boolean
  onSetup: () => void
  onDomain: () => void
  onVerify: () => void
  onEdit: () => void
  onDelete: () => void
}

function SyncGroupActions({
  group,
  actionLoading,
  compact = false,
  onSetup,
  onDomain,
  onVerify,
  onEdit,
  onDelete,
}: SyncGroupActionsProps) {
  const syncBusy = actionLoading === group.id || group.sync_status === 'pending'
  const actionBusy = actionLoading === group.id

  if (compact) {
    return (
      <div className="flex flex-wrap gap-1">
        <Button
          size="sm"
          disabled={syncBusy}
          onClick={onSetup}
          title="Домен → полная копия на реплику → проверка (полный цикл)"
        >
          {actionBusy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
          Синхронизировать
        </Button>
        <Button variant="outline" size="sm" disabled={actionBusy} onClick={onVerify}>
          <ShieldCheck size={14} />
          Проверить
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={actionBusy}>
              <MoreHorizontal size={14} />
              Ещё
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem disabled={syncBusy} onClick={onDomain}>
              <Globe size={14} />
              Домен
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={actionBusy} onClick={onEdit}>
              Изменить
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              disabled={actionBusy}
              onClick={onDelete}
            >
              <Trash2 size={14} />
              Расформировать
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap justify-end gap-1">
      <Button
        size="sm"
        disabled={syncBusy}
        onClick={onSetup}
        title="Домен → полная копия на реплику → проверка (полный цикл)"
      >
        {actionBusy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
        Синхронизировать
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={syncBusy}
        onClick={onDomain}
        title="Только shared domain → setup + doall + client.sh 7"
      >
        <Globe size={14} />
        Домен
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={actionBusy}
        onClick={onVerify}
        title="Только проверить расхождения между основным узлом и репликой (без изменений)"
      >
        <ShieldCheck size={14} />
        Проверить
      </Button>
      <Button variant="ghost" size="sm" disabled={actionBusy} onClick={onEdit}>
        Изменить
      </Button>
      <Button variant="ghost" size="sm" disabled={actionBusy} onClick={onDelete}>
        <Trash2 size={14} />
      </Button>
    </div>
  )
}

function SyncGroupCard({
  group,
  actionLoading,
  onDns,
  onOpenVerifyReport,
  onSetup,
  onDomain,
  onVerify,
  onEdit,
  onDelete,
}: {
  group: NodeSyncGroup
  actionLoading: number | null
  onDns: () => void
  onOpenVerifyReport: () => void
  onSetup: () => void
  onDomain: () => void
  onVerify: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <Card className="p-4">
      <div className="font-medium">{group.name}</div>
      {group.sync_mode === 'manual_full' ? (
        <p className="mt-1 text-xs text-muted-foreground">
          После расформирования группы на реплике выполните Конфигурации → Синхронизировать.
        </p>
      ) : group.sync_mode === 'auto' ? (
        <p className="mt-1 text-xs text-muted-foreground">
          Авто: правки с основного на реплику (см. режим синхронизации при редактировании).
        </p>
      ) : null}
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted-foreground">Домен</dt>
          <dd className="mt-0.5">
            <div>{group.shared_domain}</div>
            <button
              type="button"
              onClick={onDns}
              className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <Globe size={12} />
              Настройка DNS
            </button>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">{HA_PRIMARY}</dt>
          <dd className="mt-0.5">{group.primary_node_name ?? group.primary_node_id}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs text-muted-foreground">{HA_REPLICA}</dt>
          <dd className="mt-0.5">
            {(group.replica_node_names?.length ? group.replica_node_names : group.replica_node_ids).join(', ')}
          </dd>
        </div>
      </dl>
      <div className="mt-3">
        <SyncGroupStatusBlock group={group} onOpenVerifyReport={onOpenVerifyReport} />
      </div>
      <div className="mt-3">
        <SyncGroupActions
          group={group}
          actionLoading={actionLoading}
          compact
          onSetup={onSetup}
          onDomain={onDomain}
          onVerify={onVerify}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      </div>
    </Card>
  )
}

function AutoSyncModeDescription({ compact = false }: { compact?: boolean }) {
  const [expanded, setExpanded] = useState(false)

  if (compact && !expanded) {
    return (
      <p className="text-xs text-muted-foreground">
        Правки на основном узле автоматически реплицируются на реплику (клиенты, конфиги, маршрутизация, CIDR).{' '}
        <button
          type="button"
          className="text-primary underline-offset-2 hover:underline"
          onClick={() => setExpanded(true)}
        >
          Подробнее
        </button>
      </p>
    )
  }

  return (
    <SettingsAlert variant="info" className={compact ? 'p-3' : undefined}>
      <p className="font-medium">Авто: операции на основном узле автоматически реплицируются на реплику.</p>
      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">
        {AUTO_SYNC_OPERATIONS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Не синхронизируются: warper-include-ips.txt (локально на узле; это AZ-WARP, не флаги
        ANTIZAPRET_WARP / VPN_WARP из «Конфиг AntiZapret» — они синхронизируются).
        {HA_PUSH_FULL} — первичное выравнивание и восстановление после рассинхрона.
      </p>
      {compact ? (
        <button
          type="button"
          className="mt-2 text-xs text-primary underline-offset-2 hover:underline"
          onClick={() => setExpanded(false)}
        >
          Свернуть
        </button>
      ) : null}
    </SettingsAlert>
  )
}

export default function NodeSyncGroupSection({ nodes, onGroupsChanged }: NodeSyncGroupSectionProps) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const { task, polling, startPoll } = useBackgroundTaskPoll()
  const [groups, setGroups] = useState<NodeSyncGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<NodeSyncGroup | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [verifyDialogView, setVerifyDialogView] = useState<HaVerifyResultView | null>(null)
  const [verifyDialogOpen, setVerifyDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<NodeSyncGroup | null>(null)
  const [setupTarget, setSetupTarget] = useState<NodeSyncGroup | null>(null)
  const [domainApplyTarget, setDomainApplyTarget] = useState<NodeSyncGroup | null>(null)
  const [setupStage, setSetupStage] = useState<string | null>(null)
  const [dnsTarget, setDnsTarget] = useState<NodeSyncGroup | null>(null)
  const [copiedHost, setCopiedHost] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [syncResult, setSyncResult] = useState<HaSyncResultView | null>(null)
  const [syncResultOpen, setSyncResultOpen] = useState(false)

  const [name, setName] = useState('')
  const [sharedDomain, setSharedDomain] = useState('')
  const [primaryId, setPrimaryId] = useState<string>('')
  const [replicaIds, setReplicaIds] = useState<number[]>([])
  const [syncMode, setSyncMode] = useState('manual_full')
  const [autoSetup, setAutoSetup] = useState(true)

  const onlineNodes = useMemo(() => nodes.filter((n) => n.status === 'online'), [nodes])
  const prevSyncStatusRef = useRef<Map<number, SyncStatus>>(new Map())
  const notifiedReplicationRef = useRef<Set<string>>(new Set())
  const resumedTaskIdsRef = useRef<Set<string>>(new Set())

  const clearGroupReplicationNotices = (groupId: number) => {
    for (const key of notifiedReplicationRef.current) {
      if (key.startsWith(`warn:${groupId}:`) || key.startsWith(`failed:${groupId}:`)) {
        notifiedReplicationRef.current.delete(key)
      }
    }
  }

  const reportReplicationIssues = useCallback(
    (nextGroups: NodeSyncGroup[]) => {
      for (const group of nextGroups) {
        if (group.sync_mode !== 'auto') continue

        for (const item of group.warnings ?? []) {
          const key = `warn:${group.id}:${item}`
          if (notifiedReplicationRef.current.has(key)) continue
          notifyWarning(`«${group.name}»: ${item}`)
          notifiedReplicationRef.current.add(key)
        }

        const prevStatus = prevSyncStatusRef.current.get(group.id)
        const becameFailed =
          group.sync_status === 'failed' && prevStatus !== undefined && prevStatus !== 'failed'
        const errorText = group.last_sync_error?.trim()

        if (becameFailed && errorText) {
          const key = `failed:${group.id}:${errorText}`
          if (!notifiedReplicationRef.current.has(key)) {
            notifyWarning(`Репликация «${group.name}»: ${errorText}`)
            notifiedReplicationRef.current.add(key)
          }
        }

        if (group.sync_status === 'synced') {
          clearGroupReplicationNotices(group.id)
        }

        prevSyncStatusRef.current.set(group.id, group.sync_status)
      }
    },
    [notifyWarning],
  )

  const fetchGroups = useCallback(async () => getNodeSyncGroups(), [])

  const applyGroups = useCallback(
    (nextGroups: NodeSyncGroup[]) => {
      reportReplicationIssues(nextGroups)
      setGroups(nextGroups)
      onGroupsChanged?.(nextGroups)
    },
    [onGroupsChanged, reportReplicationIssues],
  )

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      applyGroups(await fetchGroups())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки групп синхронизации')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [applyGroups, fetchGroups, notifyError])

  const pollAutoGroups = useCallback(async () => {
    try {
      applyGroups(await fetchGroups())
    } catch {
      // Background poll: errors surface on next manual refresh.
    }
  }, [applyGroups, fetchGroups])

  useEffect(() => {
    if (nodes.length < 2) {
      setLoading(false)
      return
    }
    void load()
  }, [load, nodes.length])

  const hasAutoGroups = useMemo(() => groups.some((g) => g.sync_mode === 'auto'), [groups])

  useEffect(() => {
    if (!hasAutoGroups || nodes.length < 2) return

    const poll = () => {
      if (document.visibilityState !== 'visible') return
      void pollAutoGroups()
    }

    const interval = window.setInterval(poll, AUTO_SYNC_POLL_MS)
    return () => window.clearInterval(interval)
  }, [hasAutoGroups, nodes.length, pollAutoGroups])

  const openCreate = () => {
    setEditing(null)
    setName('')
    setSharedDomain('')
    setPrimaryId(onlineNodes[0] ? String(onlineNodes[0].id) : '')
    setReplicaIds([])
    setSyncMode('manual_full')
    setAutoSetup(true)
    setDialogOpen(true)
  }

  const openEdit = (group: NodeSyncGroup) => {
    setEditing(group)
    setName(group.name)
    setSharedDomain(group.shared_domain)
    setPrimaryId(String(group.primary_node_id))
    setReplicaIds(group.replica_node_ids)
    setSyncMode(group.sync_mode || 'manual_full')
    setAutoSetup(true)
    setDialogOpen(true)
  }

  const toggleReplica = (nodeId: number) => {
    setReplicaIds((prev) =>
      prev.includes(nodeId) ? prev.filter((id) => id !== nodeId) : [...prev, nodeId],
    )
  }

  const showVerifyResult = useCallback((group: NodeSyncGroup, result: NodeSyncVerifyResult) => {
    setVerifyDialogView(parseHaVerifyResult(result, group.name, group.sync_mode))
    setVerifyDialogOpen(true)
  }, [])

  const patchGroupVerify = useCallback((groupId: number, result: NodeSyncVerifyResult) => {
    setGroups((prev) =>
      prev.map((group) =>
        group.id === groupId
          ? {
              ...group,
              ready: result.ready,
              last_verify_result: result,
              last_verify_at: new Date().toISOString(),
            }
          : group,
      ),
    )
  }, [])

  const showSyncResult = useCallback((task: BackgroundTask, verifyReady?: boolean | null) => {
    const result = parseHaSyncTaskResult(task)
    if (!result) return

    const withVerify =
      verifyReady === false
        ? {
            ...result,
            variant: 'warning' as const,
            description: result.description
              ? `${result.description}. Проверка нашла расхождения — см. «Проверить».`
              : 'Проверка нашла расхождения — см. «Проверить».',
          }
        : result

    setSyncResult(withVerify)
    setSyncResultOpen(true)
  }, [])

  useEffect(() => {
    if (loading || polling) return
    for (const group of groups) {
      const taskId = group.last_sync_task_id
      if (group.sync_status !== 'pending' || !taskId) continue
      if (resumedTaskIdsRef.current.has(taskId)) continue
      resumedTaskIdsRef.current.add(taskId)
      setSetupStage(`Возобновление синхронизации «${group.name}»…`)
      startPoll(taskId, {
        onComplete: (task) => {
          void load()
          showSyncResult(task)
          setSetupStage(null)
        },
        onError: () => {
          void load()
          setSetupStage(null)
        },
      })
      break
    }
  }, [groups, loading, load, polling, showSyncResult, startPoll])

  /** Wrap the callback-based background poll in a promise so steps can be chained. */
  const pollToCompletion = useCallback(
    (taskId: string) =>
      new Promise<BackgroundTask>((resolve, reject) => {
        startPoll(taskId, {
          onComplete: (task) => resolve(task),
          onError: (_task, message) => reject(new Error(message || 'Задача завершилась с ошибкой')),
        })
      }),
    [startPoll],
  )

  /**
   * One-click HA setup via a single backend task: shared domain → full push → verify.
   * Running it server-side (instead of chaining requests here) means the bring-up
   * survives the admin closing the browser and shows one honest progress bar.
   */
  const runHaSetup = useCallback(
    async (group: NodeSyncGroup) => {
      setActionLoading(group.id)
      setSetupStage(`Синхронизация «${group.name}»: домен → копия на реплику → OpenVPN → проверка…`)
      try {
        const accepted = await setupNodeSyncGroup(group.id)
        const task = await pollToCompletion(accepted.task_id)

        const fresh = await fetchGroups()
        applyGroups(fresh)
        const updated = fresh.find((g) => g.id === group.id)
        if (updated?.last_verify_result && updated.ready === false) {
          showVerifyResult(group, updated.last_verify_result)
        }
        showSyncResult(task, updated?.ready)
        if (updated?.ready) {
          success('HA-группа синхронизирована и готова к DNS-переключению')
        } else {
          notifyWarning('Синхронизация завершена с расхождениями — см. отчёт')
        }
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка синхронизации HA-группы')
        await load()
      } finally {
        setSetupStage(null)
        setActionLoading(null)
      }
    },
    [applyGroups, fetchGroups, load, notifyError, notifyWarning, pollToCompletion, showSyncResult, showVerifyResult, success],
  )

  /** Non-destructive: re-apply the shared domain to all members (used after edits). */
  const runDomainApply = useCallback(
    async (group: NodeSyncGroup) => {
      setActionLoading(group.id)
      setSetupStage(`Применение домена ${group.shared_domain} на узлах (doall.sh + client.sh 7 + OpenVPN)…`)
      try {
        const accepted = await applyNodeSyncGroupSharedDomain(group.id)
        const task = await pollToCompletion(accepted.task_id)
        showSyncResult(task)
        success(`Домен ${group.shared_domain} применён на узлах`)
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка применения домена')
      } finally {
        setSetupStage(null)
        setActionLoading(null)
        await load()
      }
    },
    [load, notifyError, pollToCompletion, showSyncResult, success],
  )

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const primary = Number(primaryId)
    if (!name.trim() || !sharedDomain.trim() || !primary || replicaIds.length === 0) {
      notifyError('Заполните имя, домен, основной узел и хотя бы одну реплику')
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        name: name.trim(),
        shared_domain: sharedDomain.trim(),
        primary_node_id: primary,
        replica_node_ids: replicaIds,
        sync_mode: syncMode,
      }
      const sortedIds = (ids: number[]) => [...ids].sort((a, b) => a - b)
      const membersChanged =
        editing != null &&
        (editing.primary_node_id !== payload.primary_node_id ||
          JSON.stringify(sortedIds(editing.replica_node_ids)) !==
            JSON.stringify(sortedIds(payload.replica_node_ids)))
      const domainChanged = editing != null && editing.shared_domain.trim() !== payload.shared_domain

      let savedGroup: NodeSyncGroup
      if (editing) {
        savedGroup = await updateNodeSyncGroup(editing.id, payload)
        success('Группа синхронизации обновлена')
      } else {
        savedGroup = await createNodeSyncGroup(payload)
        success('Группа синхронизации создана')
      }
      setDialogOpen(false)
      await load()

      // On create with the setup toggle on → run the whole chain (domain + full push + verify).
      // On edit we stay non-destructive: only re-apply the domain when it changed (hosts live in
      // each member's setup); a full replica overwrite stays an explicit "Синхронизировать" click.
      if (!editing) {
        if (autoSetup) {
          await runHaSetup(savedGroup)
        }
      } else if (membersChanged) {
        setSetupTarget(savedGroup)
      } else if (domainChanged) {
        await runDomainApply(savedGroup)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения группы синхронизации')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVerify = async (group: NodeSyncGroup) => {
    setActionLoading(group.id)
    try {
      const result = await verifyNodeSyncGroup(group.id)
      patchGroupVerify(group.id, result)
      showVerifyResult(group, result)
      if (result.ready) {
        success('Проверка: готово к DNS-переключению')
      } else {
        notifyWarning('Проверка нашла расхождения')
      }
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка verify')
    } finally {
      setActionLoading(null)
    }
  }

  const openStoredVerifyResult = useCallback((group: NodeSyncGroup) => {
    if (!group.last_verify_result) return
    showVerifyResult(group, group.last_verify_result)
  }, [showVerifyResult])

  const handleRunDomainApply = async () => {
    if (!domainApplyTarget) return
    const group = domainApplyTarget
    setDomainApplyTarget(null)
    await runDomainApply(group)
  }

  const handleRunSetup = async () => {
    if (!setupTarget) return
    const group = setupTarget
    setSetupTarget(null)
    await runHaSetup(group)
  }

  const copyHost = useCallback(async (host: string) => {
    try {
      await navigator.clipboard.writeText(host)
      setCopiedHost(host)
      window.setTimeout(() => setCopiedHost((cur) => (cur === host ? null : cur)), 1500)
    } catch {
      // Clipboard may be blocked (no HTTPS / permissions); ignore silently.
    }
  }, [])

  const handleDelete = async () => {
    if (!deleteTarget) return
    setActionLoading(deleteTarget.id)
    try {
      await deleteNodeSyncGroup(deleteTarget.id)
      success('Группа синхронизации расформирована: узлы независимы, конфиги на серверах сохранены')
      setDeleteTarget(null)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    } finally {
      setActionLoading(null)
    }
  }

  if (nodes.length < 2) return null

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <GitCompare size={18} />
              Группы синхронизации (HA)
            </CardTitle>
            <CardDescription>
              Один домен на два узла: при падении основного DNS переключает на реплику. «Синхронизировать» —
              полный цикл (домен + копия VPN/crypto на реплику + проверка); «Домен» — только хосты в setup;
              «Проверить» — диагностика без изменений. Runbook:{' '}
              <code className="text-xs">docs/NodeSync.md</code>,{' '}
              <code className="text-xs">reviews/HA-sync-remediation-plan.md</code>.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => void load()} disabled={refreshing}>
              {refreshing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              Обновить
            </Button>
            <Button size="sm" onClick={openCreate} disabled={onlineNodes.length < 2}>
              <Plus size={14} />
              Создать группу
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <InlineProgressBar
            active={polling || setupStage !== null}
            label={setupStage || task?.progress_stage || task?.message || 'Синхронизация HA…'}
            value={task?.progress_percent}
          />
          {loading ? (
            <Spinner label="Загрузка групп синхронизации..." className="py-6" />
          ) : groups.length === 0 ? (
            <SettingsAlert variant="info">
              HA-группа даёт отказоустойчивость: два узла отвечают на один домен с одинаковыми
              ключами. Нажмите «Создать группу» — мастер подскажет, что вводить, и сам выполнит
              первичную синхронизацию.
            </SettingsAlert>
          ) : (
            <ResponsiveDataView
              mobile={groups.map((group) => (
                <SyncGroupCard
                  key={group.id}
                  group={group}
                  actionLoading={actionLoading}
                  onDns={() => setDnsTarget(group)}
                  onOpenVerifyReport={() => openStoredVerifyResult(group)}
                  onSetup={() => setSetupTarget(group)}
                  onDomain={() => setDomainApplyTarget(group)}
                  onVerify={() => void handleVerify(group)}
                  onEdit={() => openEdit(group)}
                  onDelete={() => setDeleteTarget(group)}
                />
              ))}
              desktop={
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Группа</TableHead>
                      <TableHead>Домен</TableHead>
                      <TableHead>{HA_PRIMARY}</TableHead>
                      <TableHead>{HA_REPLICA}</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead className="text-right">Действия</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {groups.map((group) => (
                      <TableRow key={group.id}>
                        <TableCell className="font-medium">
                          {group.name}
                          {group.sync_mode === 'manual_full' ? (
                            <p className="mt-1 text-xs font-normal text-muted-foreground">
                              После расформирования группы на реплике выполните Конфигурации → Синхронизировать.
                            </p>
                          ) : group.sync_mode === 'auto' ? (
                            <p className="mt-1 text-xs font-normal text-muted-foreground">
                              Авто: правки с основного на реплику (см. режим синхронизации при редактировании).
                            </p>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <div>{group.shared_domain}</div>
                          <button
                            type="button"
                            onClick={() => setDnsTarget(group)}
                            className="mt-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            <Globe size={12} />
                            Настройка DNS
                          </button>
                        </TableCell>
                        <TableCell>{group.primary_node_name ?? group.primary_node_id}</TableCell>
                        <TableCell>
                          {(group.replica_node_names?.length
                            ? group.replica_node_names
                            : group.replica_node_ids
                          ).join(', ')}
                        </TableCell>
                        <TableCell>
                          <SyncGroupStatusBlock
                            group={group}
                            onOpenVerifyReport={() => openStoredVerifyResult(group)}
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <SyncGroupActions
                            group={group}
                            actionLoading={actionLoading}
                            onSetup={() => setSetupTarget(group)}
                            onDomain={() => setDomainApplyTarget(group)}
                            onVerify={() => void handleVerify(group)}
                            onEdit={() => openEdit(group)}
                            onDelete={() => setDeleteTarget(group)}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              }
              mobileClassName="space-y-3"
              desktopClassName="overflow-x-auto rounded-md border"
            />
          )}

        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="flex max-h-[min(90dvh,40rem)] w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg">
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="flex min-h-0 flex-1 flex-col"
          >
            <DialogHeader className="shrink-0 space-y-1 px-6 pt-6">
              <DialogTitle>{editing ? 'Изменить группу синхронизации' : 'Создать HA-группу'}</DialogTitle>
              <DialogDescription>
                {editing
                  ? 'Узлы в сети, одинаковая версия AntiZapret.'
                  : 'Основной + реплика, общий домен. DNS-переключение настраивается отдельно.'}
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
              <div className="grid gap-3">
                <div className="grid gap-1.5">
                  <Label htmlFor="sync-name">Название группы</Label>
                  <Input
                    id="sync-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="EU-HA"
                    required
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="sync-domain">Общий домен</Label>
                  <Input
                    id="sync-domain"
                    value={sharedDomain}
                    onChange={(e) => setSharedDomain(e.target.value)}
                    placeholder="vpn.example.com"
                    required
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label>{HA_PRIMARY}</Label>
                  <Select value={primaryId} onValueChange={setPrimaryId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Главный узел" />
                    </SelectTrigger>
                    <SelectContent>
                      {onlineNodes.map((node) => (
                        <SelectItem key={node.id} value={String(node.id)}>
                          {node.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1.5">
                  <Label>{HA_REPLICA} (мин. 1)</Label>
                  <div className="flex flex-wrap gap-2">
                    {onlineNodes
                      .filter((node) => String(node.id) !== primaryId)
                      .map((node) => (
                        <Button
                          key={node.id}
                          type="button"
                          size="sm"
                          variant={replicaIds.includes(node.id) ? 'default' : 'outline'}
                          onClick={() => toggleReplica(node.id)}
                        >
                          {node.name}
                        </Button>
                      ))}
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <Label>Режим синхронизации</Label>
                  <Select value={syncMode} onValueChange={setSyncMode}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="manual_full">Ручной — по кнопке «Синхронизировать»</SelectItem>
                      <SelectItem value="auto">Авто — правки с основного на реплику</SelectItem>
                    </SelectContent>
                  </Select>
                  {syncMode === 'manual_full' ? (
                    <p className="text-xs text-muted-foreground">
                      Изменения на реплике только по кнопке «Синхронизировать».
                    </p>
                  ) : syncMode === 'auto' ? (
                    <AutoSyncModeDescription key={String(dialogOpen)} compact />
                  ) : null}
                </div>
                {!editing ? (
                  <div className="space-y-2 rounded-md border p-3">
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor="auto-setup" className="cursor-pointer">
                        Сразу настроить группу
                      </Label>
                      <Switch id="auto-setup" checked={autoSetup} onCheckedChange={setAutoSetup} />
                    </div>
                    {autoSetup ? (
                      <p className="text-xs text-destructive">
                        На реплике VPN/crypto будут удалены и заменены копией с основного (PKI, сертификаты,
                        .ovpn, WireGuard). Выключите, если на реплике есть нужные данные.
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        После создания диск реплики не меняется — настройте группу кнопкой «Синхронизировать».
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
            <DialogFooter className="shrink-0 border-t px-6 py-4">
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Отмена
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                {editing ? 'Сохранить' : 'Создать'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(setupTarget)}
        title="Синхронизировать HA-группу"
        icon={Wand2}
        description="Выполним за один шаг всё, что нужно для отказоустойчивости группы: домен, полная копия на реплику и проверка."
        alert={{
          variant: 'danger',
          title: 'Состояние реплики будет перезаписано',
          children: (() => {
            const replicasWithClients = (setupTarget?.members ?? []).filter(
              (m) => m.role === 'replica' && m.client_count > 0,
            )
            return (
              <>
                <ol className="list-decimal space-y-0.5 pl-5">
                  <li>Запись общего домена в OPENVPN_HOST / WIREGUARD_HOST на всех узлах.</li>
                  <li>
                    На реплике VPN/crypto удаляются и заменяются копией с основного (PKI, сертификаты, .ovpn,
                    WireGuard) — без перевыпуска сертификатов.
                  </li>
                  <li>Перезапуск всех служб OpenVPN (openvpn-server@*) на реплике.</li>
                  <li>Проверка готовности к DNS-переключению.</li>
                </ol>
                {replicasWithClients.length > 0 ? (
                  <p className="mt-2 font-medium">
                    Текущие клиенты на реплике будут заменены клиентами основного узла:{' '}
                    {replicasWithClients
                      .map((m) => `${m.node_name ?? m.node_id} — ${m.client_count}`)
                      .join(', ')}
                    .
                  </p>
                ) : null}
              </>
            )
          })(),
        }}
        confirmLabel="Синхронизировать"
        destructive
        onConfirm={() => void handleRunSetup()}
        onOpenChange={(open) => {
          if (!open && actionLoading === null) setSetupTarget(null)
        }}
        loading={actionLoading !== null}
      />

      <Dialog open={Boolean(dnsTarget)} onOpenChange={(open) => !open && setDnsTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Globe size={18} />
              Настройка DNS для {dnsTarget?.shared_domain}
            </DialogTitle>
            <DialogDescription>
              Создайте у DNS-провайдера записи для домена на IP всех узлов группы и включите
              health-check для переключения, чтобы при падении одного узла трафик уходил на другой.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-2">
              {(dnsTarget?.members ?? []).map((member) => (
                <div
                  key={member.node_id}
                  className="flex items-center justify-between gap-3 rounded-md border p-2"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={member.role === 'primary' ? 'default' : 'secondary'}>
                        {member.role === 'primary' ? HA_PRIMARY.toLowerCase() : HA_REPLICA.toLowerCase()}
                      </Badge>
                      <span className="truncate text-sm font-medium">
                        {member.node_name ?? member.node_id}
                      </span>
                      <span
                        className={
                          member.online
                            ? 'text-xs text-emerald-600'
                            : 'text-xs text-muted-foreground'
                        }
                      >
                        {member.online ? nodeStatusRu('online') : nodeStatusRu('offline')}
                      </span>
                    </div>
                    <code className="text-xs text-muted-foreground">{member.host ?? '—'}</code>
                  </div>
                  {member.host ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void copyHost(member.host as string)}
                    >
                      {copiedHost === member.host ? <Check size={14} /> : <Copy size={14} />}
                      {copiedHost === member.host ? 'Скопировано' : 'Копировать'}
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
            <SettingsAlert variant="info">
              Пример: A-записи <code>{dnsTarget?.shared_domain}</code> на каждый IP выше. Для
              автоматического переключения используйте DNS с проверкой доступности (режим failover), а не
              простой round-robin. IP узла — это его адрес подключения в панели (host).
            </SettingsAlert>
          </div>
          <DialogFooter>
            <Button type="button" onClick={() => setDnsTarget(null)}>
              Закрыть
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <HaSyncResultDialog
        open={syncResultOpen}
        onOpenChange={setSyncResultOpen}
        result={syncResult}
      />

      <HaVerifyResultDialog
        open={verifyDialogOpen}
        onOpenChange={setVerifyDialogOpen}
        result={verifyDialogView}
      />

      <ConfirmDialog
        open={Boolean(domainApplyTarget)}
        title="Применить shared domain"
        description={`Записать ${domainApplyTarget?.shared_domain ?? 'домен'} в setup на всех узлах группы «${domainApplyTarget?.name ?? ''}»?`}
        confirmLabel="Применить домен"
        onConfirm={() => void handleRunDomainApply()}
        onOpenChange={(open) => {
          if (!open && actionLoading === null) setDomainApplyTarget(null)
        }}
        loading={actionLoading !== null}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Расформировать группу синхронизации"
        description={`Расформировать группу «${deleteTarget?.name ?? ''}»? Узлы станут независимыми: все конфиги и файлы на каждом сервере сохранятся, дальше работа с ними как с обычными нодами.`}
        confirmLabel="Расформировать"
        destructive
        onConfirm={() => void handleDelete()}
        onOpenChange={(open) => {
          if (!open && actionLoading === null) setDeleteTarget(null)
        }}
        loading={actionLoading !== null}
      />
    </>
  )
}
