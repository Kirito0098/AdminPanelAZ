import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import { getTgDashboard } from '@/tg-mini/api'
import type { TgMiniDashboard } from '@/types'

function formatBytes(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB']
  let size = value || 0
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size.toFixed(1)} ${units[index]}`
}

export default function Dashboard() {
  const [data, setData] = useState<TgMiniDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getTgDashboard())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="tg-mini-center">
        <Spinner />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="tg-mini-panel">
        <p className="text-destructive">{error || 'Нет данных'}</p>
        <Button type="button" onClick={() => void load()}>
          Обновить
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="tg-mini-cards">
        <Card className="tg-mini-card">
          <CardContent className="p-4">
            <div className="text-2xl font-bold">{data.total_configs}</div>
            <div className="text-sm text-muted-foreground">Конфигов</div>
          </CardContent>
        </Card>
        <Card className="tg-mini-card">
          <CardContent className="p-4">
            <div className="text-2xl font-bold">{data.connected_openvpn}</div>
            <div className="text-sm text-muted-foreground">OpenVPN</div>
          </CardContent>
        </Card>
        <Card className="tg-mini-card">
          <CardContent className="p-4">
            <div className="text-2xl font-bold">{data.connected_wireguard}</div>
            <div className="text-sm text-muted-foreground">WireGuard</div>
          </CardContent>
        </Card>
        <Card className="tg-mini-card">
          <CardContent className="p-4">
            <div className="text-2xl font-bold truncate">{data.server_ip || '—'}</div>
            <div className="text-sm text-muted-foreground">Сервер</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Подключённые OpenVPN</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.openvpn_clients.length === 0 ? (
            <p className="tg-mini-muted">Нет подключений</p>
          ) : (
            data.openvpn_clients.map((client, index) => (
              <div key={index} className="tg-mini-client-row">
                <span>{String(client.common_name || '—')}</span>
                <span className="text-emerald-500">online</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">WireGuard</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.wireguard_peers.length === 0 ? (
            <p className="tg-mini-muted">Нет пиров</p>
          ) : (
            data.wireguard_peers.map((peer) => (
              <div key={peer.public_key} className="tg-mini-client-row">
                <span>{peer.client_name || peer.public_key.slice(0, 8)}</span>
                <span className="text-emerald-500">
                  {formatBytes(peer.transfer_rx + peer.transfer_tx)}
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">Обновлено: {new Date(data.timestamp).toLocaleString()}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void load()}>
          Обновить
        </Button>
      </div>
    </div>
  )
}
