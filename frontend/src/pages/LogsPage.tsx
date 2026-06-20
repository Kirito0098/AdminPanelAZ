import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ArrowDownToLine,
  ClipboardList,
  Copy,
  Download,
  Filter,
  Hash,
  ListOrdered,
  QrCode,
  Radio,
  ScrollText,
  Search,
  Wifi,
  WifiOff,
  Plug,
} from 'lucide-react'
import {
  ApiError,
  downloadActionLogsExport,
  getActionLogs,
  getConnectionLogs,
  getOpenVpnEvents,
  getOpenVpnSockets,
  getQrDownloadLogs,
} from '@/api/client'
import { NodeBadge } from '@/components/NodeSelector'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { formatDateTime } from '@/lib/datetime'
import { COL_HANDSHAKE, COL_REAL_IP, COL_VPN_IP, connectionSourceLabel } from '@/lib/uiLabels'
import { cn } from '@/lib/utils'
import { isWireGuardOnline } from '@/lib/wireguardStatus'
import type {
  ActionLogEntry,
  ConnectionLogsSnapshot,
  OpenVpnEventProfile,
  OpenVpnSocketStatus,
  QrDownloadAuditEntry,
} from '@/types'

const REFRESH_INTERVAL = 30

const LOG_PAGE_SIZE = 100

type LogLevel = 'all' | 'error' | 'warn' | 'info'

function dataSourceLabel(source?: string) {
  if (source === 'management_socket') return connectionSourceLabel('management_socket')
  if (source === 'status_log') return 'Status-логи'
  return 'Нет данных'
}

function dataSourceVariant(source?: string): 'default' | 'secondary' | 'outline' {
  if (source === 'management_socket') return 'default'
  if (source === 'status_log') return 'secondary'
  return 'outline'
}

function detectLogLevel(line: string): 'error' | 'warn' | 'info' | null {
  const upper = line.toUpperCase()
  if (/\b(ERROR|ERRO|FATAL|CRITICAL|CRIT)\b/.test(upper)) return 'error'
  if (/\b(WARN|WARNING)\b/.test(upper)) return 'warn'
  if (/\b(INFO)\b/.test(upper)) return 'info'
  return null
}

