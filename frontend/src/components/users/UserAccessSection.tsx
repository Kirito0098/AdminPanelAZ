import { useEffect, useMemo, useState } from 'react'
import { ListChecks, Plus, Trash2 } from 'lucide-react'
import { ApiError } from '@/api/client'
import { getNodeSyncGroups, getNodes } from '@/api/nodes'
import {
  addProvisioningConfig,
  removeProvisioningConfig,
  updateProvisioning,
} from '@/api/users'
import { Node, ProvisionPlanItem, UserProvisioningCard } from '@/types'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import UserSection from './UserSection'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import ConfirmDialog from '@/components/shared/ConfirmDialog'

interface UserAccessSectionProps {
  card: UserProvisioningCard
  onRefresh?: () => void
  onDirtyChange?: (dirty: boolean) => void
}

type PlanDraft = {
  baseName: string
  nodeIds: number[]
  protocols: string[]
  indexes: number[]
}

function draftFromCard(card: UserProvisioningCard): PlanDraft {
  const { user, desired, suggested } = card
  return {
    baseName: desired.client_base_name ?? suggested?.client_base_name ?? user.username ?? '',
    nodeIds: desired.node_ids?.length ? desired.node_ids : (suggested?.node_ids ?? []),
    protocols: desired.desired_protocols?.length
      ? desired.desired_protocols
      : (suggested?.protocols ?? []),
    indexes: desired.plan_config_indexes?.length
      ? desired.plan_config_indexes
      : (suggested?.plan_config_indexes ?? []),
  }
}

const sameList = (a: Array<string | number>, b: Array<string | number>) =>
  a.length === b.length && [...a].sort().join('|') === [...b].sort().join('|')

const sameDraft = (a: PlanDraft, b: PlanDraft) =>
  a.baseName.trim() === b.baseName.trim() &&
  sameList(a.nodeIds, b.nodeIds) &&
  sameList(a.protocols, b.protocols) &&
  sameList(a.indexes, b.indexes)

function nodesMissingAwg2(nodes: Node[], selectedIds: number[]): Node[] {
  return nodes.filter((n) => selectedIds.includes(n.id) && n.awg2_installed !== true)
}

