import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { GitCompare, Globe, Loader2, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import {
  ApiError,
  applyNodeSyncGroupSharedDomain,
  createNodeSyncGroup,
  deleteNodeSyncGroup,
  getNodeSyncGroups,
  pushNodeSyncGroupFull,
  updateNodeSyncGroup,
  verifyNodeSyncGroup,
} from '@/api/client'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import Spinner from '@/components/ui/Spinner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useNotifications } from '@/context/NotificationContext'
import { useBackgroundTaskPoll } from '@/hooks/useBackgroundTaskPoll'
import type { Node, NodeSyncGroup, NodeSyncVerifyResult, SyncStatus } from '@/types'

type NodeSyncGroupSectionProps = {
  nodes: Node[]
}

const AUTO_SYNC_POLL_MS = 30_000

/** Target auto-sync scope (roadmap §3). */
const AUTO_SYNC_OPERATIONS = [
  'Создание / удаление VPN-клиентов (OVPN cert, WG peer + shadow VpnConfig)',
  'Renew cert, блокировки (temp/permanent), unblock, лимиты трафика, срок WG',
  'OpenVPN disconnect, метаданные клиента (description, owner)',
  'Bulk block / renew / unblock, CSV import, шаблоны клиентов',
  'Файлы AntiZapret config: настройки (списки), редактор, routing files + doall',
  'Настройки setup (PUT antizapret-settings) и apply маршрутизации',
  'CIDR providers: правки файлов, compile/deploy на replica',
  'Политика узла по умолчанию (редактирование только на primary)',
] as const

const syncStatusLabels: Record<SyncStatus, string> = {
  unknown: 'Не синхронизировано',
  synced: 'Синхронизировано',
  pending: 'Синхронизация…',
  failed: 'Ошибка sync',
}

function syncStatusVariant(status: SyncStatus): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (status === 'synced') return 'default'
  if (status === 'pending') return 'secondary'
  if (status === 'failed') return 'destructive'
  return 'outline'
}