const levelLineStyles: Record<'error' | 'warn' | 'info', string> = {
  error: 'text-red-400',
  warn: 'text-amber-400',
  info: 'text-sky-400',
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function copyText(text: string) {
  await navigator.clipboard.writeText(text)
}

type LogViewerProps = {
  lines: string[]
  emptyTitle: string
  emptyDescription?: string
  profileName?: string
}

function LogViewer({ lines, emptyTitle, emptyDescription, profileName }: LogViewerProps) {
  const { success, error: notifyError } = useNotifications()
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevel>('all')
  const [showLineNumbers, setShowLineNumbers] = useState(true)
  const [followTail, setFollowTail] = useState(true)
  const [page, setPage] = useState(0)
  const logEndRef = useRef<HTMLDivElement>(null)
  const logContainerRef = useRef<HTMLDivElement>(null)

  const filteredLines = useMemo(() => {
    const q = search.trim().toLowerCase()
    return lines.filter((line) => {
      const level = detectLogLevel(line)
      if (levelFilter === 'error' && level !== 'error') return false
      if (levelFilter === 'warn' && level !== 'warn') return false
      if (levelFilter === 'info' && level !== 'info') return false
      if (q && !line.toLowerCase().includes(q)) return false
      return true
    })
  }, [lines, search, levelFilter])

  const totalPages = Math.max(1, Math.ceil(filteredLines.length / LOG_PAGE_SIZE))
  const safePage = Math.min(page, totalPages - 1)
  const pageLines = filteredLines.slice(safePage * LOG_PAGE_SIZE, (safePage + 1) * LOG_PAGE_SIZE)
  const lineOffset = safePage * LOG_PAGE_SIZE

  useEffect(() => {
    setPage(0)
  }, [search, levelFilter, lines.length])

  useEffect(() => {
    if (!followTail || filteredLines.length === 0) return
    const lastPage = Math.max(0, Math.ceil(filteredLines.length / LOG_PAGE_SIZE) - 1)
    setPage(lastPage)
    requestAnimationFrame(() => {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    })
  }, [followTail, filteredLines])

  const handleCopy = async () => {
    if (filteredLines.length === 0) return
    try {
      await copyText(filteredLines.join('\n'))
      success('Логи скопированы в буфер обмена')
    } catch {
      notifyError('Не удалось скопировать логи')
    }
  }

  const handleDownload = () => {
    if (filteredLines.length === 0) return
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    const name = profileName ? `openvpn-${profileName}-${stamp}.log` : `openvpn-events-${stamp}.log`
    downloadText(name, filteredLines.join('\n'))
    success('Файл логов загружен')
  }

  if (lines.length === 0) {
    return (
      <EmptyState
        icon={ScrollText}
        title={emptyTitle}
        description={emptyDescription}
        className="py-10"
      />
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 rounded-lg border bg-card p-3 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="relative min-w-[12rem] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск по строкам..."
            className="pl-9"
          />
        </div>
        <Select value={levelFilter} onValueChange={(v) => setLevelFilter(v as LogLevel)}>
          <SelectTrigger className="w-full sm:w-[10rem]">
            <Filter size={14} className="mr-1 shrink-0 text-muted-foreground" />
            <SelectValue placeholder="Уровень" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все уровни</SelectItem>
            <SelectItem value="error">ERROR</SelectItem>
            <SelectItem value="warn">WARN</SelectItem>
            <SelectItem value="info">INFO</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={showLineNumbers ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setShowLineNumbers((v) => !v)}
            title="Номера строк"
          >
            <ListOrdered size={14} />
            №
          </Button>
          <Button
            type="button"
            variant={followTail ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setFollowTail((v) => !v)}
            title="Следовать за хвостом лога"
          >
            <ArrowDownToLine size={14} />
            Хвост
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleCopy} disabled={filteredLines.length === 0}>
            <Copy size={14} />
            Копировать
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownload}
            disabled={filteredLines.length === 0}
          >
            <Download size={14} />
            Скачать
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {filteredLines.length} из {lines.length} строк
          {search || levelFilter !== 'all' ? ' (отфильтровано)' : ''}
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safePage <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Назад
            </Button>
            <span className="mono tabular-nums">
              {safePage + 1} / {totalPages}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={safePage >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            >
              Вперёд
            </Button>
          </div>
        )}
      </div>

      {filteredLines.length === 0 ? (
        <EmptyState
          icon={Filter}
          title="Нет совпадений"
          description="Измените поиск или фильтр уровня логов"
          className="py-8"
        />
      ) : (
        <div
          ref={logContainerRef}
          className="max-h-[28rem] overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 font-mono text-xs leading-relaxed"
        >
          {pageLines.map((line, idx) => {
            const lineNum = lineOffset + idx + 1
            const level = detectLogLevel(line)
            return (
              <div
                key={`${lineNum}-${line.slice(0, 24)}`}
                className="flex gap-3 hover:bg-zinc-900/60"
              >
                {showLineNumbers && (
                  <span className="w-8 shrink-0 select-none text-right text-zinc-600 tabular-nums">
                    {lineNum}
                  </span>
                )}
                <span
                  className={cn(
                    'min-w-0 flex-1 whitespace-pre-wrap break-all',
                    level ? levelLineStyles[level] : 'text-zinc-300',
                  )}
                >
                  {line}
                </span>
              </div>
            )
          })}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  )
}

type ConnectionClientCardProps = {
  name: string
  realIp: string
  vpnIp: string
}

function ConnectionClientCard({ name, realIp, vpnIp }: ConnectionClientCardProps) {
  return (
    <div className="rounded-lg border p-3">
      <p className="font-medium">{name}</p>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-muted-foreground">{COL_REAL_IP}</p>
          <p className="font-mono">{realIp}</p>
        </div>
        <div>
          <p className="text-muted-foreground">{COL_VPN_IP}</p>
          <p className="font-mono">{vpnIp}</p>
        </div>
      </div>
    </div>
  )
}

type WireGuardPeerCardProps = {
  name: string
  handshake: string
}

function WireGuardPeerCard({ name, handshake }: WireGuardPeerCardProps) {
  return (
    <div className="rounded-lg border p-3">
      <p className="font-medium">{name}</p>
      <div className="mt-2 text-xs">
        <p className="text-muted-foreground">{COL_HANDSHAKE}</p>
        <p>{handshake}</p>
      </div>
    </div>
  )
}

type ActionLogCardProps = {
  entry: ActionLogEntry
}

function ActionLogCard({ entry }: ActionLogCardProps) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge variant="secondary">{entry.action}</Badge>
        <span className="text-xs text-muted-foreground">
          {formatDateTime(entry.created_at)}
        </span>
      </div>
      <p className="mt-2 text-sm font-medium">{entry.username || '—'}</p>
      {entry.details && (
        <p className="mt-1 break-words text-xs text-muted-foreground">{entry.details}</p>
      )}
    </div>
  )
}

