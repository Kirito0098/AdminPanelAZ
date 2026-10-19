import { useEffect, useMemo, useRef, useState } from 'react'
import { Server } from 'lucide-react'
import { ApiError } from '@/api/http'
import { getNodeSyncGroups, getNodes } from '@/api/nodes'
import { previewBulkNodes, startBulkNodes } from '@/api/users'
import AppDialog from '@/components/shared/AppDialog'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type {
  BulkNodesAction,
  BulkNodesPreviewResponse,
  BulkNodesRequest,
  BulkNodesScope,
  Node,
} from '@/types'

const ACTIONS: { id: BulkNodesAction; label: string }[] = [
  { id: 'add', label: 'Добавить сервер' },
  { id: 'remove', label: 'Убрать сервер' },
  { id: 'replace', label: 'Перенести на другой сервер' },
]

/** Подписи причин пропуска из предпросмотра (спека §10). */
const SKIP_LABELS: Record<string, string> = {
  only_server: 'останутся без серверов',
  busy_provision: 'заняты другой задачей',
  already_assigned: 'сервер уже назначен',
  not_assigned: 'сервер не назначен',
}

const SKIP_HINTS: Record<string, string> = {
  only_server: '— уберите у них вручную или используйте «Перенести»',
}

export interface BulkNodesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Пресет с карточки сервера. */
  presetNodeId?: number
  presetAction?: BulkNodesAction
  /** Выбранные в списке пользователи. */
  selectedUserIds: number[]
  /** Текущий фильтр списка — для области «Текущий фильтр». */
  listFilter: { state?: string; q?: string }
  onStarted: (taskId: string) => void
}

