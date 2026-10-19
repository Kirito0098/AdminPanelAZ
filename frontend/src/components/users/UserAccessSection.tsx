import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ApiError } from '@/api/client'
import { getNodes } from '@/api/nodes'
import {
  addProvisioningConfig,
  removeProvisioningConfig,
  updateProvisioning,
} from '@/api/users'
import { Node, ProvisionPlanItem, UserUpdatePayload, UserProvisioningCard } from '@/types'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import ConfirmDialog from '@/components/shared/ConfirmDialog'

interface UserAccessSectionProps {
  card: UserProvisioningCard
  onSave: (id: number, data: Partial<UserUpdatePayload>) => void
  onRefresh?: () => void
}

export default function UserAccessSection({ card, onSave, onRefresh }: UserAccessSectionProps) {
  const { user, desired, configs, suggested } = card
  const { isEnabled } = useFeatureModules()
  const { success, error: notifyError } = useNotifications()
  const { trackBackgroundTask } = useProgress()
  const provisioningOn = isEnabled('user_provisioning')
  const [nodes, setNodes] = useState<Node[]>([])
  const [nodesLoading, setNodesLoading] = useState(false)

  // Без плана подставляем suggested (из уже существующих конфигов) или логин.
  const [draftBaseName, setDraftBaseName] = useState(
    desired.client_base_name ?? suggested?.client_base_name ?? user.username ?? '',
  )
  const [draftNodeIds, setDraftNodeIds] = useState<number[]>(
    desired.node_ids?.length ? desired.node_ids : (suggested?.node_ids ?? []),
  )
  const [draftProtocols, setDraftProtocols] = useState<string[]>(
    desired.desired_protocols?.length
      ? desired.desired_protocols
      : (suggested?.protocols ?? []),
  )
  const [draftIndexes, setDraftIndexes] = useState<number[]>(
    desired.plan_config_indexes?.length
      ? desired.plan_config_indexes
      : (suggested?.plan_config_indexes ?? []),
  )
  const [saving, setSaving] = useState(false)

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
        const list = await getNodes()
        if (!cancelled) setNodes(list)
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
      const res = await updateProvisioning(user.id, {
        node_ids: draftNodeIds,
        protocols: draftProtocols,
        plan_config_indexes: draftIndexes,
        client_base_name: draftBaseName.trim() || null,
        confirm_deletions: false,
      })
      success('План сохранён — применяется')
      onSave(user.id, { panel_login_enabled: user.panel_login_enabled })
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
      const res = await updateProvisioning(user.id, {
        node_ids: draftNodeIds,
        protocols: draftProtocols,
        plan_config_indexes: draftIndexes,
        client_base_name: draftBaseName.trim() || null,
        confirm_deletions: true,
      })
      success('План сохранён — удаления применены')
      onSave(user.id, { panel_login_enabled: user.panel_login_enabled })
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
      await removeProvisioningConfig(user.id, index, false)
      setDraftIndexes(draftIndexes.filter((i) => i !== index))
      success('Имя конфигов удалено из плана')
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
    setDraftNodeIds(Array.from(ids).sort((a, b) => a - b))
  }

  const toggleProtocol = (proto: string, checked: boolean) => {
    const ids = new Set(draftProtocols)
    if (checked) ids.add(proto)
    else ids.delete(proto)
    setDraftProtocols(Array.from(ids))
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Развёртывание</CardTitle>
          <CardDescription>
            Какие узлы, протоколы и имена конфигов должны быть у абонента.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
                Найдены существующие конфиги этого пользователя — узлы, протоколы и имя
                подставлены из них. Проверьте и нажмите «Сохранить», чтобы привязать их к плану.
              </p>
            ) : !hasPlan ? (
              <p className="text-xs text-muted-foreground">
                У абонента ещё нет плана конфигов. Задайте имя, узлы, протоколы, хотя бы одно
                имя конфига и нажмите «Сохранить» — панель создаст конфиги.
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
            ) : nodes.length === 0 ? (
              <p className="text-xs text-muted-foreground">Узлов нет в панели</p>
            ) : (
              <div className="grid gap-1 sm:grid-cols-2">
                {nodes.map((node) => {
                  const checked = draftNodeIds.includes(node.id)
                  return (
                    <label
                      key={node.id}
                      className={cn(
                        'flex items-center gap-2 rounded-lg border px-2.5 py-2 transition-colors',
                        checked
                          ? 'border-primary bg-primary/5'
                          : 'border-transparent hover:bg-muted/50',
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(next) => toggleNode(node.id, next)}
                        disabled={!provisioningOn || expired}
                        aria-label={`Узел ${node.name}`}
                      />
                      <div className="min-w-0">
                        <span className="text-sm font-medium">{node.name}</span>
                        <span className="text-[10px] text-muted-foreground">
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
            <fieldset className="border-none p-0 m-0 flex gap-3">
              <legend className="sr-only">Протоколы</legend>
              {['wireguard', 'openvpn', 'amneziawg2'].map((proto) => {
                const label =
                  proto === 'wireguard'
                    ? 'WireGuard'
                    : proto === 'openvpn'
                      ? 'OpenVPN'
                      : 'AmneziaWG 2.0'
                const checked = draftProtocols.includes(proto)
                return (
                  <label key={proto} className="flex items-center gap-2 cursor-pointer">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(next) => toggleProtocol(proto, next)}
                      disabled={!provisioningOn || expired}
                      aria-label={label}
                    />
                    {label}
                  </label>
                )
              })}
            </fieldset>
          </div>

          <div className="space-y-1.5 rounded-xl border bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-2">
              <Label>Имена конфигов в плане</Label>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={handleAddIndex}
                disabled={!provisioningOn || expired || draftIndexes.length >= 20}
              >
                <Plus size={15} />
                Добавить конфиг
              </Button>
            </div>
            {draftIndexes.length === 0 ? (
              <p className="text-xs text-muted-foreground">Имен нет — нажмите «Добавить конфиг»</p>
            ) : (
              <>
                <div className="grid gap-1 sm:grid-cols-2">
                  {draftIndexes.map((index) => {
                    const name = index === 1 ? draftBaseName : `${draftBaseName}-${index}`
                    const existing = configs.find((c) => c.name === name)
                    const hasCreated = existing?.nodes.some((n) => n.config_id != null) ?? false
                    const status = existing ? (hasCreated ? 'создан' : 'не создан') : 'вне набора'
                    return (
                      <div
                        key={index}
                        className="flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2"
                      >
                        <div className="min-w-0 flex-1">
                          <span className="text-sm font-medium">{name || `индекс ${index}`}</span>
                          <span className="text-[10px] text-muted-foreground">{status}</span>
                        </div>
                        <Button
                          type="button"
                          size="icon"
                          className="h-7 w-7 text-[10px] p-0"
                          onClick={() => void handleRemoveIndex(index)}
                          disabled={
                            !provisioningOn || expired || (hasPlan && draftIndexes.length <= 1)
                          }
                          aria-label={`Убрать ${name}`}
                        >
                          <Trash2 size={12} />
                        </Button>
                      </div>
                    )
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  Лимит: до 20 имён на пользователя. Имена на все серверы, не на сервер.
                </p>
              </>
            )}
          </div>

          <div className="flex items-center justify-end gap-3">
            {!canSave && !saving && provisioningOn && !expired && (
              <p className="text-xs text-muted-foreground">
                Нужно: имя, хотя бы один узел, протокол и имя конфига
              </p>
            )}
            <Button type="button" onClick={handleSave} disabled={!canSave}>
              {saving ? 'Сохранение…' : 'Сохранить'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Подтвердить удаления"
        description={
          confirmPending ? (
            <>
              Будет удалено {confirmPending.configs.length} конфигурац{
                confirmPending.configs.length === 1 ? 'ия' : confirmPending.configs.length < 5 ? 'ии' : 'ий'
              }. Продолжить?
            </>
          ) : null}
        confirmLabel="Удалить и применить"
        destructive
        loading={saving}
        onConfirm={handleConfirmDeletions}
      />
    </div>
  )
}
