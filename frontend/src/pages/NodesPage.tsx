import { FormEvent, useEffect, useState } from 'react'
import {
  Check,
  Download,
  Globe,
  HeartPulse,
  KeyRound,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Power,
  RefreshCw,
  Server,
  Trash2,
} from 'lucide-react'
import {
  ApiError,
  checkNodeHealth,
  createNode,
  deleteNode,
  getNodes,
  rotateNodeApiKey,
  updateNode,
} from '@/api/client'
import NodeUpdateDialog from '@/components/NodeUpdateDialog'
import { NodeBadge, NodeStatusBadge, statusLabels } from '@/components/NodeSelector'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { cn } from '@/lib/utils'
import type { Node } from '@/types'
import { Navigate } from 'react-router-dom'

type ConfirmAction = 'delete' | 'rotate-key' | null

function getNodeMeta(node: Node) {
  const meta = node.metadata ?? {}
  const servicesActive = typeof meta.services_active === 'number' ? meta.services_active : null
  const servicesTotal = typeof meta.services_total === 'number' ? meta.services_total : null
  return {
    serverIp: typeof meta.server_ip === 'string' ? meta.server_ip : null,
    servicesLabel:
      servicesActive !== null && servicesTotal !== null ? `${servicesActive}/${servicesTotal}` : null,
    agentVersion: typeof meta.agent_version === 'string' ? meta.agent_version : null,
    antizapretVersion: typeof meta.antizapret_version === 'string' ? meta.antizapret_version : null,
  }
}

function formatLastSeen(lastSeen?: string | null) {
  if (!lastSeen) return null
  return new Date(lastSeen).toLocaleString()
}

type NodeActionsProps = {
  node: Node
  isActive: boolean
  healthLoading: boolean
  activateLoading: boolean
  onActivate: () => void
  onHealth: () => void
  onUpdate: () => void
  onRotateKey: () => void
  onEdit: () => void
  onDelete: () => void
  compact?: boolean
}

function NodeActions({
  node,
  isActive,
  healthLoading,
  activateLoading,
  onActivate,
  onHealth,
  onUpdate,
  onRotateKey,
  onEdit,
  onDelete,
  compact = false,
}: NodeActionsProps) {
  const btnSize = compact ? 'icon' : 'sm'
  const iconSize = compact ? 16 : 14

  return (
    <div className={cn('flex items-center', compact ? 'justify-end gap-0.5' : 'flex-wrap gap-2')}>
      {!isActive && (
        <Button
          variant={compact ? 'ghost' : 'outline'}
          size={btnSize}
          title="Активировать узел"
          disabled={activateLoading}
          onClick={onActivate}
        >
          {activateLoading ? (
            <Loader2 size={iconSize} className="animate-spin" />
          ) : (
            <Power size={iconSize} />
          )}
          {!compact && 'Активировать'}
        </Button>
      )}
      <Button
        variant={compact ? 'ghost' : 'outline'}
        size={btnSize}
        title="Проверка здоровья"
        disabled={healthLoading}
        onClick={onHealth}
      >
        {healthLoading ? (
          <Loader2 size={iconSize} className="animate-spin" />
        ) : (
          <HeartPulse size={iconSize} />
        )}
        {!compact && 'Здоровье'}
      </Button>
      <Button
        variant={compact ? 'ghost' : 'outline'}
        size={btnSize}
        title="Обновление узла"
        onClick={onUpdate}
      >
        <Download size={iconSize} />
        {!compact && 'Обновить'}
      </Button>
      {!node.is_local && (
        <>
          <Button
            variant={compact ? 'ghost' : 'outline'}
            size={btnSize}
            title="Ротация API-ключа"
            onClick={onRotateKey}
          >
            <KeyRound size={iconSize} />
            {!compact && 'Ключ'}
          </Button>
          <Button
            variant={compact ? 'ghost' : 'outline'}
            size={btnSize}
            title="Редактировать"
            onClick={onEdit}
          >
            <Pencil size={iconSize} />
            {!compact && 'Изменить'}
          </Button>
          <Button
            variant={compact ? 'ghost' : 'outline'}
            size={btnSize}
            title="Удалить"
            className="text-destructive hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 size={iconSize} />
            {!compact && 'Удалить'}
          </Button>
        </>
      )}
    </div>
  )
}

type NodeCardProps = {
  node: Node
  isActive: boolean
  healthLoading: boolean
  activateLoading: boolean
  onActivate: () => void
  onHealth: () => void
  onUpdate: () => void
  onRotateKey: () => void
  onEdit: () => void
  onDelete: () => void
}

