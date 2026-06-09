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
  Shield,
  Trash2,
} from 'lucide-react'
import {
  ApiError,
  checkNodeHealth,
  createNode,
  deleteNode,
  enableNodeMtls,
  getNodeMtlsStatus,
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
import type { Node, NodeMtlsStatus } from '@/types'
import { Navigate } from 'react-router-dom'

type ConfirmAction = 'delete' | 'rotate-key' | 'enable-mtls' | null

function isWrongVersionSslError(error: string) {
  return /WRONG_VERSION_NUMBER|wrong version number/i.test(error)
}

function NodeTransportBadge({ node }: { node: Node }) {
  if (node.is_local) {
    return <span className="text-muted-foreground">—</span>
  }
  return node.mtls_enabled ? (
    <Badge variant="default">mTLS</Badge>
  ) : (
    <Badge variant="outline">HTTP</Badge>
  )
}

function MtlsCaStatusAlert({ status }: { status: NodeMtlsStatus }) {
  if (!status.writable) {
    return (
      <SettingsAlert variant="warning" title="mTLS: нет прав на каталог сертификатов">
        Панель не может записывать в <code className="text-xs">{status.mtls_dir}</code>. Запустите
        панель с правами на <code className="text-xs">/etc/adminpanelaz</code> или выдайте доступ
        до первого включения mTLS на узле.
      </SettingsAlert>
    )
  }
  if (status.ready) {
    return (
      <SettingsAlert variant="info" title="mTLS: CA готов">
        CA и клиентский сертификат панели созданы
        {status.agent_certs_count > 0 ? ` · сертификатов узлов: ${status.agent_certs_count}` : ''}.
        Каталог: <code className="text-xs">{status.mtls_dir}</code>
      </SettingsAlert>
    )
  }
  return (
    <SettingsAlert variant="info" title="mTLS: CA ещё не создан">
      При первом «Включить mTLS» на удалённом узле панель автоматически создаст CA и сертификаты в{' '}
      <code className="text-xs">{status.mtls_dir}</code>.
    </SettingsAlert>
  )
}

function NodeConnectionErrorAlert({ node, lastError }: { node: Node; lastError: string }) {
  if (isWrongVersionSslError(lastError)) {
    return (
      <SettingsAlert variant="warning" title="Несовпадение протокола (SSL)">
        {node.mtls_enabled ? (
          <>
            Панель подключается по HTTPS, а узел отвечает по HTTP. Временно отключите глобальный{' '}
            <code className="text-xs">NODE_AGENT_MTLS_ENABLED</code> в <code className="text-xs">.env</code>{' '}
            или сбросьте флаг mTLS для узла вручную.
          </>
        ) : (
          <>
            Узел отвечает по HTTPS (mTLS), а панель — по HTTP. Нажмите{' '}
            <strong>«Включить mTLS»</strong> в меню узла или отключите mTLS на node agent.
          </>
        )}
      </SettingsAlert>
    )
  }
  return (
    <SettingsAlert variant="danger" title="Ошибка связи">
      {lastError}
    </SettingsAlert>
  )
}

function getNodeMeta(node: Node) {
  const meta = node.metadata ?? {}
  const servicesActive = typeof meta.services_active === 'number' ? meta.services_active : null
  const servicesTotal = typeof meta.services_total === 'number' ? meta.services_total : null
  return {
    serverIp: typeof meta.server_ip === 'string' ? meta.server_ip : null,
    servicesLabel:
      servicesActive !== null && servicesTotal !== null ? `${servicesActive}/${servicesTotal}` : null,
    agentVersion: typeof meta.agent_version === 'string' ? meta.agent_version : null,
    lastError: typeof meta.last_error === 'string' ? meta.last_error : null,
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
  onEnableMtls: () => void
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
  onEnableMtls,
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
          {!node.mtls_enabled && (
            <Button
              variant={compact ? 'ghost' : 'outline'}
              size={btnSize}
              title="Включить mTLS"
              onClick={onEnableMtls}
            >
              <Shield size={iconSize} />
              {!compact && 'Включить mTLS'}
            </Button>
          )}
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
  onEnableMtls: () => void
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
  onEnableMtls,
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
          <NodeTransportBadge node={node} />
          {lastSeen && <span>Последняя проверка: {lastSeen}</span>}
        </div>
        {node.status === 'offline' && meta.lastError && (
          <NodeConnectionErrorAlert node={node} lastError={meta.lastError} />
        )}
        <NodeActions
          node={node}
          isActive={isActive}
          healthLoading={healthLoading}
          activateLoading={activateLoading}
          onActivate={onActivate}
          onHealth={onHealth}
          onUpdate={onUpdate}
          onRotateKey={onRotateKey}
          onEnableMtls={onEnableMtls}
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
  const { success, warning, error: notifyError } = useNotifications()
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
  const [mtlsStatus, setMtlsStatus] = useState<NodeMtlsStatus | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [nodesList, status] = await Promise.all([getNodes(), getNodeMtlsStatus()])
      setNodes(nodesList)
      setMtlsStatus(status)
      await refreshNodes()
      await refresh()
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

  const resetDialogForm = () => {
    setEditing(null)
    setName('')
    setHost('')
    setPort(9100)
    setApiKey('')
  }

  const openCreate = () => {
    resetDialogForm()
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

  const closeDialog = () => {
    setShowDialog(false)
    resetDialogForm()
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    const trimmedName = name.trim()
    const trimmedHost = host.trim()

    if (!trimmedName) {
      notifyError('Укажите имя узла')
      return
    }
    if (!editing?.is_local && !trimmedHost) {
      notifyError('Укажите хост')
      return
    }
    if (!Number.isFinite(port) || port < 1 || port > 65535) {
      notifyError('Укажите корректный порт (1–65535)')
      return
    }
    if (!editing && (!apiKey || apiKey.length < 8)) {
      notifyError('API-ключ обязателен (минимум 8 символов)')
      return
    }
    if (editing && apiKey && apiKey.length < 8) {
      notifyError('API-ключ должен содержать минимум 8 символов')
      return
    }

    setSubmitting(true)
    try {
      if (editing) {
        const payload: Record<string, string | number> = { name: trimmedName, host: trimmedHost, port }
        if (apiKey) payload.api_key = apiKey
        await updateNode(editing.id, payload)
        closeDialog()
        await load()
        await refresh()
        success('Узел обновлён')
      } else {
        const created = await createNode({ name: trimmedName, host: trimmedHost, port, api_key: apiKey })
        closeDialog()
        await load()
        await refresh()
        if (created.status === 'offline') {
          const lastError =
            typeof created.metadata?.last_error === 'string' ? created.metadata.last_error : null
          warning(
            lastError
              ? `Узел добавлен, но агент недоступен: ${lastError}. Запустите node agent на сервере и нажмите «Здоровье».`
              : 'Узел добавлен, но агент недоступен. Запустите node agent на сервере и нажмите «Здоровье».',
          )
        } else {
          success('Узел добавлен и доступен')
        }
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка сохранения')
    } finally {
      setSubmitting(false)
    }
  }

  const openConfirm = (action: ConfirmAction, node: Node) => {
    setConfirmAction(action)
    setConfirmTarget(node)
  }

  const closeConfirm = () => {
    setConfirmAction(null)
    setConfirmTarget(null)
  }

  const handleDelete = (node: Node) => {
    openConfirm('delete', node)
  }

  const handleRotateKey = (node: Node) => {
    openConfirm('rotate-key', node)
  }

  const handleEnableMtls = (node: Node) => {
    openConfirm('enable-mtls', node)
  }

  const handleConfirm = async () => {
    const action = confirmAction
    const target = confirmTarget
    if (!target || !action) return

    setConfirmLoading(true)
    try {
      if (action === 'delete') {
        await deleteNode(target.id)
        closeConfirm()
        success('Узел удалён')
        await load()
        await refresh()
      } else if (action === 'rotate-key') {
        await rotateNodeApiKey(target.id)
        closeConfirm()
        success(`API-ключ узла «${target.name}» обновлён`)
        await load()
        await refresh()
      } else if (action === 'enable-mtls') {
        const result = await enableNodeMtls(target.id)
        closeConfirm()
        success(result.message || `mTLS включён для узла «${target.name}»`)
        await load()
        await refresh()
        setHealthLoading(target.id)
        try {
          const health = await checkNodeHealth(target.id)
          const label = statusLabels[health.status] ?? health.status
          if (health.status === 'online') {
            success(`Узел «${target.name}»: ${label}`)
          } else {
            const errDetail =
              typeof health.health?.error === 'string' ? health.health.error : null
            notifyError(
              errDetail
                ? `Узел «${target.name}»: ${errDetail}`
                : `Узел «${target.name}»: ${label}`,
            )
          }
          await load()
        } catch (err) {
          notifyError(err instanceof ApiError ? err.message : 'Ошибка проверки здоровья')
        } finally {
          setHealthLoading(null)
        }
      }
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
      const errDetail =
        typeof result.health?.error === 'string' ? result.health.error : null
      if (result.status === 'online') {
        success(`Узел «${node.name}»: ${label}`)
      } else {
        notifyError(
          errDetail ? `Узел «${node.name}»: ${errDetail}` : `Узел «${node.name}»: ${label}`,
        )
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
  const hasRemoteNodes = nodes.some((n) => !n.is_local)
  const showMtlsStatus =
    mtlsStatus &&
    (hasRemoteNodes || mtlsStatus.ready || !mtlsStatus.writable)

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
              Управление VPN-серверами (node agent)
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

      {showMtlsStatus && <MtlsCaStatusAlert status={mtlsStatus} />}

      <InlineProgressBar
        active={loading || healthLoading !== null || confirmLoading || submitting}
        label={
          submitting
            ? 'Сохранение узла...'
            : healthLoading !== null
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
                    onEnableMtls={() => handleEnableMtls(node)}
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
                      <TableHead>Agent</TableHead>
                      <TableHead>Службы</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead>Тип</TableHead>
                      <TableHead>Транспорт</TableHead>
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
                          <TableCell className="font-mono text-xs">{meta.agentVersion ?? '—'}</TableCell>
                          <TableCell className="text-xs">{meta.servicesLabel ?? '—'}</TableCell>
                          <TableCell>
                            <NodeStatusBadge status={node.status} />
                            {lastSeen && (
                              <div className="mt-1 text-[10px] text-muted-foreground">{lastSeen}</div>
                            )}
                            {node.status === 'offline' && meta.lastError && (
                              <div
                                className="mt-1 max-w-xs text-[10px] text-destructive"
                                title={meta.lastError}
                              >
                                {isWrongVersionSslError(meta.lastError)
                                  ? 'Несовпадение протокола HTTP/HTTPS — см. подсказку при раскрытии карточки'
                                  : meta.lastError}
                              </div>
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
                            <NodeTransportBadge node={node} />
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
                              onEnableMtls={() => handleEnableMtls(node)}
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

      <Dialog
        open={showDialog}
        onOpenChange={(open) => {
          if (!open && !submitting) closeDialog()
        }}
      >
        <DialogContent className="max-w-md">
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

          <form noValidate onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-4">
              {!editing && (
                <SettingsAlert variant="info">
                  Сначала на VPN-сервере запустите <strong>node agent</strong> (
                  <code className="text-xs">./start_node_agent.sh daemon</code>), затем укажите его{' '}
                  <strong>публичный IP или домен</strong> (не 127.0.0.1) и тот же API-ключ. Порт —{' '}
                  <strong>9100</strong>.
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
                  />
                  {!editing && (
                    <p className="text-xs text-muted-foreground">Секретный ключ для аутентификации агента</p>
                  )}
                </div>
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog} disabled={submitting}>
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
          if (!open && !confirmLoading) closeConfirm()
        }}
        title={
          confirmAction === 'delete'
            ? 'Удалить узел?'
            : confirmAction === 'rotate-key'
              ? 'Ротация API-ключа?'
              : confirmAction === 'enable-mtls'
                ? 'Включить mTLS?'
                : ''
        }
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
              : confirmAction === 'enable-mtls'
                ? {
                    variant: 'warning',
                    title: 'Перезапуск node agent',
                    children:
                      'Будет сгенерирован сертификат, node agent перезапустится ~5–30 сек. Связь может кратковременно прерваться.',
                  }
                : undefined
        }
        confirmLabel={
          confirmAction === 'delete'
            ? 'Удалить'
            : confirmAction === 'rotate-key'
              ? 'Сгенерировать ключ'
              : confirmAction === 'enable-mtls'
                ? 'Включить mTLS'
                : 'Подтвердить'
        }
        destructive
        loading={confirmLoading}
        onConfirm={handleConfirm}
      />

      <NodeUpdateDialog
        node={updateNodeTarget}
        open={!!updateNodeTarget}
        onOpenChange={(open) => {
          if (!open) setUpdateNodeTarget(null)
        }}
        onComplete={async () => {
          await load()
          await refresh()
        }}
      />
    </div>
  )
}
