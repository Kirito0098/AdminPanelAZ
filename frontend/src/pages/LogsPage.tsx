import { useEffect, useState } from 'react'
import { ClipboardList, Wifi } from 'lucide-react'
import { ApiError, getActionLogs, getConnectionLogs } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useAuth } from '@/context/AuthContext'
import { useNotifications } from '@/context/NotificationContext'
import type { ActionLogEntry } from '@/types'

export default function LogsPage() {
  const { user } = useAuth()
  const { error: notifyError } = useNotifications()
  const [actions, setActions] = useState<ActionLogEntry[]>([])
  const [connections, setConnections] = useState<{ openvpn_clients: Array<Record<string, string>>; wireguard_peers: Array<Record<string, unknown>> } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const conn = await getConnectionLogs()
        setConnections(conn as typeof connections)
        if (user?.role === 'admin') {
          setActions(await getActionLogs())
        }
      } catch (err) {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки логов')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [user?.role])

  if (loading) return <Spinner label="Загрузка логов..." />

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Журналы</h2>
        <p className="text-sm text-muted-foreground">Подключения и действия администраторов</p>
      </div>
      <Tabs defaultValue="connections">
        <TabsList>
          <TabsTrigger value="connections">
            <Wifi size={14} className="mr-1" />
            Подключения
          </TabsTrigger>
          {user?.role === 'admin' && (
            <TabsTrigger value="actions">
              <ClipboardList size={14} className="mr-1" />
              Действия
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="connections">
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
                      <TableHead>Адрес</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(connections?.openvpn_clients ?? []).map((c) => (
                      <TableRow key={c.common_name}>
                        <TableCell>{c.common_name}</TableCell>
                        <TableCell className="font-mono text-xs">{c.real_address}</TableCell>
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
                        <TableCell className="text-xs">{String(p.latest_handshake || '—')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
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