export default function BulkNodesDialog({
  open,
  onOpenChange,
  presetNodeId,
  presetAction,
  selectedUserIds,
  listFilter,
  onStarted,
}: BulkNodesDialogProps) {
  const [nodes, setNodes] = useState<Node[]>([])
  const [replicaIds, setReplicaIds] = useState<Set<number>>(new Set())
  const [action, setAction] = useState<BulkNodesAction>(presetAction ?? 'add')
  const [nodeId, setNodeId] = useState<number | null>(presetNodeId ?? null)
  const [toNodeId, setToNodeId] = useState<number | null>(null)
  const [scopeMode, setScopeMode] = useState<'all' | 'user_ids' | 'filter'>('all')
  const [notify, setNotify] = useState(false)
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<BulkNodesPreviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    const load = async () => {
      try {
        const [list, groups] = await Promise.all([getNodes(), getNodeSyncGroups()])
        if (cancelled) return
        setNodes(list)
        const replicas = new Set<number>()
        for (const group of groups) {
          for (const id of group.replica_node_ids ?? []) replicas.add(id)
        }
        setReplicaIds(replicas)
      } catch {
        /* список серверов необязателен — покажем подсказку */
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [open])

  const wasOpen = useRef(false)
  useEffect(() => {
    // Сброс — только в момент открытия: пресет из меню/карточки сервера.
    if (open && !wasOpen.current) {
      setAction(presetAction ?? 'add')
      setNodeId(presetNodeId ?? null)
      setToNodeId(null)
      setScopeMode('all')
      setNotify(false)
      setNote('')
      setPreview(null)
      setError(null)
      setConfirmOpen(false)
    }
    wasOpen.current = open
  }, [open, presetAction, presetNodeId])

  /** Прокси и реплики HA выдавать пользователям нельзя (сервер проверит ещё раз). */
  const assignableNodes = useMemo(
    () =>
      nodes.filter(
        (node) => (node.node_kind ?? 'vpn') === 'vpn' && !replicaIds.has(node.id),
      ),
    [nodes, replicaIds],
  )

  const selectedNode = useMemo(
    () => assignableNodes.find((node) => node.id === nodeId) ?? null,
    [assignableNodes, nodeId],
  )
  const nodeName = selectedNode ? selectedNode.portal_label || selectedNode.name : ''

  // Фильтр «все» — это область «Все с набором», у бэкенда нет состояния «all».
  const filterState = (listFilter.state ?? 'all').trim()
  const filterSupported = filterState !== 'all' && filterState !== 'inactive'
  const scopeOptions = useMemo(() => {
    const options: { id: 'all' | 'user_ids' | 'filter'; label: string; disabled?: boolean }[] = [
      { id: 'all', label: 'Все с набором' },
      {
        id: 'user_ids',
        label: `Выбранные (${selectedUserIds.length})`,
        disabled: selectedUserIds.length === 0,
      },
    ]
    if (filterSupported) {
      options.push({ id: 'filter', label: 'Текущий фильтр' })
    }
    return options
  }, [filterSupported, selectedUserIds.length])

  const buildScope = (): BulkNodesScope => {
    if (scopeMode === 'user_ids') {
      return { mode: 'user_ids', user_ids: selectedUserIds }
    }
    if (scopeMode === 'filter') {
      return { mode: 'filter', state: filterState, q: listFilter.q?.trim() || null }
    }
    return { mode: 'all' }
  }

  const buildBody = (): BulkNodesRequest => ({
    action,
    node_id: nodeId ?? 0,
    to_node_id: action === 'replace' ? toNodeId : null,
    scope: buildScope(),
    notify_telegram: notify,
    note: note.trim() || null,
  })

  // Пустая или неподдерживаемая область — операцию не запускаем: молча менять
  // область опасно (иначе «выбранные» превратились бы в «все с набором»).
  const emptySelection = scopeMode === 'user_ids' && selectedUserIds.length === 0
  const unsupportedFilter = scopeMode === 'filter' && !filterSupported
  const canPreview =
    nodeId != null &&
    (action !== 'replace' || toNodeId != null) &&
    !emptySelection &&
    !unsupportedFilter

  const handlePreview = async () => {
    if (!canPreview) return
    setBusy(true)
    setError(null)
    try {
      setPreview(await previewBulkNodes(buildBody()))
    } catch (err) {
      setPreview(null)
      setError(err instanceof ApiError ? err.message : 'Не удалось получить предпросмотр')
    } finally {
      setBusy(false)
    }
  }

  const handleStart = async () => {
    setBusy(true)
    setError(null)
    try {
      const body = buildBody()
      const res = await startBulkNodes({
        ...body,
        confirm_node_name: action === 'add' ? null : nodeName,
      })
      setConfirmOpen(false)
      onStarted(res.task_id)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось запустить операцию')
    } finally {
      setBusy(false)
    }
  }

  const affectedCount = preview?.affected.length ?? 0
  const destructive = action !== 'add'

  return (
    <>
      <AppDialog
        open={open}
        onOpenChange={onOpenChange}
        title="Массовая операция с серверами"
        description="Изменения применятся ко всем выбранным пользователям одной фоновой задачей"
        icon={Server}
        size="lg"
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            {preview ? (
              <Button
                type="button"
                variant={destructive ? 'destructive' : 'default'}
                onClick={() => (destructive ? setConfirmOpen(true) : void handleStart())}
                disabled={busy || affectedCount === 0}
              >
                {destructive ? 'Запустить…' : 'Запустить'}
              </Button>
            ) : (
              <Button type="button" onClick={() => void handlePreview()} disabled={busy || !canPreview}>
                {busy ? 'Проверяем…' : 'Предпросмотр'}
              </Button>
            )}
          </>
        }
      >
        <div className="space-y-4">
          {error && (
            <SettingsAlert variant="danger" title="Операция невозможна">
              {error}
            </SettingsAlert>
          )}

          <div className="space-y-1.5">
            <Label>Действие</Label>
            <div className="grid gap-1 sm:grid-cols-3">
              {ACTIONS.map((item) => (
                <label
                  key={item.id}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition-colors ${
                    action === item.id
                      ? 'border-primary bg-primary/5'
                      : 'border-transparent hover:bg-muted/50'
                  }`}
                >
                  <input
                    type="radio"
                    name="bulk-action"
                    className="h-4 w-4"
                    checked={action === item.id}
                    onChange={() => {
                      setAction(item.id)
                      setPreview(null)
                    }}
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="bulkNode">Сервер</Label>
            <select
              id="bulkNode"
              value={nodeId ?? ''}
              onChange={(e) => {
                setNodeId(e.target.value ? Number(e.target.value) : null)
                setPreview(null)
              }}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              <option value="">— выберите сервер —</option>
              {assignableNodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.portal_label || node.name}
                  {node.status !== 'online' ? ' (офлайн)' : ''}
                </option>
              ))}
            </select>
            {assignableNodes.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Нет серверов, доступных для выдачи (прокси и реплики HA не подходят).
              </p>
            )}
          </div>

          {action === 'replace' && (
            <div className="space-y-1.5">
              <Label htmlFor="bulkToNode">Перенести на сервер</Label>
              <select
                id="bulkToNode"
                value={toNodeId ?? ''}
                onChange={(e) => {
                  setToNodeId(e.target.value ? Number(e.target.value) : null)
                  setPreview(null)
                }}
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <option value="">— выберите сервер —</option>
                {assignableNodes
                  .filter((node) => node.id !== nodeId)
                  .map((node) => (
                    <option key={node.id} value={node.id}>
                      {node.portal_label || node.name}
                      {node.status !== 'online' ? ' (офлайн)' : ''}
                    </option>
                  ))}
              </select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label>Кому</Label>
            <div className="space-y-1">
              {scopeOptions.map((option) => (
                <label key={option.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="bulk-scope"
                    className="h-4 w-4"
                    disabled={option.disabled}
                    checked={scopeMode === option.id}
                    onChange={() => {
                      setScopeMode(option.id)
                      setPreview(null)
                    }}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            {emptySelection && (
              <p className="text-xs text-muted-foreground">
                Выбранных пользователей нет — выберите область заново.
              </p>
            )}
            {unsupportedFilter && (
              <p className="text-xs text-muted-foreground">
                Текущий фильтр списка нельзя применить к серверам — выберите другую область.
              </p>
            )}
          </div>

          <div className="space-y-2 rounded-lg border bg-muted/20 p-3">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={notify}
                onCheckedChange={(next) => {
                  setNotify(next)
                  setPreview(null)
                }}
                aria-label="Оповестить пользователей в Telegram"
              />
              Оповестить пользователей в Telegram
            </label>
            {notify && (
              <div className="space-y-1.5">
                <Label htmlFor="bulkNote">Заметка для пользователей (необязательно, до 500 символов)</Label>
                <Input
                  id="bulkNote"
                  value={note}
                  maxLength={500}
                  onChange={(e) => {
                    setNote(e.target.value)
                    setPreview(null)
                  }}
                  placeholder="Например: обновите приложение"
                  className="h-9"
                />
              </div>
            )}
          </div>

          {preview && (
            <div className="space-y-3 rounded-lg border bg-muted/20 p-3 text-sm">
              <div>
                <p className="font-medium">
                  Затронуто пользователей: {preview.affected.length}
                </p>
                <p className="text-xs text-muted-foreground">
                  конфигов создать: {preview.configs_to_create} · удалить: {preview.configs_to_delete}
                </p>
              </div>
              {Object.entries(preview.skipped).map(([reason, rows]) => (
                <p key={reason} className="text-xs text-muted-foreground">
                  {SKIP_LABELS[reason] ?? reason}: {rows.length} {SKIP_HINTS[reason] ?? ''}
                </p>
              ))}
              {preview.without_telegram.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  без Telegram: {preview.without_telegram.length} — увидят уведомление в портале
                </p>
              )}
              {preview.notify_text_preview && (
                <div className="rounded-md border bg-background p-2">
                  <p className="text-xs font-medium">Текст уведомления</p>
                  <p className="mt-1 whitespace-pre-line text-xs text-muted-foreground">
                    {preview.notify_text_preview}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </AppDialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={
          action === 'remove'
            ? `Убрать сервер «${nodeName}» у ${affectedCount} пользователей?`
            : `Перенести ${affectedCount} пользователей на другой сервер?`
        }
        description="Операция выполняется одной фоновой задачей, пользователи обрабатываются по очереди."
        alert={{
          variant: 'danger',
          title: 'Удаляются VPN-конфиги',
          children: `Будут удалены плановые конфиги на сервере «${nodeName}» у ${affectedCount} пользователей. У пользователей, у которых это единственный сервер, операция пропускается.`,
        }}
        confirmLabel="Запустить"
        destructive
        loading={busy}
        confirmPhrase={nodeName}
        confirmPhraseLabel={`Введите имя сервера «${nodeName}» для подтверждения`}
        onConfirm={handleStart}
      />
    </>
  )
}