export default function LogsPage() {
  const { user } = useAuth()
  const { isEnabled } = useFeatureModules()
  const logsDashboardEnabled = isEnabled('logs_dashboard')
  const actionLogsEnabled = isEnabled('action_logs')
  const qrDownloadsEnabled = isEnabled('qr_downloads')
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal } = useProgress()
  const [actions, setActions] = useState<ActionLogEntry[]>([])
  const [connections, setConnections] = useState<ConnectionLogsSnapshot | null>(null)
  const [events, setEvents] = useState<OpenVpnEventProfile[]>([])
  const [qrDownloads, setQrDownloads] = useState<QrDownloadAuditEntry[]>([])
  const [openVpnSockets, setOpenVpnSockets] = useState<OpenVpnSocketStatus[]>([])
  const [socketsTimestamp, setSocketsTimestamp] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const [selectedProfile, setSelectedProfile] = useState<string>('all')
  const [actionSearch, setActionSearch] = useState('')
  const [exportingActions, setExportingActions] = useState(false)
  const actionsLoadedRef = useRef(false)

  const load = useCallback(
    async (manual = false, initial = false) => {
      if (initial) {
        setLoading(true)
        startGlobal()
      } else if (manual) {
        setRefreshing(true)
      }
      try {
        const connPromise = logsDashboardEnabled ? getConnectionLogs() : Promise.resolve(null)
        const evtPromise = logsDashboardEnabled ? getOpenVpnEvents() : Promise.resolve({ profiles: [] })
        const qrPromise =
          user?.role === 'admin' && qrDownloadsEnabled
            ? getQrDownloadLogs()
            : Promise.resolve([])
        const socketsPromise =
          user?.role === 'admin' && logsDashboardEnabled
            ? getOpenVpnSockets()
            : Promise.resolve(null)
        const [conn, evt, qr, sockets] = await Promise.all([
          connPromise,
          evtPromise,
          qrPromise,
          socketsPromise,
        ])
        if (conn) setConnections(conn)
        setEvents(evt.profiles)
        setQrDownloads(qr)
        if (sockets) {
          setOpenVpnSockets(sockets.sockets)
          setSocketsTimestamp(sockets.timestamp)
        }
        setLoadError(null)
        if (user?.role === 'admin' && actionLogsEnabled && !actionsLoadedRef.current) {
          setActions(await getActionLogs())
          actionsLoadedRef.current = true
        }
        setCountdown(REFRESH_INTERVAL)
        if (manual) success('Логи обновлены')
      } catch (err) {
        const message = err instanceof ApiError ? err.message : 'Ошибка загрузки логов'
        setLoadError(message)
        notifyError(message)
      } finally {
        setLoading(false)
        setRefreshing(false)
        if (initial) doneGlobal()
      }
    },
    [user?.role, notifyError, success, startGlobal, doneGlobal, logsDashboardEnabled, actionLogsEnabled, qrDownloadsEnabled],
  )

  useEffect(() => {
    load(false, true)
  }, [load, activeNode?.id])

  useEffect(() => {
    if (!autoRefresh) return
    const tick = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          load()
          return REFRESH_INTERVAL
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(tick)
  }, [autoRefresh, load])

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'

  const openvpnClients = connections?.openvpn_clients ?? []
  const wireguardPeers = connections?.wireguard_peers ?? []
  const activeWireguardPeers = useMemo(
    () => wireguardPeers.filter(isWireGuardOnline),
    [wireguardPeers],
  )
  const totalConnections = openvpnClients.length + activeWireguardPeers.length

  const activeEvents = useMemo(() => events.filter((p) => p.exists), [events])

  const selectedEventProfile = useMemo(() => {
    if (selectedProfile === 'all') return null
    return activeEvents.find((p) => p.profile === selectedProfile) ?? null
  }, [activeEvents, selectedProfile])

  const eventLines = useMemo(() => {
    if (selectedEventProfile) return selectedEventProfile.recent_lines
    return activeEvents.flatMap((p) => p.recent_lines)
  }, [activeEvents, selectedEventProfile])

  useEffect(() => {
    if (selectedProfile === 'all') return
    if (!activeEvents.some((p) => p.profile === selectedProfile)) {
      setSelectedProfile('all')
    }
  }, [activeEvents, selectedProfile])

  const filteredActions = useMemo(() => {
    const q = actionSearch.trim().toLowerCase()
    if (!q) return actions
    return actions.filter(
      (a) =>
        (a.username ?? '').toLowerCase().includes(q) ||
        a.action.toLowerCase().includes(q) ||
        (a.details ?? '').toLowerCase().includes(q),
    )
  }, [actions, actionSearch])

  const handleRefresh = () => load(true)

  const handleExportActions = async () => {
    setExportingActions(true)
    try {
      const res = await downloadActionLogsExport()
      if (!res.ok) {
        let detail = 'Ошибка экспорта журнала'
        try {
          const data = await res.json()
          detail = typeof data.detail === 'string' ? data.detail : detail
        } catch {
          /* non-JSON error body */
        }
        throw new ApiError(detail, res.status)
      }
      const blob = await res.blob()
      const disposition = res.headers.get('Content-Disposition') ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      const filename = match?.[1] ?? `action-logs-${new Date().toISOString().slice(0, 10)}.csv`
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      a.click()
      URL.revokeObjectURL(a.href)
      success('Журнал действий экспортирован')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка экспорта журнала')
    } finally {
      setExportingActions(false)
    }
  }

  const defaultLogTab = logsDashboardEnabled ? 'connections' : 'actions'
  const showConnectionTabs = logsDashboardEnabled
  const showActionTab = user?.role === 'admin' && actionLogsEnabled
  const showQrDownloadsTab = user?.role === 'admin' && qrDownloadsEnabled
  const showSocketsTab = user?.role === 'admin' && logsDashboardEnabled

  const [searchParams] = useSearchParams()
  const initialLogTab = useMemo(() => {
    const tab = searchParams.get('tab')
    if (tab === 'qr-downloads' && showQrDownloadsTab) return tab
    if (tab === 'openvpn-sockets' && showSocketsTab) return tab
    if (tab === 'actions' && showActionTab) return tab
    if ((tab === 'connections' || tab === 'openvpn-events') && showConnectionTabs) return tab
    return defaultLogTab
  }, [
    searchParams,
    showQrDownloadsTab,
    showSocketsTab,
    showActionTab,
    showConnectionTabs,
    defaultLogTab,
  ])

  if (loading && !connections && events.length === 0 && actions.length === 0) {
    return <Spinner label="Загрузка логов..." className="py-16" />
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ScrollText size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Журналы</h2>
              <NodeBadge name={activeNode?.name} status={activeNode?.status} />
            </div>
            <p className="text-sm text-muted-foreground">
              Подключения, события OpenVPN, аудит QR и действия администраторов
              {connections?.timestamp && (
                <> · обновлено {formatDateTime(connections.timestamp)}</>
              )}
            </p>
          </div>
        </div>
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={() => setAutoRefresh((v) => !v)}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onManualRefresh={handleRefresh}
        />
      </div>

      <SettingsAlert variant="info" title="Данные активного узла">
        Логи собираются с <strong>{activeNode?.name ?? 'активного узла'}</strong>
        {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'}.
        Переключите узел в шапке или на странице «Узлы», чтобы смотреть другой сервер.
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Логи подключений и событий могут быть устаревшими или отсутствовать.
          Проверьте связь с node agent и повторите обновление.
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar active={refreshing} label="Обновление логов..." />

      {loadError && !connections && events.length === 0 ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={WifiOff}
              title="Логи недоступны"
              description={loadError}
              action={
                <Button onClick={handleRefresh} disabled={refreshing}>
                  Обновить
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <Tabs defaultValue={initialLogTab} key={initialLogTab}>
          <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1">
            {showConnectionTabs && (
            <TabsTrigger value="connections" className="gap-1.5">
              <Wifi size={14} />
              Подключения
              {totalConnections > 0 && (
                <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                  {totalConnections}
                </Badge>
              )}
            </TabsTrigger>
            )}
            {showConnectionTabs && (
            <TabsTrigger value="openvpn-events" className="gap-1.5">
              <Radio size={14} />
              OpenVPN события
              {events.length > 0 && (
                <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                  {events.length}
                </Badge>
              )}
            </TabsTrigger>
            )}
            {showActionTab && (
              <TabsTrigger value="actions" className="gap-1.5">
                <ClipboardList size={14} />
                Действия
                {actions.length > 0 && (
                  <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                    {actions.length}
                  </Badge>
                )}
              </TabsTrigger>
            )}
            {showQrDownloadsTab && (
              <TabsTrigger value="qr-downloads" className="gap-1.5">
                <QrCode size={14} />
                QR-скачивания
                {qrDownloads.length > 0 && (
                  <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                    {qrDownloads.length}
                  </Badge>
                )}
              </TabsTrigger>
            )}
            {showSocketsTab && (
              <TabsTrigger value="openvpn-sockets" className="gap-1.5">
                <Plug size={14} />
                OVPN сокеты
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="connections" className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={dataSourceVariant(connections?.openvpn_data_source)}>
                Источник OVPN: {dataSourceLabel(connections?.openvpn_data_source)}
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Hash size={10} />
                OpenVPN: {openvpnClients.length}
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Hash size={10} />
                WireGuard: {activeWireguardPeers.length}
                {wireguardPeers.length > activeWireguardPeers.length && (
                  <> / {wireguardPeers.length}</>
                )}
              </Badge>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Wifi size={16} />
                    OpenVPN
                  </CardTitle>
                  <CardDescription>{openvpnClients.length} активных сессий</CardDescription>
                </CardHeader>
                <CardContent>
                  {openvpnClients.length === 0 ? (
                    <EmptyState
                      icon={WifiOff}
                      title="Нет активных подключений"
                      description="Клиенты OpenVPN появятся здесь после установления VPN-сессии"
                      className="py-8"
                    />
                  ) : (
                    <>
                      <div className="hidden overflow-x-auto md:block">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Клиент</TableHead>
                              <TableHead>{COL_REAL_IP}</TableHead>
                              <TableHead>{COL_VPN_IP}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {openvpnClients.map((c) => (
                              <TableRow key={`${c.common_name}-${c.real_address}`}>
                                <TableCell>{c.common_name}</TableCell>
                                <TableCell className="font-mono text-xs">{c.real_address}</TableCell>
                                <TableCell className="font-mono text-xs">{c.virtual_address}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                      <div className="space-y-2 md:hidden">
                        {openvpnClients.map((c) => (
                          <ConnectionClientCard
                            key={`${c.common_name}-${c.real_address}`}
                            name={c.common_name}
                            realIp={c.real_address}
                            vpnIp={c.virtual_address}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Wifi size={16} />
                    WireGuard
                  </CardTitle>
                  <CardDescription>
                    {activeWireguardPeers.length} онлайн
                    {wireguardPeers.length > activeWireguardPeers.length &&
                      ` из ${wireguardPeers.length} пиров`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {activeWireguardPeers.length === 0 ? (
                    <EmptyState
                      icon={WifiOff}
                      title="Нет активных пиров WireGuard"
                      description="Пиры с недавним handshake отобразятся здесь"
                      className="py-8"
                    />
                  ) : (
                    <>
                      <div className="hidden overflow-x-auto md:block">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Клиент</TableHead>
                              <TableHead>{COL_HANDSHAKE}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {activeWireguardPeers.map((p) => (
                              <TableRow key={p.public_key}>
                                <TableCell>{String(p.client_name || '—')}</TableCell>
                                <TableCell className="text-xs">
                                  {p.latest_handshake
                                    ? formatDateTime(p.latest_handshake)
                                    : '—'}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                      <div className="space-y-2 md:hidden">
                        {activeWireguardPeers.map((p) => (
                          <WireGuardPeerCard
                            key={p.public_key}
                            name={String(p.client_name || '—')}
                            handshake={
                              p.latest_handshake
                                ? formatDateTime(p.latest_handshake)
                                : '—'
                            }
                          />
                        ))}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="openvpn-events" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">События management interface</CardTitle>
                <CardDescription>
                  Хвост логов из Unix-сокетов OpenVPN на активном узле
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {activeEvents.length === 0 ? (
                  <EmptyState
                    icon={Radio}
                    title="Нет активных профилей OpenVPN"
                    description={
                      nodeOffline
                        ? 'Узел офлайн — события management interface недоступны'
                        : 'Профили появятся, когда запущены сервисы OpenVPN с management socket'
                    }
                    className="py-10"
                  />
                ) : (
                  <>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <Select value={selectedProfile} onValueChange={setSelectedProfile}>
                        <SelectTrigger className="w-full sm:w-[16rem]">
                          <SelectValue placeholder="Профиль" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Все профили</SelectItem>
                          {activeEvents.map((p) => (
                            <SelectItem key={p.profile} value={p.profile}>
                              {p.profile}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {selectedEventProfile && (
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <Badge variant="default">
                            {selectedEventProfile.line_count > 0
                              ? `${selectedEventProfile.line_count} строк`
                              : 'Нет событий'}
                          </Badge>
                          <span>{selectedEventProfile.source_name}</span>
                        </div>
                      )}
                    </div>

                    {selectedProfile === 'all' ? (
                      <div className="space-y-4">
                        {activeEvents.map((profile) => (
                          <div key={profile.profile} className="rounded-lg border p-4">
                            <div className="mb-3 flex flex-wrap items-center gap-2">
                              <span className="font-medium">{profile.profile}</span>
                              <Badge variant="default">
                                {profile.line_count > 0 ? `${profile.line_count} строк` : 'Нет событий'}
                              </Badge>
                              <span className="text-xs text-muted-foreground">{profile.source_name}</span>
                            </div>
                            <LogViewer
                              lines={profile.recent_lines}
                              emptyTitle="Нет событий"
                              emptyDescription="Сокет доступен, но новых строк пока нет"
                              profileName={profile.profile}
                            />
                          </div>
                        ))}
                      </div>
                    ) : selectedEventProfile ? (
                      <LogViewer
                        lines={eventLines}
                        emptyTitle="Нет событий"
                        emptyDescription="Сокет доступен, но новых строк пока нет"
                        profileName={selectedEventProfile.profile}
                      />
                    ) : null}
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {user?.role === 'admin' && (
            <TabsContent value="actions" className="space-y-4">
              <Card>
                <CardHeader>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <ClipboardList size={16} />
                        Журнал действий
                      </CardTitle>
                      <CardDescription>Последние операции администраторов панели</CardDescription>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      onClick={() => void handleExportActions()}
                      disabled={exportingActions}
                    >
                      <Download size={14} />
                      {exportingActions ? 'Экспорт…' : 'Экспорт CSV'}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="relative max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={actionSearch}
                      onChange={(e) => setActionSearch(e.target.value)}
                      placeholder="Поиск по пользователю, действию, деталям..."
                      className="pl-9"
                    />
                  </div>

                  {actions.length === 0 ? (
                    <EmptyState
                      icon={ClipboardList}
                      title="Журнал пуст"
                      description="Действия администраторов появятся здесь после первых операций в панели"
                      className="py-10"
                    />
                  ) : filteredActions.length === 0 ? (
                    <EmptyState
                      icon={Search}
                      title="Нет совпадений"
                      description="Измените поисковый запрос"
                      className="py-8"
                    />
                  ) : (
                    <>
                      <div className="hidden overflow-x-auto md:block">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Время</TableHead>
                              <TableHead>Пользователь</TableHead>
                              <TableHead>Действие</TableHead>
                              <TableHead>Детали</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {filteredActions.map((a) => (
                              <TableRow key={a.id}>
                                <TableCell className="text-xs whitespace-nowrap">
                                  {formatDateTime(a.created_at)}
                                </TableCell>
                                <TableCell>{a.username || '—'}</TableCell>
                                <TableCell>
                                  <Badge variant="secondary">{a.action}</Badge>
                                </TableCell>
                                <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                                  {a.details}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                      <div className="space-y-2 md:hidden">
                        {filteredActions.map((a) => (
                          <ActionLogCard key={a.id} entry={a} />
                        ))}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {showQrDownloadsTab && (
            <TabsContent value="qr-downloads" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <QrCode size={16} />
                    Аудит QR-скачиваний
                  </CardTitle>
                  <CardDescription>
                    События одноразовых ссылок и скачиваний конфигов клиентами
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {qrDownloads.length === 0 ? (
                    <EmptyState
                      icon={QrCode}
                      title="Событий нет"
                      description="Записи появятся после первых скачиваний по одноразовым ссылкам"
                      className="py-10"
                    />
                  ) : (
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Время</TableHead>
                            <TableHead>Событие</TableHead>
                            <TableHead>Пользователь</TableHead>
                            <TableHead>IP</TableHead>
                            <TableHead>Детали</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {qrDownloads.map((entry) => (
                            <TableRow key={entry.id}>
                              <TableCell className="text-xs whitespace-nowrap">
                                {formatDateTime(entry.created_at)}
                              </TableCell>
                              <TableCell>
                                <Badge variant="secondary">{entry.event_type}</Badge>
                              </TableCell>
                              <TableCell>{entry.actor_username || '—'}</TableCell>
                              <TableCell className="font-mono text-xs">{entry.remote_addr || '—'}</TableCell>
                              <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                                {entry.details || '—'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}

          {showSocketsTab && (
            <TabsContent value="openvpn-sockets" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Plug size={16} />
                    OpenVPN management sockets
                  </CardTitle>
                  <CardDescription>
                    Диагностика Unix-сокетов для событий OpenVPN на активном узле
                    {socketsTimestamp && (
                      <> · обновлено {formatDateTime(socketsTimestamp)}</>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {openVpnSockets.length === 0 ? (
                    <EmptyState
                      icon={Plug}
                      title="Нет данных о сокетах"
                      description="Проверьте связь с узлом и обновите страницу"
                      className="py-10"
                    />
                  ) : (
                    <div className="overflow-x-auto rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Профиль</TableHead>
                            <TableHead>Путь сокета</TableHead>
                            <TableHead>Файл</TableHead>
                            <TableHead>Ответ</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {openVpnSockets.map((socket) => (
                            <TableRow key={socket.profile}>
                              <TableCell className="font-medium">{socket.profile}</TableCell>
                              <TableCell className="max-w-xs truncate font-mono text-xs">
                                {socket.socket_path}
                              </TableCell>
                              <TableCell>
                                <Badge variant={socket.socket_exists ? 'default' : 'destructive'}>
                                  {socket.socket_exists ? 'Есть' : 'Нет'}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge variant={socket.responsive ? 'default' : 'secondary'}>
                                  {socket.responsive ? 'Отвечает' : 'Нет ответа'}
                                </Badge>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  )
}
