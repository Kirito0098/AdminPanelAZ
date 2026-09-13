import { FormEvent, Fragment, useEffect, useState } from 'react'
import {
  Activity,
  Check,
  ExternalLink,
  Globe,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Server,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  ApiError,
  checkNodeHealth,
  createNode,
  deleteNode,
  listNodeTransports,
  patchNodeTransport,
  getNodeMtlsStatus,
  rollingNodeUpdate,
  rotateNodeApiKey,
  restartNodeAgent,
  updateNode,
} from '@/api/client'
import NodeUpdateDialog from '@/components/NodeUpdateDialog'
import MtlsCaStatusAlert from '@/components/nodes/MtlsCaStatusAlert'
import NodeActions from '@/components/nodes/NodeActions'
import NodeBulkActionsBar from '@/components/nodes/NodeBulkActionsBar'
import NodeCard from '@/components/nodes/NodeCard'
import NodeOfflineNotifyCard from '@/components/nodes/NodeOfflineNotifyCard'
import NodeSyncGroupSection from '@/components/nodes/NodeSyncGroupSection'
import NodeTransportBadge from '@/components/nodes/NodeTransportBadge'
import ProxyNodePanel, { AZ_PROXY_SH_DOCS_URL } from '@/components/nodes/ProxyNodePanel'
import {
  formatLastSeen,
  getNodeMeta,
  getSelectedNodes,
  isWrongVersionSslError,
} from '@/components/nodes/nodeHelpers'
import { isProxyNode, PROXY_DEFAULT_PORT, VPN_DEFAULT_PORT } from '@/components/nodes/nodeKind'
import ProxyLinkBadge from '@/components/proxy/ProxyLinkBadge'
import ProxyLinkSelect from '@/components/proxy/ProxyLinkSelect'
import { NodeBadge, NodeStatusBadge, statusLabels } from '@/components/NodeSelector'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import ResponsiveDataView from '@/components/shared/ResponsiveDataView'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import Spinner from '@/components/ui/Spinner'
import MetricCard from '@/components/noc/MetricCard'
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
import { Textarea } from '@/components/ui/textarea'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useBackgroundTaskPoll } from '@/hooks/useBackgroundTaskPoll'
import { findNodeHaMembership, nodeDeleteBlockedMessage, nodeHaDeleteBlockedHint } from '@/lib/nodeHa'
import {
  PROXY_LINK_NONE,
  linkedVpnNodeIdFromSelectorValue,
  proxyLinkSelectorOptions,
  resolveProxyLinkSelectorValue,
} from '@/lib/proxyLinkTarget'
import { cn } from '@/lib/utils'
import type {
  Node,
  NodeKind,
  NodeMtlsStatus,
  NodeStatus,
  NodeTransportId,
  NodeTransportOption,
  NodeTransportPatchBody,
} from '@/types'
import { Navigate } from 'react-router-dom'

export { isProxyNode }

/** User guide for SSH node transport (GitHub). */
export const NODE_SSH_TRANSPORT_DOCS_URL =
  'https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs/node-ssh-transport.md'

type ConfirmAction = 'delete' | 'rotate-key' | 'enable-mtls' | 'disable-mtls' | 'restart-agent' | null
type BulkConfirmAction = 'delete' | 'enable-mtls' | null

type SshTransportFormState = {
  ssh_host: string
  ssh_port: string
  ssh_username: string
  ssh_private_key: string
  ssh_passphrase: string
}

const EMPTY_SSH_FORM: SshTransportFormState = {
  ssh_host: '',
  ssh_port: '22',
  ssh_username: 'root',
  ssh_private_key: '',
  ssh_passphrase: '',
}