function NodeCard({
  node,
  isActive,
  healthLoading,
  activateLoading,
  onActivate,
  onHealth,
  onUpdate,
  onRotateKey,
  onEdit,
  onDelete,
}: NodeCardProps) {
  const meta = getNodeMeta(node)
  const lastSeen = formatLastSeen(node.last_seen_at)
  const address = node.is_local ? 'local' : `${node.host}:${node.port}`

  return (
    <Card className={cn(isActive && 'border-primary/40 bg-primary/5')}>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <CardTitle className="flex flex-wrap items-center gap-2 text-base">
              <Server size={16} className="shrink-0 text-muted-foreground" />
              <span className="truncate">{node.name}</span>
              {isActive && (
                <Badge variant="default" className="text-[10px]">
                  <Check size={10} />
                  активный
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="font-mono text-xs">{address}</CardDescription>
          </div>
          <NodeStatusBadge status={node.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">IP сервера</p>
            <p className="font-mono text-xs">{meta.serverIp ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Службы</p>
            <p>{meta.servicesLabel ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Agent</p>
            <p className="font-mono text-xs">{meta.agentVersion ?? '—'}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">AntiZapret</p>
            <p className="font-mono text-xs">{meta.antizapretVersion ?? '—'}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {node.is_local ? (
            <Badge variant="secondary">Локальный</Badge>
          ) : (
            <Badge variant="outline">
              <Globe size={10} />
              Удалённый
            </Badge>
          )}
          {lastSeen && <span>Последняя проверка: {lastSeen}</span>}
        </div>
        <NodeActions
          node={node}
          isActive={isActive}
          healthLoading={healthLoading}
          activateLoading={activateLoading}
          onActivate={onActivate}
          onHealth={onHealth}
          onUpdate={onUpdate}
          onRotateKey={onRotateKey}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      </CardContent>
    </Card>
  )
}

export default function NodesPage() {
  const { user } = useAuth()
  const { activeNode, refresh, refreshNodes, activate } = useNode()
  const { success, error: notifyError } = useNotifications()
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editing, setEditing] = useState<Node | null>(null)
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState(9100)
  const [apiKey, setApiKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [healthLoading, setHealthLoading] = useState<number | null>(null)
  const [activateLoading, setActivateLoading] = useState<number | null>(null)
  const [updateNodeTarget, setUpdateNodeTarget] = useState<Node | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [confirmTarget, setConfirmTarget] = useState<Node | null>(null)
  const [confirmLoading, setConfirmLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      setNodes(await getNodes())
      await refreshNodes()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки узлов')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user?.role === 'admin') load()
  }, [user?.role])

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const openCreate = () => {
    setEditing(null)
    setName('')
    setHost('')
    setPort(9100)
    setApiKey('')
    setShowDialog(true)
  }

  const openEdit = (node: Node) => {
    setEditing(node)
    setName(node.name)
    setHost(node.host)
    setPort(node.port)
    setApiKey('')
    setShowDialog(true)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (editing) {
        const payload: Record<string, string | number> = { name, host, port }
        if (apiKey) payload.api_key = apiKey
        await updateNode(editing.id, payload)
        success('Узел обновлён')
      } else {
        if (!apiKey) {
          notifyError('API-ключ обязателен')
          return
        }
        await createNode({ name, host, port, api_key: apiKey })
        success('Узел добавлен')
      }
      setShowDialog(false)
      await load()
      await refresh()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (node: Node) => {
    setConfirmAction('delete')
    setConfirmTarget(node)
  }

  const handleRotateKey = async (node: Node) => {
    setConfirmAction('rotate-key')
    setConfirmTarget(node)
  }

  const handleConfirm = async () => {
    if (!confirmTarget || !confirmAction) return
    setConfirmLoading(true)
    try {
      if (confirmAction === 'delete') {
        await deleteNode(confirmTarget.id)
        success('Узел удалён')
        await load()
        await refresh()
      } else if (confirmAction === 'rotate-key') {
        await rotateNodeApiKey(confirmTarget.id)
        success(`API-ключ узла «${confirmTarget.name}» обновлён`)
        await load()
      }
      setConfirmAction(null)
      setConfirmTarget(null)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка операции')
    } finally {
      setConfirmLoading(false)
    }
  }

  const handleHealth = async (node: Node) => {
    setHealthLoading(node.id)
    try {
      const result = await checkNodeHealth(node.id)
      const label = statusLabels[result.status] ?? result.status
      if (result.status === 'online') {
        success(`Узел «${node.name}»: ${label}`)
      } else {
        notifyError(`Узел «${node.name}»: ${label}`)
      }
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки')
    } finally {
      setHealthLoading(null)
    }
  }

  const handleActivate = async (node: Node) => {
    setActivateLoading(node.id)
    try {
      await activate(node.id)
      success(`Активный узел: ${node.name}`)
      await load()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка активации')
    } finally {
      setActivateLoading(null)
    }
  }

  const onlineCount = nodes.filter((n) => n.status === 'online').length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Server size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Узлы</h2>
              <NodeBadge name={activeNode?.name} status={activeNode?.status} />
            </div>
            <p className="text-sm text-muted-foreground">
              Управление VPN-серверами AntiZapret (Controller → Nodes)
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Обновить
          </Button>
          <Button onClick={openCreate}>
            <Plus size={16} />
            Добавить узел
          </Button>
        </div>
      </div>

      <SettingsAlert variant="info" title="Активный узел">
        Все операции панели (VPN, маршрутизация, мониторинг) выполняются на{' '}
        <strong>{activeNode?.name ?? 'не выбранном узле'}</strong>. Переключите активный узел кнопкой
        «Активировать» или через селектор в шапке.
      </SettingsAlert>

      <InlineProgressBar
        active={loading || healthLoading !== null || confirmLoading}
        label={
          healthLoading !== null
            ? 'Проверка здоровья узла...'
            : confirmLoading
              ? 'Выполнение операции...'
              : loading
                ? 'Загрузка узлов...'
                : undefined
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <MoreHorizontal size={18} />
            Список узлов
          </CardTitle>
          <CardDescription>
            {loading
              ? 'Загрузка...'
              : nodes.length > 0
                ? `${nodes.length} узл${nodes.length === 1 ? '' : nodes.length < 5 ? 'а' : 'ов'} · ${onlineCount} онлайн`
                : 'Узлы не найдены'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Spinner label="Загрузка узлов..." className="py-12" />
          ) : nodes.length === 0 ? (
            <EmptyState
              icon={Server}
              title="Нет узлов"
              description="Добавьте первый VPN-сервер с установленным node agent для управления через панель"
              action={
                <Button onClick={openCreate}>
                  <Plus size={16} />
                  Добавить первый узел
                </Button>
              }
              className="py-8"
            />
          ) : (
            <>
              <div className="space-y-4 lg:hidden">
                {nodes.map((node) => (
                  <NodeCard
                    key={node.id}
                    node={node}
                    isActive={activeNode?.id === node.id}
                    healthLoading={healthLoading === node.id}
                    activateLoading={activateLoading === node.id}
                    onActivate={() => handleActivate(node)}
                    onHealth={() => handleHealth(node)}
                    onUpdate={() => setUpdateNodeTarget(node)}
                    onRotateKey={() => handleRotateKey(node)}
                    onEdit={() => openEdit(node)}
                    onDelete={() => handleDelete(node)}
                  />
                ))}
              </div>

              <div className="hidden overflow-x-auto rounded-md border lg:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Имя</TableHead>
                      <TableHead>Адрес</TableHead>
                      <TableHead>IP сервера</TableHead>
                      <TableHead>Версии</TableHead>
                      <TableHead>Службы</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead>Тип</TableHead>
                      <TableHead className="text-right">Действия</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {nodes.map((node) => {
                      const isActive = activeNode?.id === node.id
                      const meta = getNodeMeta(node)
                      const lastSeen = formatLastSeen(node.last_seen_at)
                      const address = node.is_local ? 'local' : `${node.host}:${node.port}`

                      return (
                        <TableRow key={node.id} className={cn(isActive && 'bg-primary/5')}>
                          <TableCell className="font-medium">
                            <div className="flex flex-wrap items-center gap-2">
                              {node.name}
                              {isActive && (
                                <Badge variant="default" className="text-[10px]">
                                  <Check size={10} />
                                  активный
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{address}</TableCell>
                          <TableCell className="font-mono text-xs">{meta.serverIp ?? '—'}</TableCell>
                          <TableCell className="text-xs">
                            <div>agent: {meta.agentVersion ?? '—'}</div>
                            <div className="text-muted-foreground">az: {meta.antizapretVersion ?? '—'}</div>
                          </TableCell>
                          <TableCell className="text-xs">{meta.servicesLabel ?? '—'}</TableCell>
                          <TableCell>
                            <NodeStatusBadge status={node.status} />
                            {lastSeen && (
                              <div className="mt-1 text-[10px] text-muted-foreground">{lastSeen}</div>
                            )}
                          </TableCell>
                          <TableCell>
                            {node.is_local ? (
                              <Badge variant="secondary">Локальный</Badge>
                            ) : (
                              <Badge variant="outline">
                                <Globe size={10} />
                                Удалённый
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <NodeActions
                              node={node}
                              isActive={isActive}
                              healthLoading={healthLoading === node.id}
                              activateLoading={activateLoading === node.id}
                              onActivate={() => handleActivate(node)}
                              onHealth={() => handleHealth(node)}
                              onUpdate={() => setUpdateNodeTarget(node)}
                              onRotateKey={() => handleRotateKey(node)}
                              onEdit={() => openEdit(node)}
                              onDelete={() => handleDelete(node)}
                              compact
                            />
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-md">
          <form onSubmit={handleSubmit}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {editing ? <Pencil size={18} /> : <Plus size={18} />}
                {editing ? 'Редактировать узел' : 'Добавить узел'}
              </DialogTitle>
              <DialogDescription>
                {editing
                  ? 'Измените параметры подключения к удалённому node agent'
                  : 'Подключение к node agent на VPN-сервере'}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {!editing && (
                <SettingsAlert variant="info">
                  Удалённый узел должен запускать <strong>node agent</strong> с тем же API-ключом, что указан
                  ниже. Порт по умолчанию — <strong>9100</strong>.
                </SettingsAlert>
              )}
              {editing && !editing.is_local && (
                <SettingsAlert variant="warning" title="API-ключ">
                  Оставьте поле ключа пустым, если не хотите его менять. Новый ключ нужно прописать в
                  конфигурации node agent на сервере.
                </SettingsAlert>
              )}

              <div className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="node-name">Имя</Label>
                  <Input
                    id="node-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="vpn-eu-1"
                    required
                  />
                  <p className="text-xs text-muted-foreground">Отображаемое имя в панели и селекторе узлов</p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="node-host">Хост</Label>
                  <Input
                    id="node-host"
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    placeholder="vpn.example.com"
                    required={!editing?.is_local}
                    disabled={!!editing?.is_local}
                  />
                  <p className="text-xs text-muted-foreground">Домен или IP, доступный с controller</p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="node-port">Порт агента</Label>
                  <Input
                    id="node-port"
                    type="number"
                    min={1}
                    max={65535}
                    value={port}
                    onChange={(e) => setPort(Number(e.target.value))}
                    disabled={!!editing?.is_local}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="node-key">API-ключ (X-Node-Key)</Label>
                  <Input
                    id="node-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={editing ? 'Оставьте пустым, чтобы не менять' : 'Минимум 8 символов'}
                    required={!editing}
                    minLength={editing ? undefined : 8}
                  />
                  {!editing && (
                    <p className="text-xs text-muted-foreground">Секретный ключ для аутентификации агента</p>
                  )}
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowDialog(false)} disabled={submitting}>
                Отмена
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Сохранение...
                  </>
                ) : editing ? (
                  'Сохранить'
                ) : (
                  <>
                    <Plus size={16} />
                    Добавить
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={(open) => {
          if (!open) {
            setConfirmAction(null)
            setConfirmTarget(null)
          }
        }}
        title={confirmAction === 'delete' ? 'Удалить узел?' : 'Ротация API-ключа?'}
        description={
          confirmTarget ? (
            <>
              Узел: <strong>{confirmTarget.name}</strong>
            </>
          ) : undefined
        }
        alert={
          confirmAction === 'delete'
            ? {
                variant: 'danger',
                title: 'Необратимое действие',
                children: 'Узел будет удалён из панели. Конфигурация VPN на сервере не затрагивается.',
              }
            : confirmAction === 'rotate-key'
              ? {
                  variant: 'warning',
                  title: 'Старый ключ перестанет работать',
                  children:
                    'Будет сгенерирован новый API-ключ. Обновите его в конфигурации node agent на сервере, иначе связь с панелью прервётся.',
                }
              : undefined
        }
        confirmLabel={confirmAction === 'delete' ? 'Удалить' : 'Сгенерировать ключ'}
        destructive
        loading={confirmLoading}
        onConfirm={handleConfirm}
      />

      <NodeUpdateDialog
        node={updateNodeTarget}
        open={!!updateNodeTarget}
        onOpenChange={(open) => !open && setUpdateNodeTarget(null)}
        onComplete={load}
      />
    </div>
  )
}