function AutoSyncModeDescription() {
  return (
    <SettingsAlert variant="info">
      <p className="font-medium">Auto: все перечисленные операции на primary автоматически реплицируются на replica.</p>
      <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">
        {AUTO_SYNC_OPERATIONS.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        Не синхронизируются: warper-include-ips.txt, флаги ANTIZAPRET_WARP / VPN_WARP (локально на узле).
        Push full — первичное выравнивание и восстановление после рассинхрона.
      </p>
    </SettingsAlert>
  )
}

export default function NodeSyncGroupSection({ nodes }: NodeSyncGroupSectionProps) {
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const { task, polling, startPoll } = useBackgroundTaskPoll()
  const [groups, setGroups] = useState<NodeSyncGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<NodeSyncGroup | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [verifyResult, setVerifyResult] = useState<NodeSyncVerifyResult | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<NodeSyncGroup | null>(null)
  const [pushTarget, setPushTarget] = useState<NodeSyncGroup | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  const [name, setName] = useState('')
  const [sharedDomain, setSharedDomain] = useState('')
  const [primaryId, setPrimaryId] = useState<string>('')
  const [replicaIds, setReplicaIds] = useState<number[]>([])
  const [syncMode, setSyncMode] = useState('manual_full')

  const onlineNodes = useMemo(() => nodes.filter((n) => n.status === 'online'), [nodes])
  const prevSyncStatusRef = useRef<Map<number, SyncStatus>>(new Map())
  const notifiedReplicationRef = useRef<Set<string>>(new Set())

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
    },
    [reportReplicationIssues],
  )

  const load = useCallback(async () => {
    setRefreshing(true)
    try {
      applyGroups(await fetchGroups())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки Sync Groups')
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
    setDialogOpen(true)
  }

  const openEdit = (group: NodeSyncGroup) => {
    setEditing(group)
    setName(group.name)
    setSharedDomain(group.shared_domain)
    setPrimaryId(String(group.primary_node_id))
    setReplicaIds(group.replica_node_ids)
    setSyncMode(group.sync_mode || 'manual_full')
    setDialogOpen(true)
  }

  const toggleReplica = (nodeId: number) => {
    setReplicaIds((prev) =>
      prev.includes(nodeId) ? prev.filter((id) => id !== nodeId) : [...prev, nodeId],
    )
  }

  const runSharedDomainApply = useCallback(
    async (groupId: number, domain: string) => {
      setActionLoading(groupId)
      try {
        const accepted = await applyNodeSyncGroupSharedDomain(groupId)
        success(accepted.message)
        await load()
        startPoll(accepted.task_id, {
          onComplete: () => {
            success(`Домен ${domain} применён на узлах (doall.sh + client.sh 7)`)
            void load()
          },
          onError: (_task, message) => notifyError(message),
        })
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка применения shared domain')
      } finally {
        setActionLoading(null)
      }
    },
    [load, notifyError, startPoll, success],
  )

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const primary = Number(primaryId)
    if (!name.trim() || !sharedDomain.trim() || !primary || replicaIds.length === 0) {
      notifyError('Заполните имя, домен, primary и хотя бы один replica')
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
      const domainChanged = !editing || editing.shared_domain.trim() !== payload.shared_domain
      let groupId: number
      if (editing) {
        const updated = await updateNodeSyncGroup(editing.id, payload)
        groupId = updated.id
        success('Sync Group обновлена')
      } else {
        const created = await createNodeSyncGroup(payload)
        groupId = created.id
        success('Sync Group создана')
      }
      setDialogOpen(false)
      await load()
      if (domainChanged) {
        await runSharedDomainApply(groupId, payload.shared_domain)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения Sync Group')
    } finally {
      setSubmitting(false)
    }
  }

  const handleVerify = async (group: NodeSyncGroup) => {
    setActionLoading(group.id)
    try {
      const result = await verifyNodeSyncGroup(group.id)
      setVerifyResult(result)
      if (result.ready) {
        success('Verify: готово к DNS failover')
      } else {
        notifyError(`Verify: ${result.summary}`)
      }
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка verify')
    } finally {
      setActionLoading(null)
    }
  }

  const handlePushFull = async () => {
    if (!pushTarget) return
    setActionLoading(pushTarget.id)
    try {
      const accepted = await pushNodeSyncGroupFull(pushTarget.id)
      setPushTarget(null)
      success(accepted.message)
      await load()
      startPoll(accepted.task_id, {
        onComplete: () => {
          success('Полная синхронизация завершена')
          void load()
        },
        onError: (_task, message) => notifyError(message),
      })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка push-full')
    } finally {
      setActionLoading(null)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setActionLoading(deleteTarget.id)
    try {
      await deleteNodeSyncGroup(deleteTarget.id)
      success('Sync Group расформирована: узлы независимы, конфиги на серверах сохранены')
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
              Sync Groups (HA)
            </CardTitle>
            <CardDescription>
              Primary + replica с общим доменом. Push full заменяет ручной client.sh 8 → restore.
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
            active={polling}
            label={task?.progress_stage || task?.message || 'Синхронизация HA…'}
            value={task?.progress_percent}
          />
          {loading ? (
            <Spinner label="Загрузка Sync Groups..." className="py-6" />
          ) : groups.length === 0 ? (
            <SettingsAlert variant="info">
              Создайте HA-группу для failover: один домен, два IP, одинаковые ключи на primary и replica.
            </SettingsAlert>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Группа</TableHead>
                  <TableHead>Домен</TableHead>
                  <TableHead>Primary</TableHead>
                  <TableHead>Replica</TableHead>
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
                          После расформирования группы на replica выполните Конфигурации → Синхронизировать.
                        </p>
                      ) : group.sync_mode === 'auto' ? (
                        <p className="mt-1 text-xs font-normal text-muted-foreground">
                          Auto: правки на primary → replica (см. режим sync при редактировании).
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell>{group.shared_domain}</TableCell>
                    <TableCell>{group.primary_node_name ?? group.primary_node_id}</TableCell>
                    <TableCell>
                      {(group.replica_node_names?.length ? group.replica_node_names : group.replica_node_ids).join(
                        ', ',
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={syncStatusVariant(group.sync_status)}>
                        {syncStatusLabels[group.sync_status]}
                      </Badge>
                      {group.last_sync_error ? (
                        <p className="mt-1 text-xs text-destructive">{group.last_sync_error}</p>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actionLoading === group.id || group.sync_status === 'pending'}
                          onClick={() => setPushTarget(group)}
                        >
                          <Upload size={14} />
                          Push full
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actionLoading === group.id || group.sync_status === 'pending'}
                          onClick={() => void runSharedDomainApply(group.id, group.shared_domain)}
                          title="Записать домен в OPENVPN_HOST/WIREGUARD_HOST на всех узлах и выполнить doall.sh + client.sh 7"
                        >
                          <Globe size={14} />
                          Домен → узлы
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={actionLoading === group.id}
                          onClick={() => void handleVerify(group)}
                        >
                          Verify
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => openEdit(group)}>
                          Изменить
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => setDeleteTarget(group)}>
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {verifyResult ? (
            <SettingsAlert variant={verifyResult.ready ? 'info' : 'warning'}>
              <strong>Verify:</strong> {verifyResult.summary}
              {verifyResult.replicas.some((r) => r.mismatches.length > 0) ? (
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {verifyResult.replicas.flatMap((replica) =>
                    replica.mismatches.map((m, idx) => (
                      <li key={`${replica.node_id}-${idx}`}>
                        {replica.node_name ?? replica.node_id}: {m.kind}
                        {m.only_primary?.length ? ` (+primary: ${m.only_primary.join(', ')})` : ''}
                        {m.only_replica?.length ? ` (+replica: ${m.only_replica.join(', ')})` : ''}
                        {m.path ? ` [${m.path}]` : ''}
                      </li>
                    )),
                  )}
                </ul>
              ) : null}
            </SettingsAlert>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <form onSubmit={(e) => void handleSubmit(e)}>
            <DialogHeader>
              <DialogTitle>{editing ? 'Изменить Sync Group' : 'Создать Sync Group'}</DialogTitle>
              <DialogDescription>
                Узлы должны быть online и с одинаковой версией AntiZapret. DNS настраивается вручную.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="sync-name">Имя</Label>
                <Input id="sync-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="sync-domain">Shared domain</Label>
                <Input
                  id="sync-domain"
                  value={sharedDomain}
                  onChange={(e) => setSharedDomain(e.target.value)}
                  placeholder="vpn.example.com"
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label>Primary</Label>
                <Select value={primaryId} onValueChange={setPrimaryId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Primary узел" />
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
              <div className="grid gap-2">
                <Label>Replica (1+)</Label>
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
              <div className="grid gap-2">
                <Label>Режим sync</Label>
                <Select value={syncMode} onValueChange={setSyncMode}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual_full">Manual push (только Push full)</SelectItem>
                    <SelectItem value="auto">Auto — репликация операций с primary</SelectItem>
                  </SelectContent>
                </Select>
                {syncMode === 'manual_full' ? (
                  <SettingsAlert variant="info">
                    После расформирования группы на replica выполните Конфигурации → Синхронизировать.
                  </SettingsAlert>
                ) : syncMode === 'auto' ? (
                  <AutoSyncModeDescription />
                ) : null}
              </div>
            </div>
            <DialogFooter>
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
        open={Boolean(pushTarget)}
        title="Полная синхронизация"
        description="VPN-состояние на replica будет полностью перезаписано из primary (PKI, WireGuard, config). Продолжить?"
        confirmLabel="Push full"
        onConfirm={() => void handlePushFull()}
        onOpenChange={(open) => {
          if (!open && actionLoading === null) setPushTarget(null)
        }}
        loading={actionLoading !== null}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Расформировать Sync Group"
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