export default function UserAccessSection({ card, onRefresh, onDirtyChange }: UserAccessSectionProps) {
  const { user, configs, suggested } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const provisioningOn = isEnabled('user_provisioning')
  const [nodes, setNodes] = useState<Node[]>([])
  const [replicaIds, setReplicaIds] = useState<Set<number>>(new Set())
  const [nodesLoading, setNodesLoading] = useState(false)

  // Без плана подставляем suggested (из уже существующих конфигов) или логин.
  const initialDraft = draftFromCard(card)
  const [draftBaseName, setDraftBaseName] = useState(initialDraft.baseName)
  const [draftNodeIds, setDraftNodeIds] = useState<number[]>(initialDraft.nodeIds)
  const [draftProtocols, setDraftProtocols] = useState<string[]>(initialDraft.protocols)
  const [draftIndexes, setDraftIndexes] = useState<number[]>(initialDraft.indexes)
  // Последнее сохранённое состояние — чтобы показать «есть изменения» и сбросить черновик.
  const [savedPlan, setSavedPlan] = useState<PlanDraft>(initialDraft)
  const [saving, setSaving] = useState(false)

  const draft: PlanDraft = {
    baseName: draftBaseName,
    nodeIds: draftNodeIds,
    protocols: draftProtocols,
    indexes: draftIndexes,
  }
  const dirty = !sameDraft(draft, savedPlan)

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  const resetDraft = () => {
    setDraftBaseName(savedPlan.baseName)
    setDraftNodeIds(savedPlan.nodeIds.filter((id) => !replicaIds.has(id)))
    setDraftProtocols([...savedPlan.protocols])
    setDraftIndexes([...savedPlan.indexes])
  }

  // confirm-deletions flow
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmPending, setConfirmPending] = useState<{ index: number; configs: ProvisionPlanItem[] } | null>(
    null,
  )

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setNodesLoading(true)
      try {
        const [list, groups] = await Promise.all([getNodes(), getNodeSyncGroups().catch(() => [])])
        if (cancelled) return
        const replicas = new Set<number>()
        for (const group of groups) {
          for (const id of group.replica_node_ids ?? []) replicas.add(id)
        }
        const assignableIds = new Set(
          list
            .filter((node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicas.has(node.id))
            .map((node) => node.id),
        )
        setNodes(list)
        setReplicaIds(replicas)
        setDraftNodeIds((prev) => prev.filter((id) => assignableIds.has(id)))
      } catch {
        /* без списка узлов нельзя редактировать назначения — покажем те, что есть в плане */
      } finally {
        if (!cancelled) setNodesLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  /** Прокси и реплики HA выдавать нельзя (сервер проверит ещё раз). */
  const assignableNodes = useMemo(
    () => nodes.filter((node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicaIds.has(node.id)),
    [nodes, replicaIds],
  )

  const awg2Blocked = useMemo(
    () => nodesMissingAwg2(assignableNodes, draftNodeIds),
    [assignableNodes, draftNodeIds],
  )

  const awg2Enabled = isEnabled('awg2')

  const hasPlan = user.client_base_name != null && user.client_base_name.length > 0
  // План заблокирован, пока срок доступа истёк (Stage 1) — изменения и применение недоступны.
  const expired =
    Boolean(card.plan?.blocked) ||
    Boolean(user.access_until && new Date(user.access_until) < new Date())
  const canSave =
    provisioningOn &&
    !expired &&
    !saving &&
    draftBaseName.trim().length > 0 &&
    draftNodeIds.length > 0 &&
    draftProtocols.length > 0 &&
    draftIndexes.length > 0

  const trackTask = (taskId?: string | null) => {
    if (!taskId) {
      onRefresh?.()
      return
    }
    trackBackgroundTask(taskId, {
      onComplete: () => {
        onRefresh?.()
        success('План применён')
      },
      onError: (_task, message) => {
        onRefresh?.()
        notifyError(message)
      },
    })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const submitted: PlanDraft = {
        ...draft,
        nodeIds: [...draft.nodeIds],
        protocols: [...draft.protocols],
        indexes: [...draft.indexes],
      }
      const res = await updateProvisioning(user.id, {
        node_ids: submitted.nodeIds,
        protocols: submitted.protocols,
        plan_config_indexes: submitted.indexes,
        client_base_name: submitted.baseName.trim() || null,
        confirm_deletions: false,
      })
      setSavedPlan(submitted)
      success('План сохранён — применяется')
      onRefresh?.()
      trackTask(res.task_id)
    } catch (err) {
      const apiErr = err as ApiError
      const payload = apiErr.payload as { code?: string; configs?: ProvisionPlanItem[] } | undefined
      if (apiErr.status === 409 && payload?.code === 'confirm_deletions') {
        setConfirmPending({ index: -1, configs: payload.configs ?? [] })
        setConfirmOpen(true)
        return
      }
      notifyError(apiErr.message ?? 'Ошибка сохранения плана')
    } finally {
      setSaving(false)
    }
  }

  const handleConfirmDeletions = async () => {
    if (!confirmPending) return
    setSaving(true)
    try {
      if (confirmPending.index >= 0) {
        // Удаление имени по индексу подтверждаем тем же DELETE-маршрутом.
        const res = await removeProvisioningConfig(user.id, confirmPending.index, true)
        setDraftIndexes((prev) => prev.filter((i) => i !== confirmPending.index))
        setSavedPlan((prev) => ({
          ...prev,
          indexes: prev.indexes.filter((i) => i !== confirmPending.index),
        }))
        success('Имя конфигов удалено из плана')
        trackTask(res.task_id)
        return
      }

      const submitted: PlanDraft = {
        ...draft,
        nodeIds: [...draft.nodeIds],
        protocols: [...draft.protocols],
        indexes: [...draft.indexes],
      }
      const res = await updateProvisioning(user.id, {
        node_ids: submitted.nodeIds,
        protocols: submitted.protocols,
        plan_config_indexes: submitted.indexes,
        client_base_name: submitted.baseName.trim() || null,
        confirm_deletions: true,
      })
      setSavedPlan(submitted)
      success('План сохранён — удаления применены')
      onRefresh?.()
      trackTask(res.task_id)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка применения удалений')
    } finally {
      setSaving(false)
      setConfirmOpen(false)
      setConfirmPending(null)
    }
  }

  const handleAddIndex = async () => {
    // Плана ещё нет — индекс только в черновик, создастся при «Сохранить».
    if (!hasPlan) {
      const free = Array.from({ length: 20 }, (_, i) => i + 1).find(
        (i) => !draftIndexes.includes(i),
      )
      if (free == null) return
      setDraftIndexes((prev) => [...prev, free].sort((a, b) => a - b))
      return
    }
    setSaving(true)
    try {
      const res = await addProvisioningConfig(user.id)
      setDraftIndexes((prev) =>
        prev.includes(res.index) ? prev : [...prev, res.index].sort((a, b) => a - b),
      )
      setSavedPlan((prev) => ({
        ...prev,
        indexes: Array.from(new Set([...prev.indexes, res.index])).sort((a, b) => a - b),
      }))
      success('Имя конфигов добавлено')
      onRefresh?.()
      trackTask(res.task_id)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка добавления имени')
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveIndex = async (index: number) => {
    if (!hasPlan) {
      setDraftIndexes((prev) => prev.filter((i) => i !== index))
      return
    }
    // optimistic: try remove; backend may return 409 confirm_deletions
    setSaving(true)
    try {
      const res = await removeProvisioningConfig(user.id, index, false)
      setDraftIndexes((prev) => prev.filter((i) => i !== index))
      setSavedPlan((prev) => ({ ...prev, indexes: prev.indexes.filter((i) => i !== index) }))
      success('Имя конфигов удалено из плана')
      trackTask(res.task_id)
    } catch (err) {
      const apiErr = err as ApiError
      const payload = apiErr.payload as { code?: string; configs?: ProvisionPlanItem[] } | undefined
      if (apiErr.status === 409 && payload?.code === 'last_config_name') {
        notifyError('Последнее имя плана нельзя удалить — удалите пользователя или очистите план')
      } else if (apiErr.status === 409 && payload?.code === 'confirm_deletions') {
        setConfirmPending({ index, configs: payload.configs ?? [] })
        setConfirmOpen(true)
      } else {
        notifyError(apiErr.message ?? 'Ошибка удаления имени')
      }
    } finally {
      setSaving(false)
    }
  }

  const toggleNode = (nodeId: number, checked: boolean) => {
    const ids = new Set(draftNodeIds)
    if (checked) ids.add(nodeId)
    else ids.delete(nodeId)
    const nextIds = Array.from(ids).sort((a, b) => a - b)
    setDraftNodeIds(nextIds)
    if (nodesMissingAwg2(assignableNodes, nextIds).length > 0) {
      setDraftProtocols((prev) => prev.filter((id) => id !== 'amneziawg2'))
    }
  }

  const toggleProtocol = (proto: string, checked: boolean) => {
    const ids = new Set(draftProtocols)
    if (checked) ids.add(proto)
    else ids.delete(proto)
    setDraftProtocols(Array.from(ids))
  }

  return (
    <div className="space-y-4">
      <UserSection
        icon={ListChecks}
        title="План конфигов"
        description="Узлы, протоколы и имена, которые должны быть у абонента."
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            {dirty && (
              <span className="inline-flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
                Не сохранено
              </span>
            )}
            {dirty && (
              <Button type="button" size="sm" variant="ghost" onClick={resetDraft} disabled={saving}>
                Сбросить
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              onClick={handleSave}
              disabled={!canSave || !dirty}
              title={
                expired
                  ? 'Срок доступа истёк — продлите доступ'
                  : !canSave && provisioningOn
                    ? 'Заполните имя, узлы, протоколы и имена конфигов'
                    : undefined
              }
            >
              {saving ? 'Сохранение…' : 'Сохранить'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          {!provisioningOn && (
            <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
              Модуль «Пользователи (абоненты)» выключен — план доступен только для просмотра.
            </p>
          )}
          <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
            <Label htmlFor="accessBaseName">Базовое имя конфигов</Label>
            <Input
              id="accessBaseName"
              value={draftBaseName}
              onChange={(e) => setDraftBaseName(e.target.value)}
              disabled={!provisioningOn || expired}
              className="h-9 font-mono"
              placeholder={user.username}
            />
            {!hasPlan && suggested ? (
              <p className="text-xs text-muted-foreground">
                Параметры подставлены из существующих конфигов. Проверьте и сохраните.
              </p>
            ) : !hasPlan ? (
              <p className="text-xs text-muted-foreground">
                Плана нет. Заполните поля и сохраните — конфиги создадутся автоматически.
              </p>
            ) : null}
            {expired && (
              <p className="text-xs text-destructive">
                Срок доступа истёк — изменение плана недоступно до продления.
              </p>
            )}
          </div>

          <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
            <Label>Узлы</Label>
            {nodesLoading ? (
              <span className="text-xs text-muted-foreground">Загрузка узлов…</span>
            ) : assignableNodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">В панели нет узлов</p>
            ) : (
              <div className="grid gap-1 sm:grid-cols-2">
                {assignableNodes.map((node) => {
                  const checked = draftNodeIds.includes(node.id)
                  return (
                    <label
                      key={node.id}
                      className={cn(
                        'flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors',
                        checked
                          ? 'border-primary bg-primary/5'
                          : 'border-border/70 hover:bg-muted/50',
                        !provisioningOn || expired ? 'opacity-60' : 'cursor-pointer',
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(next) => toggleNode(node.id, next)}
                        disabled={!provisioningOn || expired}
                        aria-label={`Узел ${node.name}`}
                      />
                      <div className="flex min-w-0 flex-1 items-center gap-1.5">
                        <span
                          className={cn(
                            'h-1.5 w-1.5 shrink-0 rounded-full',
                            node.status === 'online' ? 'bg-emerald-500' : 'bg-muted-foreground/40',
                          )}
                          aria-hidden
                        />
                        <span className="truncate text-sm font-medium">{node.name}</span>
                        <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">
                          {node.status === 'online' ? 'онлайн' : 'офлайн'}
                        </span>
                      </div>
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
            <Label>Протоколы</Label>
            <fieldset className="m-0 grid gap-1 border-none p-0 sm:grid-cols-3">
              <legend className="sr-only">Протоколы</legend>
              {['wireguard', 'openvpn', 'amneziawg2'].map((proto) => {
                const label =
                  proto === 'wireguard'
                    ? 'WireGuard'
                    : proto === 'openvpn'
                      ? 'OpenVPN'
                      : 'AmneziaWG 2.0'
                const checked = draftProtocols.includes(proto)
                const awg2Disabled = proto === 'amneziawg2' && awg2Blocked.length > 0 && !checked
                const disabled = !provisioningOn || expired || awg2Disabled
                return (
                  <label
                    key={proto}
                    className={cn(
                      'flex items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition-colors',
                      checked
                        ? 'border-primary bg-primary/5'
                        : 'border-border/70 hover:bg-muted/50',
                      disabled ? 'opacity-60' : 'cursor-pointer',
                    )}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(next) => toggleProtocol(proto, next)}
                      disabled={disabled}
                      aria-label={label}
                    />
                    {label}
                  </label>
                )
              })}
            </fieldset>
            {awg2Enabled && awg2Blocked.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                AmneziaWG 2.0: AZ-AWG2 не установлен на: {awg2Blocked.map((n) => n.name).join(', ')}
              </p>
            ) : null}
          </div>

          <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Label>Имена конфигов</Label>
                <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                  {draftIndexes.length} / 20
                </Badge>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleAddIndex}
                disabled={!provisioningOn || expired || draftIndexes.length >= 20}
              >
                <Plus size={15} />
                Добавить
              </Button>
            </div>
            {draftIndexes.length === 0 ? (
              <p className="text-xs text-muted-foreground">Нажмите «Добавить», чтобы создать имя</p>
            ) : (
              <>
                <div className="grid gap-1 sm:grid-cols-2">
                  {draftIndexes.map((index) => {
                    const name = index === 1 ? draftBaseName : `${draftBaseName}-${index}`
                    const existing = configs.find((c) => c.name === name)
                    const hasCreated = existing?.nodes.some((n) => n.config_id != null) ?? false
                    const statusVariant: 'success' | 'warning' | 'outline' = existing
                      ? hasCreated
                        ? 'success'
                        : 'warning'
                      : 'outline'
                    const status = existing ? (hasCreated ? 'создан' : 'не создан') : 'вне плана'
                    return (
                      <div
                        key={index}
                        className="flex items-center justify-between gap-2 rounded-lg border border-border/70 px-2.5 py-2"
                      >
                        <div className="flex min-w-0 flex-1 items-center gap-2">
                          <span className="truncate font-mono text-sm">
                            {name || `индекс ${index}`}
                          </span>
                          <Badge
                            variant={statusVariant}
                            className="shrink-0 px-1.5 py-0 text-[10px] font-medium"
                          >
                            {status}
                          </Badge>
                        </div>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-muted-foreground hover:text-destructive"
                          onClick={() => void handleRemoveIndex(index)}
                          disabled={
                            !provisioningOn || expired || (hasPlan && draftIndexes.length <= 1)
                          }
                          aria-label={`Убрать ${name}`}
                        >
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    )
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  До 20 имён. Имя действует на всех узлах абонента.
                </p>
              </>
            )}
          </div>

        </div>
      </UserSection>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Подтвердить удаления"
        description={
          confirmPending ? (
            <>Будет удалено имён конфигов: {confirmPending.configs.length}. Продолжить?</>
          ) : null
        }
        confirmLabel="Удалить и применить"
        destructive
        loading={saving}
        onConfirm={handleConfirmDeletions}
      />
    </div>
  )
}