export default function NodesPage() {
  const { user } = useAuth()
  const {
    activeNode,
    nodes,
    syncGroups,
    syncGroupsLoaded,
    refresh,
    refreshNodes,
    refreshSyncGroups,
    applySyncGroups,
    activate,
  } = useNode()
  const { features } = useFeatureModules()
  // Default-off toggle: treat missing key as disabled (isEnabled() falls back to true).
  const proxyNodesEnabled = features.proxy_nodes === true
  const { success, warning, error: notifyError } = useNotifications()
  const [loading, setLoading] = useState(true)
  const [showDialog, setShowDialog] = useState(false)
  const [editing, setEditing] = useState<Node | null>(null)
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState(VPN_DEFAULT_PORT)
  const [nodeKind, setNodeKind] = useState<NodeKind>('vpn')
  const [apiKey, setApiKey] = useState('')
  const [createTransport, setCreateTransport] = useState<NodeTransportId>('http')
  const [createSshForm, setCreateSshForm] = useState<SshTransportFormState>(EMPTY_SSH_FORM)
  const [transportOptions, setTransportOptions] = useState<NodeTransportOption[]>([
    { id: 'http', label: 'HTTP', available: true },
    { id: 'mtls', label: 'HTTPS + mTLS', available: true },
    { id: 'ssh', label: 'SSH tunnel', available: false },
  ])
  const [linkSelectorValue, setLinkSelectorValue] = useState(PROXY_LINK_NONE)
  const [submitting, setSubmitting] = useState(false)
  const [healthLoading, setHealthLoading] = useState<number | null>(null)
  const [activateLoading, setActivateLoading] = useState<number | null>(null)
  const [updateNodeTarget, setUpdateNodeTarget] = useState<Node | null>(null)
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [confirmTarget, setConfirmTarget] = useState<Node | null>(null)
  const [confirmLoading, setConfirmLoading] = useState(false)
  const [sshDialogNode, setSshDialogNode] = useState<Node | null>(null)
  const [sshForm, setSshForm] = useState<SshTransportFormState>(EMPTY_SSH_FORM)
  const [sshSubmitting, setSshSubmitting] = useState(false)
  const [mtlsStatus, setMtlsStatus] = useState<NodeMtlsStatus | null>(null)
  const [selectedNodeIds, setSelectedNodeIds] = useState<number[]>([])
  const [rollingUpdating, setRollingUpdating] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkConfirmAction, setBulkConfirmAction] = useState<BulkConfirmAction>(null)
  const [haDeleteBlockedNodes, setHaDeleteBlockedNodes] = useState<Node[]>([])
  const [statusFilter, setStatusFilter] = useState<'all' | NodeStatus>('all')
  const { task: rollTask, polling: rollPolling, startPoll: startRollPoll } = useBackgroundTaskPoll()

  const getNodeDeleteBlockedReason = (node: Node): string | null => {
    const membership = findNodeHaMembership(node.id, syncGroups)
    if (!membership) return null
    return nodeDeleteBlockedMessage(node, membership)
  }

  const showHaDeleteBlockedDialog = (blockedNodes: Node[]) => {
    if (blockedNodes.length === 0) return
    setHaDeleteBlockedNodes(blockedNodes)
  }

  const load = async (opts?: { forceNodes?: boolean }) => {
    const forceNodes = opts?.forceNodes ?? true
    setLoading(true)
    try {
      const status = await getNodeMtlsStatus()
      setMtlsStatus(status)
      const tasks: Promise<unknown>[] = []
      if (forceNodes || nodes.length === 0) {
        tasks.push(refreshNodes().catch(() => {}))
      }
      if (forceNodes || !syncGroupsLoaded) {
        tasks.push(refreshSyncGroups())
      }
      if (forceNodes) {
        tasks.push(refresh())
      }
      if (tasks.length > 0) {
        await Promise.all(tasks)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки узлов')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user?.role === 'admin') void load({ forceNodes: false })
    // Initial mount: reuse NodeContext nodes/syncGroups when already loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role])

  useEffect(() => {
    if (!showDialog || editing) return
    let cancelled = false
    listNodeTransports()
      .then((res) => {
        if (!cancelled && Array.isArray(res.items) && res.items.length > 0) {
          setTransportOptions(res.items)
        }
      })
      .catch(() => {
        /* keep defaults */
      })
    return () => {
      cancelled = true
    }
  }, [showDialog, editing])

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const resetDialogForm = () => {
    setEditing(null)
    setName('')
    setHost('')
    setPort(VPN_DEFAULT_PORT)
    setNodeKind('vpn')
    setApiKey('')
    setCreateTransport('http')
    setCreateSshForm(EMPTY_SSH_FORM)
    setLinkSelectorValue(PROXY_LINK_NONE)
  }

  const openCreate = () => {
    resetDialogForm()
    setShowDialog(true)
  }

  const handleNodeKindChange = (kind: NodeKind) => {
    setNodeKind(kind)
    setPort(kind === 'proxy' ? PROXY_DEFAULT_PORT : VPN_DEFAULT_PORT)
    if (kind !== 'proxy') {
      setLinkSelectorValue(PROXY_LINK_NONE)
    }
  }

  const openEdit = (node: Node) => {
    setEditing(node)
    setName(node.name)
    setHost(node.host)
    setPort(node.port)
    setNodeKind(isProxyNode(node) ? 'proxy' : 'vpn')
    setApiKey('')
    setLinkSelectorValue(
      isProxyNode(node)
        ? resolveProxyLinkSelectorValue(node.linked_vpn_node_id, nodes, syncGroups)
        : PROXY_LINK_NONE,
    )
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
    if (!editing?.is_local && (!Number.isFinite(port) || port < 1 || port > 65535)) {
      notifyError('Укажите корректный порт (1–65535)')
      return
    }
    if (!editing && (!apiKey || apiKey.length < 8)) {
      notifyError('API-ключ обязателен (минимум 8 символов)')
      return
    }
    if (editing && !editing.is_local && apiKey && apiKey.length < 8) {
      notifyError('API-ключ должен содержать минимум 8 символов')
      return
    }

    let createSshPayload:
      | {
          ssh_host: string
          ssh_port: number
          ssh_username: string
          ssh_private_key: string
          ssh_passphrase?: string
        }
      | undefined
    if (!editing && createTransport === 'ssh') {
      const sshHost = (createSshForm.ssh_host.trim() || trimmedHost).trim()
      const sshUsername = createSshForm.ssh_username.trim()
      const sshPrivateKey = createSshForm.ssh_private_key.trim()
      const sshPort = Number(createSshForm.ssh_port)
      if (!sshHost) {
        notifyError('Укажите SSH-хост')
        return
      }
      if (!Number.isInteger(sshPort) || sshPort < 1 || sshPort > 65535) {
        notifyError('Укажите корректный SSH-порт (1–65535)')
        return
      }
      if (!sshUsername) {
        notifyError('Укажите SSH-пользователя')
        return
      }
      if (!sshPrivateKey) {
        notifyError('Добавьте приватный SSH-ключ')
        return
      }
      createSshPayload = {
        ssh_host: sshHost,
        ssh_port: sshPort,
        ssh_username: sshUsername,
        ssh_private_key: sshPrivateKey,
      }
      const sshPassphrase = createSshForm.ssh_passphrase.trim()
      if (sshPassphrase) {
        createSshPayload.ssh_passphrase = sshPassphrase
      }
    }

    setSubmitting(true)
    try {
      const isProxyForm =
        (editing && isProxyNode(editing)) || (!editing && proxyNodesEnabled && nodeKind === 'proxy')
      const linkedVpnNodeId = isProxyForm
        ? linkedVpnNodeIdFromSelectorValue(linkSelectorValue, proxyLinkSelectorOptions(nodes, syncGroups))
        : undefined

      if (editing) {
        if (editing.is_local) {
          await updateNode(editing.id, { name: trimmedName })
        } else {
          const payload: {
            name: string
            host: string
            port: number
            api_key?: string
            linked_vpn_node_id?: number | null
          } = { name: trimmedName, host: trimmedHost, port }
          if (apiKey) payload.api_key = apiKey
          if (isProxyForm) payload.linked_vpn_node_id = linkedVpnNodeId ?? null
          await updateNode(editing.id, payload)
        }
        closeDialog()
        await load()
        await refresh()
        success(editing.is_local ? 'Имя узла обновлено' : 'Узел обновлён')
      } else {
        const kind = proxyNodesEnabled && nodeKind === 'proxy' ? 'proxy' : 'vpn'
        const created = await createNode({
          name: trimmedName,
          host: trimmedHost,
          port,
          api_key: apiKey,
          node_kind: kind,
          transport: createTransport,
          ...(createSshPayload || {}),
          ...(kind === 'proxy' ? { linked_vpn_node_id: linkedVpnNodeId ?? null } : {}),
        })
        closeDialog()
        await load()
        await refresh()
        if (created.status === 'offline') {
          const lastError =
            typeof created.metadata?.last_error === 'string' ? created.metadata.last_error : null
          const agentLabel = kind === 'proxy' ? 'proxy_agent' : 'node agent'
          warning(
            lastError
              ? `Узел добавлен, но агент недоступен: ${lastError}. Запустите ${agentLabel} на сервере и нажмите «Здоровье».`
              : `Узел добавлен, но агент недоступен. Запустите ${agentLabel} на сервере и нажмите «Здоровье».`,
          )
        } else {
          success(kind === 'proxy' ? 'Прокси-узел добавлен и доступен' : 'Узел добавлен и доступен')
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

  const closeSshDialog = () => {
    setSshDialogNode(null)
    setSshForm(EMPTY_SSH_FORM)
  }

  const openSshDialog = (node: Node) => {
    setSshDialogNode(node)
    setSshForm({
      ssh_host: (node.ssh_host || node.host || '').trim(),
      ssh_port: String(node.ssh_port || 22),
      ssh_username: (node.ssh_username || 'root').trim() || 'root',
      ssh_private_key: '',
      ssh_passphrase: '',
    })
  }

  const handleDelete = (node: Node) => {
    if (getNodeDeleteBlockedReason(node)) {
      showHaDeleteBlockedDialog([node])
      return
    }
    openConfirm('delete', node)
  }

  const handleRotateKey = (node: Node) => {
    openConfirm('rotate-key', node)
  }

  const handleTransportChange = (node: Node, transport: NodeTransportId) => {
    const current = (node.transport || (node.mtls_enabled ? 'mtls' : 'http')).toLowerCase()
    if (transport === current) return
    if (transport === 'ssh') {
      openSshDialog(node)
      return
    }
    if (transport === 'mtls') {
      openConfirm('enable-mtls', node)
    } else {
      openConfirm('disable-mtls', node)
    }
  }

  const handleSshSubmit = async () => {
    const target = sshDialogNode
    if (!target) return

    const sshHost = sshForm.ssh_host.trim()
    const sshUsername = sshForm.ssh_username.trim()
    const sshPrivateKey = sshForm.ssh_private_key.trim()
    const sshPort = Number(sshForm.ssh_port)

    if (!sshHost) {
      notifyError('Укажите SSH-хост')
      return
    }
    if (!Number.isInteger(sshPort) || sshPort < 1 || sshPort > 65535) {
      notifyError('Укажите корректный SSH-порт (1–65535)')
      return
    }
    if (!sshUsername) {
      notifyError('Укажите SSH-пользователя')
      return
    }
    if (!target.ssh_key_configured && !sshPrivateKey) {
      notifyError('Добавьте приватный SSH-ключ')
      return
    }

    setSshSubmitting(true)
    try {
      const body: NodeTransportPatchBody = {
        transport: 'ssh',
        ssh_host: sshHost,
        ssh_port: sshPort,
        ssh_username: sshUsername,
      }
      const sshPassphrase = sshForm.ssh_passphrase.trim()
      if (sshPrivateKey) {
        body.ssh_private_key = sshPrivateKey
      }
      if (sshPassphrase) {
        body.ssh_passphrase = sshPassphrase
      }
      await patchNodeTransport(target.id, body)
      closeSshDialog()
      success(`Способ связи «${target.name}»: SSH`)
      await load()
      await refresh()
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        notifyError('SSH transport выключен в разделе модулей панели')
      } else {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка переключения на SSH')
      }
    } finally {
      setSshSubmitting(false)
    }
  }

  const handleRestartAgent = (node: Node) => {
    openConfirm('restart-agent', node)
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
        await patchNodeTransport(target.id, 'mtls')
        closeConfirm()
        success(
          isProxyNode(target)
            ? `Способ связи «${target.name}»: HTTPS + mTLS (сертификаты proxy_agent вручную)`
            : `Способ связи «${target.name}»: HTTPS + mTLS`,
        )
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
      } else if (action === 'disable-mtls') {
        await patchNodeTransport(target.id, 'http')
        closeConfirm()
        success(`Способ связи «${target.name}»: HTTP`)
        warning(
          'Агент по-прежнему может работать с mTLS. Для полного отключения настройте узел вручную.',
        )
        await load()
        await refresh()
      } else if (action === 'restart-agent') {
        const result = await restartNodeAgent(target.id)
        closeConfirm()
        success(result.message || `Перезапуск node agent «${target.name}» запланирован`)
        if (result.restarting) {
          warning('Node agent перезапускается — подождите и выполните проверку здоровья')
        }
        await load()
        await refresh()
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

  const toggleNodeSelection = (nodeId: number) => {
    setSelectedNodeIds((prev) =>
      prev.includes(nodeId) ? prev.filter((id) => id !== nodeId) : [...prev, nodeId],
    )
  }

  const clearNodeSelection = () => {
    setSelectedNodeIds([])
  }

  const handleRollingUpdate = async (nodeIds: number[]) => {
    if (nodeIds.length === 0) {
      notifyError('Выберите хотя бы один узел')
      return
    }
    setRollingUpdating(true)
    try {
      const result = await rollingNodeUpdate(nodeIds)
      if (result.task_id) {
        startRollPoll(result.task_id, {
          onComplete: async (task) => {
            success(task.message || 'Rolling update завершён')
            setSelectedNodeIds([])
            await load()
            setRollingUpdating(false)
          },
          onError: (_task, message) => {
            notifyError(message)
            setRollingUpdating(false)
          },
        })
        success(result.message)
      }
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка rolling update')
      setRollingUpdating(false)
    }
  }

  const handleBulkHealth = async () => {
    const selected = getSelectedNodes(nodes, selectedNodeIds)
    if (selected.length === 0) {
      notifyError('Выберите хотя бы один узел')
      return
    }

    setBulkBusy(true)
    let online = 0
    let offline = 0
    const errors: string[] = []

    try {
      for (const node of selected) {
        try {
          const result = await checkNodeHealth(node.id)
          if (result.status === 'online') {
            online += 1
          } else {
            offline += 1
            const errDetail =
              typeof result.health?.error === 'string' ? result.health.error : null
            if (errDetail) {
              errors.push(`${node.name}: ${errDetail}`)
            }
          }
        } catch (err) {
          offline += 1
          errors.push(
            `${node.name}: ${err instanceof ApiError ? err.message : 'ошибка проверки'}`,
          )
        }
      }

      await load()

      if (offline === 0) {
        success(`Проверка здоровья: ${online} узл(ов) в сети`)
      } else if (online === 0) {
        notifyError(
          errors.length > 0
            ? `Все выбранные узлы не в сети. ${errors[0]}`
            : `Все выбранные узлы не в сети (${offline})`,
        )
      } else {
        warning(`Проверка здоровья: ${online} в сети, ${offline} не в сети`)
      }
    } finally {
      setBulkBusy(false)
    }
  }

  const openBulkConfirm = (action: BulkConfirmAction) => {
    const selected = getSelectedNodes(nodes, selectedNodeIds)
    if (action === 'delete') {
      const remoteSelected = selected.filter((node) => !node.is_local)
      if (remoteSelected.length === 0) {
        notifyError('Локальный узел нельзя удалить. Выберите удалённые узлы.')
        return
      }
      const blocked = remoteSelected.filter((node) => getNodeDeleteBlockedReason(node))
      if (blocked.length === remoteSelected.length) {
        showHaDeleteBlockedDialog(blocked)
        return
      }
      if (blocked.length > 0) {
        warning(
          `${blocked.length} из ${remoteSelected.length} узл(ов) в HA-группе — будут пропущены. Сначала расформируйте группу синхронизации.`,
        )
      }
    }
    if (action === 'enable-mtls') {
      const mtlsCandidates = selected.filter(
        (node) =>
          !node.is_local &&
          !isProxyNode(node) &&
          (node.transport || (node.mtls_enabled ? 'mtls' : 'http')) !== 'mtls',
      )
      if (mtlsCandidates.length === 0) {
        notifyError('Нет удалённых VPN-узлов без mTLS среди выбранных')
        return
      }
    }
    setBulkConfirmAction(action)
  }

  const closeBulkConfirm = () => {
    setBulkConfirmAction(null)
  }

  const handleBulkConfirm = async () => {
    const action = bulkConfirmAction
    if (!action) return

    const selected = getSelectedNodes(nodes, selectedNodeIds)
    setConfirmLoading(true)
    setBulkBusy(true)

    try {
      if (action === 'delete') {
        const remoteSelected = selected.filter((node) => !node.is_local)
        const failed: string[] = []
        const deletedIds: number[] = []
        for (const node of remoteSelected) {
          const blockedReason = getNodeDeleteBlockedReason(node)
          if (blockedReason) {
            failed.push(blockedReason)
            continue
          }
          try {
            await deleteNode(node.id)
            deletedIds.push(node.id)
          } catch (err) {
            failed.push(`${node.name}: ${err instanceof ApiError ? err.message : 'ошибка'}`)
          }
        }
        closeBulkConfirm()
        if (deletedIds.length > 0) {
          setSelectedNodeIds((prev) => prev.filter((id) => !deletedIds.includes(id)))
        }
        await load()
        await refresh()
        const deletedCount = remoteSelected.length - failed.length
        if (failed.length === 0) {
          success(`Удалено узлов: ${remoteSelected.length}`)
        } else if (deletedCount === 0) {
          const haBlocked = remoteSelected.filter((node) => getNodeDeleteBlockedReason(node))
          if (haBlocked.length > 0) {
            showHaDeleteBlockedDialog(haBlocked)
          } else {
            notifyError(failed[0] ?? 'Не удалось удалить выбранные узлы')
          }
        } else {
          notifyError(`Удалено ${deletedCount} из ${remoteSelected.length}. ${failed[0]}`)
        }
      } else if (action === 'enable-mtls') {
        const mtlsCandidates = selected.filter(
          (node) =>
            !node.is_local &&
            !isProxyNode(node) &&
            (node.transport || (node.mtls_enabled ? 'mtls' : 'http')) !== 'mtls',
        )
        let enabled = 0
        const failed: string[] = []
        for (const node of mtlsCandidates) {
          try {
            await patchNodeTransport(node.id, 'mtls')
            enabled += 1
            try {
              await checkNodeHealth(node.id)
            } catch {
              // health after mTLS is best-effort
            }
          } catch (err) {
            failed.push(`${node.name}: ${err instanceof ApiError ? err.message : 'ошибка'}`)
          }
        }
        closeBulkConfirm()
        await load()
        await refresh()
        if (failed.length === 0) {
          success(`mTLS включён на ${enabled} узл(ах)`)
        } else if (enabled === 0) {
          notifyError(`Не удалось включить mTLS. ${failed[0]}`)
        } else {
          warning(`mTLS включён на ${enabled} из ${mtlsCandidates.length} узл(ов)`)
        }
      }
    } finally {
      setConfirmLoading(false)
      setBulkBusy(false)
    }
  }

  const handleRollingUpdateSelected = () => {
    void handleRollingUpdate(selectedNodeIds)
  }

  const onlineCount = nodes.filter((n) => n.status === 'online').length
  const offlineCount = nodes.filter((n) => n.status === 'offline').length
  const unknownCount = nodes.filter((n) => n.status === 'unknown').length
  const filteredNodes =
    statusFilter === 'all' ? nodes : nodes.filter((n) => n.status === statusFilter)
  const showMtlsStatus = Boolean(mtlsStatus && (!mtlsStatus.ready || !mtlsStatus.writable))

  return (
    <div className="space-y-6">
      <PageSectionHeader
        icon={Server}
        title="Узлы"
        titleAddon={<NodeBadge name={activeNode?.name} status={activeNode?.status} />}
        description={
          proxyNodesEnabled
            ? 'VPN-узлы (node agent) и прокси-узлы (proxy_agent). Операции панели идут на активном узле.'
            : 'VPN-серверы с node agent. Операции панели идут на активном узле.'
        }
        actions={
          <>
            <Button variant="outline" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              Обновить
            </Button>
            <Button onClick={openCreate}>
              <Plus size={16} />
              Добавить узел
            </Button>
          </>
        }
      />

      {nodes.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Всего"
            value={<span className="tabular-nums">{nodes.length}</span>}
            icon={Server}
            accent="cyan"
            sub={proxyNodesEnabled ? 'VPN + прокси' : 'VPN-узлы'}
          />
          <MetricCard
            label="В сети"
            value={<span className="tabular-nums">{onlineCount}</span>}
            icon={Wifi}
            accent="green"
            sub={
              nodes.length > 0
                ? `${Math.round((onlineCount / nodes.length) * 100)}% флота`
                : undefined
            }
          />
          <MetricCard
            label="Не в сети"
            value={<span className="tabular-nums">{offlineCount}</span>}
            icon={WifiOff}
            accent={offlineCount > 0 ? 'red' : 'default'}
            sub={unknownCount > 0 ? `+${unknownCount} неизвестно` : 'по health check'}
          />
          <MetricCard
            label="Активный"
            value={activeNode?.name ?? '—'}
            icon={Activity}
            accent="amber"
            sub={activeNode ? statusLabels[activeNode.status] : 'не выбран'}
          />
        </div>
      )}

      {showMtlsStatus && mtlsStatus && <MtlsCaStatusAlert status={mtlsStatus} />}

      <NodeOfflineNotifyCard />

      <NodeSyncGroupSection
        nodes={nodes}
        initialGroups={syncGroups}
        groupsLoaded={syncGroupsLoaded}
        onGroupsChanged={applySyncGroups}
      />

      {(rollPolling || rollTask) && (
        <SettingsAlert variant="info" title="Rolling update">
          {rollTask?.progress_stage || rollTask?.message || 'Обновление узлов…'}
          {rollTask?.progress_percent != null && ` (${rollTask.progress_percent}%)`}
        </SettingsAlert>
      )}

      <InlineProgressBar
        active={
          loading ||
          healthLoading !== null ||
          confirmLoading ||
          submitting ||
          sshSubmitting ||
          rollingUpdating ||
          rollPolling ||
          bulkBusy
        }
        label={
          sshSubmitting
            ? 'Сохранение SSH...'
            : submitting
            ? 'Сохранение узла...'
            : bulkBusy
              ? 'Массовая операция...'
            : healthLoading !== null
              ? 'Проверка здоровья узла...'
              : confirmLoading
                ? 'Выполнение операции...'
                : loading
                  ? 'Загрузка узлов...'
                  : undefined
        }
      />

      <Card className="overflow-hidden border-border/70">
        <CardHeader className="border-b border-border/60 bg-muted/15 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <MoreHorizontal size={18} className="text-muted-foreground" />
                Список узлов
              </CardTitle>
              <CardDescription>
                {loading
                  ? 'Загрузка...'
                  : nodes.length > 0
                    ? `${filteredNodes.length} из ${nodes.length} · ${onlineCount} в сети`
                    : 'Узлы не найдены'}
              </CardDescription>
            </div>
            {nodes.length > 0 && (
              <div
                className="flex flex-wrap gap-1 rounded-lg border border-border/60 bg-background/80 p-1"
                role="tablist"
                aria-label="Фильтр по статусу"
              >
                {(
                  [
                    { value: 'all' as const, label: 'Все', count: nodes.length },
                    { value: 'online' as const, label: 'В сети', count: onlineCount },
                    { value: 'offline' as const, label: 'Офлайн', count: offlineCount },
                    { value: 'unknown' as const, label: '?', count: unknownCount },
                  ] as const
                ).map((item) => (
                  <Button
                    key={item.value}
                    type="button"
                    role="tab"
                    aria-selected={statusFilter === item.value}
                    size="sm"
                    variant={statusFilter === item.value ? 'secondary' : 'ghost'}
                    className={cn(
                      'h-8 gap-1.5 px-2.5 text-xs',
                      statusFilter === item.value && 'shadow-sm',
                    )}
                    onClick={() => setStatusFilter(item.value)}
                  >
                    {item.label}
                    <span className="tabular-nums text-muted-foreground">{item.count}</span>
                  </Button>
                ))}
              </div>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-4">
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
          ) : filteredNodes.length === 0 ? (
            <EmptyState
              icon={WifiOff}
              title="Нет узлов с таким статусом"
              description="Сбросьте фильтр или проверьте здоровье агентов"
              action={
                <Button variant="outline" onClick={() => setStatusFilter('all')}>
                  Показать все
                </Button>
              }
              className="py-8"
            />
          ) : (
            <>
              <NodeBulkActionsBar
                nodes={filteredNodes}
                selectedNodeIds={selectedNodeIds}
                bulkBusy={bulkBusy}
                rollingUpdating={rollingUpdating}
                rollPolling={rollPolling}
                onSelectAll={() => setSelectedNodeIds(filteredNodes.map((n) => n.id))}
                onClearSelection={clearNodeSelection}
                onBulkHealth={() => void handleBulkHealth()}
                onBulkRollingUpdate={handleRollingUpdateSelected}
                onBulkEnableMtls={() => openBulkConfirm('enable-mtls')}
                onBulkDelete={() => openBulkConfirm('delete')}
              />

              <ResponsiveDataView
                breakpoint="xl"
                mobile={filteredNodes.map((node) => (
                  <NodeCard
                    key={node.id}
                    node={node}
                    isActive={activeNode?.id === node.id}
                    showProxyUi={proxyNodesEnabled}
                    nodes={nodes}
                    syncGroups={syncGroups}
                    healthLoading={healthLoading === node.id}
                    activateLoading={activateLoading === node.id}
                    selected={selectedNodeIds.includes(node.id)}
                    onToggleSelect={() => toggleNodeSelection(node.id)}
                    onActivate={() => handleActivate(node)}
                    onHealth={() => handleHealth(node)}
                    onUpdate={() => setUpdateNodeTarget(node)}
                    onRestart={() => handleRestartAgent(node)}
                    onRotateKey={() => handleRotateKey(node)}
                    onTransportChange={(transport) => handleTransportChange(node, transport)}
                    onEdit={() => openEdit(node)}
                    onDelete={() => handleDelete(node)}
                    onProxyUpdated={() => void load()}
                  />
                ))}
                desktop={
                  <div className="overflow-x-auto rounded-lg border border-border/50">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead className="w-10 bg-muted/30">
                            <input
                              type="checkbox"
                              checked={
                                filteredNodes.length > 0 &&
                                filteredNodes.every((n) => selectedNodeIds.includes(n.id))
                              }
                              ref={(el) => {
                                if (el) {
                                  const selectedVisible = filteredNodes.filter((n) =>
                                    selectedNodeIds.includes(n.id),
                                  ).length
                                  el.indeterminate =
                                    selectedVisible > 0 && selectedVisible < filteredNodes.length
                                }
                              }}
                              onChange={() => {
                                const allVisibleSelected =
                                  filteredNodes.length > 0 &&
                                  filteredNodes.every((n) => selectedNodeIds.includes(n.id))
                                if (allVisibleSelected) {
                                  const visibleIds = new Set(filteredNodes.map((n) => n.id))
                                  setSelectedNodeIds((prev) =>
                                    prev.filter((id) => !visibleIds.has(id)),
                                  )
                                } else {
                                  setSelectedNodeIds((prev) => [
                                    ...new Set([...prev, ...filteredNodes.map((n) => n.id)]),
                                  ])
                                }
                              }}
                              aria-label="Выбрать все узлы"
                              className="h-4 w-4 rounded border"
                            />
                          </TableHead>
                          <TableHead className="bg-muted/30">Имя</TableHead>
                          <TableHead className="bg-muted/30">Адрес</TableHead>
                          <TableHead className="bg-muted/30">IP сервера</TableHead>
                          <TableHead className="bg-muted/30">Agent</TableHead>
                          <TableHead className="bg-muted/30">Службы</TableHead>
                          <TableHead className="bg-muted/30">Статус</TableHead>
                          <TableHead className="bg-muted/30">Тип</TableHead>
                          <TableHead className="bg-muted/30">Транспорт</TableHead>
                          <TableHead className="bg-muted/30 text-right">Действия</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredNodes.map((node) => {
                          const isActive = activeNode?.id === node.id
                          const meta = getNodeMeta(node)
                          const lastSeen = formatLastSeen(node.last_seen_at)
                          const address = node.is_local ? 'local' : `${node.host}:${node.port}`
                          const isProxy = isProxyNode(node)
                          const showProxyAffordance = proxyNodesEnabled && isProxy

                          return (
                            <Fragment key={node.id}>
                              <TableRow
                                className={cn(
                                  'border-l-2 border-l-transparent transition-colors',
                                  isActive && 'border-l-primary bg-primary/[0.06]',
                                  node.status === 'offline' && !isActive && 'bg-destructive/[0.03]',
                                )}
                              >
                                <TableCell>
                                  <input
                                    type="checkbox"
                                    checked={selectedNodeIds.includes(node.id)}
                                    onChange={() => toggleNodeSelection(node.id)}
                                    aria-label={`Выбрать ${node.name}`}
                                    className="h-4 w-4 rounded border"
                                  />
                                </TableCell>
                                <TableCell className="font-medium">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-[15px] font-semibold tracking-tight">
                                      {node.name}
                                    </span>
                                    {isProxy && (
                                      <Badge
                                        variant="outline"
                                        className="border-amber-500/40 text-[10px] text-amber-800 dark:text-amber-100"
                                      >
                                        Прокси
                                      </Badge>
                                    )}
                                    {isProxy && !proxyNodesEnabled && (
                                      <Badge variant="secondary" className="text-[10px]">
                                        модуль выкл
                                      </Badge>
                                    )}
                                    {showProxyAffordance && (
                                      <ProxyLinkBadge
                                        linkedVpnNodeId={node.linked_vpn_node_id}
                                        nodes={nodes}
                                        syncGroups={syncGroups}
                                        showUnlinked
                                      />
                                    )}
                                    {isActive && (
                                      <Badge variant="default" className="text-[10px]">
                                        <Check size={10} />
                                        активный
                                      </Badge>
                                    )}
                                  </div>
                                </TableCell>
                                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                                  {address}
                                </TableCell>
                                <TableCell className="font-mono text-xs tabular-nums">
                                  {meta.serverIp ?? '—'}
                                </TableCell>
                                <TableCell className="font-mono text-xs tabular-nums">
                                  {meta.agentVersion ?? '—'}
                                </TableCell>
                                <TableCell className="text-xs tabular-nums">
                                  {meta.servicesLabel ?? '—'}
                                </TableCell>
                                <TableCell>
                                  <NodeStatusBadge status={node.status} />
                                  {lastSeen && (
                                    <div className="mt-1 text-[10px] text-muted-foreground">
                                      {lastSeen}
                                    </div>
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
                                    isProxy={isProxy}
                                    healthLoading={healthLoading === node.id}
                                    activateLoading={activateLoading === node.id}
                                    onActivate={() => handleActivate(node)}
                                    onHealth={() => handleHealth(node)}
                                    onUpdate={() => setUpdateNodeTarget(node)}
                                    onRestart={() => handleRestartAgent(node)}
                                    onRotateKey={() => handleRotateKey(node)}
                                    onTransportChange={(transport) =>
                                      handleTransportChange(node, transport)
                                    }
                                    onEdit={() => openEdit(node)}
                                    onDelete={() => handleDelete(node)}
                                    compact
                                  />
                                </TableCell>
                              </TableRow>
                              {showProxyAffordance && (
                                <TableRow>
                                  <TableCell colSpan={10} className="bg-muted/20 py-3">
                                    <ProxyNodePanel
                                      node={node}
                                      nodes={nodes}
                                      syncGroups={syncGroups}
                                      onUpdated={() => void load()}
                                    />
                                  </TableCell>
                                </TableRow>
                              )}
                            </Fragment>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </div>
                }
                mobileClassName="space-y-4"
                desktopClassName="overflow-x-auto"
              />
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
        <DialogContent className={createTransport === 'ssh' && !editing ? 'max-w-xl' : 'max-w-md'}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {editing ? <Pencil size={18} /> : <Plus size={18} />}
              {editing ? 'Редактировать узел' : 'Добавить узел'}
            </DialogTitle>
            <DialogDescription>
              {editing
                ? editing.is_local
                  ? 'Можно изменить отображаемое имя локального узла'
                  : isProxyNode(editing)
                    ? 'Измените параметры подключения к proxy_agent'
                    : 'Измените параметры подключения к удалённому node agent'
                : proxyNodesEnabled && nodeKind === 'proxy'
                  ? 'Подключение к proxy_agent на RU-прокси'
                  : 'Подключение к node agent на VPN-сервере'}
            </DialogDescription>
          </DialogHeader>

          <form noValidate onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-4">
              {!editing && proxyNodesEnabled && (
                <div className="grid gap-2">
                  <Label htmlFor="node-kind">Тип узла</Label>
                  <Select
                    value={nodeKind}
                    onValueChange={(value) => handleNodeKindChange(value as NodeKind)}
                  >
                    <SelectTrigger id="node-kind">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="vpn">VPN (node agent)</SelectItem>
                      <SelectItem value="proxy">Прокси (proxy_agent)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
              {!editing && (
                <div className="grid gap-2">
                  <Label htmlFor="node-transport">Способ связи</Label>
                  <Select
                    value={createTransport}
                    onValueChange={(value) => {
                      const next = value as NodeTransportId
                      const opt = transportOptions.find((item) => item.id === next)
                      if (!opt?.available) return
                      setCreateTransport(next)
                      if (next === 'ssh') {
                        setCreateSshForm((prev) => ({
                          ...prev,
                          ssh_host: prev.ssh_host || host.trim(),
                        }))
                      }
                    }}
                    disabled={submitting}
                  >
                    <SelectTrigger id="node-transport">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {transportOptions.map((item) => (
                        <SelectItem
                          key={item.id}
                          value={item.id}
                          disabled={!item.available}
                          title={item.available ? item.label : 'Модуль отключён'}
                        >
                          {item.label}
                          {!item.available ? ' (выключено)' : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Как панель будет достучаться до агента. SSH — только при включённом модуле.
                  </p>
                </div>
              )}
              {!editing && nodeKind === 'vpn' && createTransport === 'http' && (
                <SettingsAlert variant="info">
                  Сначала на VPN-сервере установите и запустите <strong>node agent</strong> (
                  <code className="text-xs">systemctl start adminpanelaz-node</code>), затем укажите его{' '}
                  <strong>публичный IP или домен</strong> (не 127.0.0.1) и тот же API-ключ. Порт —{' '}
                  <strong>{VPN_DEFAULT_PORT}</strong>.
                </SettingsAlert>
              )}
              {!editing && nodeKind === 'vpn' && createTransport === 'mtls' && (
                <SettingsAlert variant="info">
                  После добавления панель попытается выдать сертификаты агенту по HTTP. Агент должен быть
                  уже доступен по адресу и ключу ниже; порт — <strong>{VPN_DEFAULT_PORT}</strong>.
                </SettingsAlert>
              )}
              {!editing && nodeKind === 'vpn' && createTransport === 'ssh' && (
                <SettingsAlert variant="info">
                  Агент лучше слушать на <strong>127.0.0.1:{VPN_DEFAULT_PORT}</strong>. В{' '}
                  <code className="text-xs">authorized_keys</code> SSH-пользователя добавьте публичный
                  ключ, парный приватному ключу ниже.{' '}
                  <a
                    href={NODE_SSH_TRANSPORT_DOCS_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium underline underline-offset-2"
                  >
                    Инструкция
                    <ExternalLink size={12} aria-hidden />
                  </a>
                </SettingsAlert>
              )}
              {!editing && proxyNodesEnabled && nodeKind === 'proxy' && (
                <SettingsAlert variant="warning" title="Прокси-узел">
                  Сначала сами установите{' '}
                  <a
                    href={AZ_PROXY_SH_DOCS_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium underline underline-offset-2"
                  >
                    proxy.sh по инструкции AntiZapret
                  </a>
                  , затем запустите <strong>proxy_agent</strong> (порт{' '}
                  <strong>{PROXY_DEFAULT_PORT}</strong>). Панель не ставит и не запускает proxy.sh.
                </SettingsAlert>
              )}
              {editing?.is_local && (
                <SettingsAlert variant="info">
                  Хост и порт локального узла задаются панелью. Меняется только{' '}
                  <strong>имя</strong> в списке и селекторе.
                </SettingsAlert>
              )}
              {editing && !editing.is_local && (
                <SettingsAlert variant="warning" title="API-ключ">
                  Оставьте поле ключа пустым, если не хотите его менять. Новый ключ нужно прописать в
                  конфигурации {isProxyNode(editing) ? 'proxy_agent' : 'node agent'} на сервере.
                </SettingsAlert>
              )}

              <div className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="node-name">Имя</Label>
                  <Input
                    id="node-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={
                      editing?.is_local
                        ? 'Локальный сервер'
                        : nodeKind === 'proxy'
                          ? 'proxy-ru-1'
                          : 'vpn-eu-1'
                    }
                  />
                  <p className="text-xs text-muted-foreground">Отображаемое имя в панели и селекторе узлов</p>
                </div>
                {!editing?.is_local && (
                  <>
                <div className="grid gap-2">
                  <Label htmlFor="node-host">Хост</Label>
                  <Input
                    id="node-host"
                    value={host}
                    onChange={(e) => {
                      const next = e.target.value
                      setHost(next)
                      if (!editing && createTransport === 'ssh' && !createSshForm.ssh_host.trim()) {
                        setCreateSshForm((prev) => ({ ...prev, ssh_host: next }))
                      }
                    }}
                    placeholder="vpn.example.com"
                  />
                  <p className="text-xs text-muted-foreground">
                    {createTransport === 'ssh' && !editing
                      ? 'Отображаемый адрес узла (может совпадать с SSH-хостом)'
                      : 'Домен или IP, доступный с controller'}
                  </p>
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
                  </>
                )}
                {!editing && createTransport === 'ssh' && (
                  <>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div className="grid gap-2">
                        <Label htmlFor="create-ssh-host">SSH-хост</Label>
                        <Input
                          id="create-ssh-host"
                          value={createSshForm.ssh_host}
                          onChange={(e) =>
                            setCreateSshForm((prev) => ({ ...prev, ssh_host: e.target.value }))
                          }
                          placeholder={host || '203.0.113.10'}
                          disabled={submitting}
                        />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="create-ssh-port">SSH-порт</Label>
                        <Input
                          id="create-ssh-port"
                          type="number"
                          min={1}
                          max={65535}
                          value={createSshForm.ssh_port}
                          onChange={(e) =>
                            setCreateSshForm((prev) => ({ ...prev, ssh_port: e.target.value }))
                          }
                          placeholder="22"
                          disabled={submitting}
                        />
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="create-ssh-username">SSH-пользователь</Label>
                      <Input
                        id="create-ssh-username"
                        value={createSshForm.ssh_username}
                        onChange={(e) =>
                          setCreateSshForm((prev) => ({ ...prev, ssh_username: e.target.value }))
                        }
                        placeholder="root"
                        disabled={submitting}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="create-ssh-private-key">Приватный SSH-ключ</Label>
                      <Textarea
                        id="create-ssh-private-key"
                        value={createSshForm.ssh_private_key}
                        onChange={(e) =>
                          setCreateSshForm((prev) => ({ ...prev, ssh_private_key: e.target.value }))
                        }
                        placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                        className="min-h-40 font-mono text-xs"
                        disabled={submitting}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="create-ssh-passphrase">Passphrase ключа</Label>
                      <Input
                        id="create-ssh-passphrase"
                        type="password"
                        value={createSshForm.ssh_passphrase}
                        onChange={(e) =>
                          setCreateSshForm((prev) => ({ ...prev, ssh_passphrase: e.target.value }))
                        }
                        placeholder="Необязательно"
                        disabled={submitting}
                      />
                    </div>
                  </>
                )}
                {((editing && isProxyNode(editing)) ||
                  (!editing && proxyNodesEnabled && nodeKind === 'proxy')) && (
                  <ProxyLinkSelect
                    value={linkSelectorValue}
                    onChange={setLinkSelectorValue}
                    nodes={nodes}
                    syncGroups={syncGroups}
                    disabled={submitting}
                    orphanNodeId={editing?.linked_vpn_node_id ?? null}
                  />
                )}
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
        open={!!sshDialogNode}
        onOpenChange={(open) => {
          if (!open && !sshSubmitting) closeSshDialog()
        }}
        title="Переключить на SSH?"
        description={
          sshDialogNode ? (
            <>
              Узел: <strong>{sshDialogNode.name}</strong>
            </>
          ) : undefined
        }
        alert={{
          variant: 'info',
          title: 'Туннель от controller к agent',
          children: (
            <>
              Панель подключится по SSH к серверу и будет обращаться к node agent через туннель.
              Внутренний адрес agent по умолчанию — 127.0.0.1 и текущий порт узла.{' '}
              <a
                href={NODE_SSH_TRANSPORT_DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-2"
              >
                Инструкция
                <ExternalLink size={12} aria-hidden />
              </a>
            </>
          ),
        }}
        confirmLabel="Сохранить SSH"
        loading={sshSubmitting}
        onConfirm={handleSshSubmit}
        className="max-w-xl"
      >
        <div className="grid gap-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="ssh-host">SSH-хост</Label>
              <Input
                id="ssh-host"
                value={sshForm.ssh_host}
                onChange={(e) => setSshForm((prev) => ({ ...prev, ssh_host: e.target.value }))}
                placeholder={sshDialogNode?.host || '203.0.113.10'}
                disabled={sshSubmitting}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ssh-port">SSH-порт</Label>
              <Input
                id="ssh-port"
                type="number"
                min={1}
                max={65535}
                value={sshForm.ssh_port}
                onChange={(e) => setSshForm((prev) => ({ ...prev, ssh_port: e.target.value }))}
                placeholder="22"
                disabled={sshSubmitting}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="ssh-username">SSH-пользователь</Label>
            <Input
              id="ssh-username"
              value={sshForm.ssh_username}
              onChange={(e) => setSshForm((prev) => ({ ...prev, ssh_username: e.target.value }))}
              placeholder="root"
              disabled={sshSubmitting}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="ssh-private-key">Приватный ключ</Label>
            <Textarea
              id="ssh-private-key"
              value={sshForm.ssh_private_key}
              onChange={(e) => setSshForm((prev) => ({ ...prev, ssh_private_key: e.target.value }))}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
              className="min-h-40 font-mono text-xs"
              disabled={sshSubmitting}
            />
            <p className="text-xs text-muted-foreground">
              {sshDialogNode?.ssh_key_configured
                ? 'Ключ уже сохранён. Оставьте поле пустым, если не хотите его менять.'
                : 'Ключ обязателен для первого переключения на SSH transport.'}
            </p>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="ssh-passphrase">Passphrase ключа</Label>
            <Input
              id="ssh-passphrase"
              type="password"
              value={sshForm.ssh_passphrase}
              onChange={(e) => setSshForm((prev) => ({ ...prev, ssh_passphrase: e.target.value }))}
              placeholder="Необязательно"
              disabled={sshSubmitting}
            />
          </div>
        </div>
      </ConfirmDialog>

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
                ? confirmTarget && isProxyNode(confirmTarget)
                  ? 'Отметить mTLS?'
                  : 'Включить mTLS?'
                : confirmAction === 'disable-mtls'
                  ? 'Сбросить mTLS в панели?'
                  : confirmAction === 'restart-agent'
                    ? 'Перезапустить node agent?'
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
                ? confirmTarget && isProxyNode(confirmTarget)
                  ? {
                      variant: 'info',
                      title: 'Только флаг в панели',
                      children:
                        'Панель начнёт ходить к proxy_agent по HTTPS. Сертификаты на RU-прокси ставятся вручную (docs/proxy-agent.md) — панель их не provision’ит.',
                    }
                  : {
                      variant: 'warning',
                      title: 'Перезапуск node agent',
                      children:
                        'Будет сгенерирован сертификат, node agent перезапустится ~5–30 сек. Связь может кратковременно прерваться.',
                    }
                : confirmAction === 'disable-mtls'
                  ? {
                      variant: 'warning',
                      title: 'Только флаг в панели',
                      children:
                        confirmTarget && isProxyNode(confirmTarget)
                          ? 'Сбрасывается флаг mTLS в базе панели. proxy_agent может продолжать работать с mTLS — для полного отключения настройте узел вручную.'
                          : 'Сбрасывается флаг mTLS в базе панели. Node agent может продолжать работать с mTLS — для полного отключения настройте узел вручную.',
                    }
                  : confirmAction === 'restart-agent'
                    ? {
                        variant: 'warning',
                        title: 'Кратковременный разрыв связи',
                        children:
                          'Node agent перезапустится через несколько секунд (~5–30 сек). VPN-службы на узле не затрагиваются.',
                      }
                    : undefined
        }
        confirmLabel={
          confirmAction === 'delete'
            ? 'Удалить'
            : confirmAction === 'rotate-key'
              ? 'Сгенерировать ключ'
              : confirmAction === 'enable-mtls'
                ? confirmTarget && isProxyNode(confirmTarget)
                  ? 'Отметить mTLS'
                  : 'Включить mTLS'
                : confirmAction === 'disable-mtls'
                  ? 'Сбросить mTLS'
                  : confirmAction === 'restart-agent'
                    ? 'Перезапустить'
                    : 'Подтвердить'
        }
        destructive={confirmAction === 'delete'}
        loading={confirmLoading}
        onConfirm={handleConfirm}
      />

      <ConfirmDialog
        open={!!bulkConfirmAction}
        onOpenChange={(open) => {
          if (!open && !confirmLoading) closeBulkConfirm()
        }}
        title={
          bulkConfirmAction === 'delete'
            ? `Удалить ${getSelectedNodes(nodes, selectedNodeIds).filter((n) => !n.is_local).length} узл(ов)?`
            : bulkConfirmAction === 'enable-mtls'
              ? `Включить mTLS на ${
                  getSelectedNodes(nodes, selectedNodeIds).filter(
                    (n) =>
                      !n.is_local &&
                      !isProxyNode(n) &&
                      (n.transport || (n.mtls_enabled ? 'mtls' : 'http')) !== 'mtls',
                  ).length
                } узл(ах)?`
              : ''
        }
        description={
          bulkConfirmAction === 'delete' ? (
            <>
              Будут удалены только <strong>удалённые</strong> узлы из выбранных. Локальный сервер не
              затрагивается.
            </>
          ) : bulkConfirmAction === 'enable-mtls' ? (
            <>
              Node agent на каждом узле будет перезапущен (~5–30 сек). Связь может кратковременно
              прерваться.
            </>
          ) : undefined
        }
        alert={
          bulkConfirmAction === 'delete'
            ? {
                variant: 'danger',
                title: 'Необратимое действие',
                children:
                  'Узлы будут удалены из панели. Конфигурация VPN на серверах не затрагивается.',
              }
            : bulkConfirmAction === 'enable-mtls'
              ? {
                  variant: 'warning',
                  title: 'Перезапуск node agent',
                  children:
                    'Операция выполняется последовательно для каждого выбранного узла без mTLS.',
                }
              : undefined
        }
        confirmLabel={
          bulkConfirmAction === 'delete'
            ? 'Удалить выбранные'
            : bulkConfirmAction === 'enable-mtls'
              ? 'Включить mTLS'
              : 'Подтвердить'
        }
        destructive={bulkConfirmAction === 'delete'}
        loading={confirmLoading}
        onConfirm={handleBulkConfirm}
      />

      <ConfirmDialog
        open={haDeleteBlockedNodes.length > 0}
        onOpenChange={(open) => {
          if (!open) setHaDeleteBlockedNodes([])
        }}
        title={
          haDeleteBlockedNodes.length === 1
            ? 'Невозможно удалить узел'
            : 'Невозможно удалить выбранные узлы'
        }
        description={
          haDeleteBlockedNodes.length === 1 ? (
            <>
              Узел: <strong>{haDeleteBlockedNodes[0]?.name}</strong>
            </>
          ) : (
            <>Узлов в HA-группе: {haDeleteBlockedNodes.length}</>
          )
        }
        alert={{
          variant: 'warning',
          title: 'Узел в группе синхронизации',
          children: (
            <div className="space-y-3 text-sm leading-relaxed">
              <ul className="list-disc space-y-1 pl-4">
                {haDeleteBlockedNodes.map((node) => {
                  const membership = findNodeHaMembership(node.id, syncGroups)
                  return (
                    <li key={node.id}>
                      <strong>{node.name}</strong>
                      {membership ? ` — группа «${membership.groupName}»` : null}
                    </li>
                  )
                })}
              </ul>
              <p>{nodeHaDeleteBlockedHint()}</p>
            </div>
          ),
        }}
        confirmHidden
        onConfirm={() => setHaDeleteBlockedNodes([])}
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
