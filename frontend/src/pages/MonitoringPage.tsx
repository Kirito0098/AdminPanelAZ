import { useEffect, useState } from 'react'
import { ApiError, getMonitoring } from '../api/client'
import type { MonitoringOverview } from '../types'

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

export default function MonitoringPage() {
  const [data, setData] = useState<MonitoringOverview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      setData(await getMonitoring())
      setError('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  const activeServices = data?.services.filter((s) => s.active).length ?? 0
  const totalConnections = (data?.openvpn_clients.length ?? 0) + (data?.wireguard_peers.filter((p) => p.latest_handshake).length ?? 0)

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>Мониторинг</h2>
          <p>Статус служб, подключения и трафик</p>
        </div>
        <button className="btn secondary" onClick={load}>Обновить</button>
      </header>

      {error && <div className="alert error">{error}</div>}
      {loading && !data ? (
        <div className="loading-inline">Загрузка данных...</div>
      ) : data && (
        <>
          <div className="stats-grid">
            <div className="card stat-card">
              <span className="stat-label">IP сервера</span>
              <strong>{data.server_ip || '—'}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Активные службы</span>
              <strong>{activeServices} / {data.services.length}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Подключения</span>
              <strong>{totalConnections}</strong>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Обновлено</span>
              <strong>{new Date(data.timestamp).toLocaleTimeString('ru-RU')}</strong>
            </div>
          </div>

          <section className="card">
            <h3>Службы VPN</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Служба</th><th>Статус</th></tr>
                </thead>
                <tbody>
                  {data.services.map((s) => (
                    <tr key={s.name}>
                      <td>{s.name}</td>
                      <td><span className={`status ${s.active ? 'ok' : 'bad'}`}>{s.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="card">
            <h3>OpenVPN — активные клиенты</h3>
            {data.openvpn_clients.length === 0 ? (
              <p className="muted">Нет активных подключений</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Клиент</th><th>Реальный IP</th><th>VPN IP</th><th>Получено</th><th>Отправлено</th><th>С</th></tr>
                  </thead>
                  <tbody>
                    {data.openvpn_clients.map((c) => (
                      <tr key={`${c.common_name}-${c.real_address}`}>
                        <td>{c.common_name}</td>
                        <td>{c.real_address}</td>
                        <td>{c.virtual_address}</td>
                        <td>{formatBytes(c.bytes_received)}</td>
                        <td>{formatBytes(c.bytes_sent)}</td>
                        <td>{c.connected_since}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="card">
            <h3>WireGuard / AmneziaWG — пиры</h3>
            {data.wireguard_peers.length === 0 ? (
              <p className="muted">Нет данных WireGuard</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>Интерфейс</th><th>Клиент</th><th>Endpoint</th><th>IP</th><th>RX</th><th>TX</th><th>Handshake</th></tr>
                  </thead>
                  <tbody>
                    {data.wireguard_peers.map((p) => (
                      <tr key={`${p.interface}-${p.public_key}`}>
                        <td>{p.interface}</td>
                        <td>{p.client_name || '—'}</td>
                        <td>{p.endpoint || '—'}</td>
                        <td>{p.allowed_ips || '—'}</td>
                        <td>{formatBytes(p.transfer_rx)}</td>
                        <td>{formatBytes(p.transfer_tx)}</td>
                        <td>{p.latest_handshake ? new Date(p.latest_handshake).toLocaleString('ru-RU') : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
