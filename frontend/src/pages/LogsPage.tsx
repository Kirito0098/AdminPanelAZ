import { useCallback, useEffect, useRef, useState } from 'react'
import { ClipboardList, Radio, Wifi } from 'lucide-react'
import { ApiError, getActionLogs, getConnectionLogs, getOpenVpnEvents } from '@/api/client'
import AutoRefreshControl from '@/components/noc/AutoRefreshControl'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'
import type { ActionLogEntry, ConnectionLogsSnapshot, OpenVpnEventProfile } from '@/types'

const REFRESH_INTERVAL = 30

function dataSourceLabel(source?: string) {
  if (source === 'management_socket') return 'Management socket'
  if (source === 'status_log') return 'Status-логи'
  return 'Нет данных'
}

function dataSourceVariant(source?: string): 'default' | 'secondary' | 'outline' {
  if (source === 'management_socket') return 'default'
  if (source === 'status_log') return 'secondary'
  return 'outline'
}

export default function LogsPage() {
  const { user } = useAuth()
  const { error: notifyError } = useNotifications()
  const [actions, setActions] = useState<ActionLogEntry[]>([])
  const [connections, setConnections] = useState<ConnectionLogsSnapshot | null>(null)
  const [events, setEvents] = useState<OpenVpnEventProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL)
  const actionsLoadedRef = useRef(false)

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    try {
      const [conn, evt] = await Promise.all([getConnectionLogs(), getOpenVpnEvents()])
      setConnections(conn)
      setEvents(evt.profiles)
      if (user?.role === 'admin' && !actionsLoadedRef.current) {
        setActions(await getActionLogs())
        actionsLoadedRef.current = true
      }
      setCountdown(REFRESH_INTERVAL)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки логов')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [user?.role, notifyError])

  useEffect(() => {
    load()
  }, [load])

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

  if (loading) return <Spinner label="Загрузка логов..." />

  const eventLines = events.flatMap((p) => p.recent_lines.slice(-5))

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Журналы</h2>
          <p className="text-sm text-muted-foreground">Подключения, события OpenVPN и действия администраторов</p>
        </div>
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={() => setAutoRefresh((v) => !v)}
          countdown={countdown}
          intervalSec={REFRESH_INTERVAL}
          refreshing={refreshing}
          onManualRefresh={() => load(true)}
        />
      </div>

      <Tabs defaultValue="connections">
        <TabsList>
          <TabsTrigger value="connections">
            <Wifi size={14} className="mr-1" />
            Подключения
          </TabsTrigger>
          <TabsTrigger value="openvpn-events">
            <Radio size={14} className="mr-1" />
            OpenVPN события
          </TabsTrigger>
          {user?.role === 'admin' && (
            <TabsTrigger value="actions">
              <ClipboardList size={14} className="mr-1" />
              Действия
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="connections">
          <div className="mb-3">
            <Badge variant={dataSourceVariant(connections?.openvpn_data_source)}>
              Источник OVPN: {dataSourceLabel(connections?.openvpn_data_source)}
            </Badge>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">OpenVPN</CardTitle>
                <CardDescription>{connections?.openvpn_clients.length ?? 0} активных</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Клиент</TableHead>
                      <TableHead>Real IP</TableHead>
                      <TableHead>VPN IP</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(connections?.openvpn_clients ?? []).map((c) => (
                      <TableRow key={`${c.common_name}-${c.real_address}`}>
                        <TableCell>{c.common_name}</TableCell>
                        <TableCell className="font-mono text-xs">{c.real_address}</TableCell>
                        <TableCell className="font-mono text-xs">{c.virtual_address}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">WireGuard</CardTitle>
                <CardDescription>{connections?.wireguard_peers.length ?? 0} пиров</CardDescription>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Клиент</TableHead>
                      <TableHead>Handshake</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(connections?.wireguard_peers ?? []).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell>{String(p.client_name || '—')}</TableCell>
                        <TableCell className="text-xs">
                          {p.latest_handshake ? new Date(p.latest_handshake).toLocaleString('ru-RU') : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="openvpn-events">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">События management interface</CardTitle>
              <CardDescription>
                Хвост логов из Unix-сокетов OpenVPN ({eventLines.length} строк в сводке)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {events.map((profile) => (
                <div key={profile.profile} className="rounded-md border p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="font-medium">{profile.profile}</span>
                    <Badge variant={profile.exists ? 'default' : 'outline'}>
                      {profile.exists ? `${profile.line_count} строк` : 'Сокет недоступен'}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{profile.source_name}</span>
                  </div>
                  {profile.recent_lines.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Нет событий</p>
                  ) : (
                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground">
                      {profile.recent_lines.join('\n')}
                    </pre>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {user?.role === 'admin' && (
          <TabsContent value="actions">
            <Card>
              <CardContent className="pt-6">
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
                    {actions.map((a) => (
                      <TableRow key={a.id}>
                        <TableCell className="text-xs">{new Date(a.created_at).toLocaleString('ru-RU')}</TableCell>
                        <TableCell>{a.username || '—'}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">{a.action}</Badge>
                        </TableCell>
                        <TableCell className="max-w-xs truncate text-xs text-muted-foreground">{a.details}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
