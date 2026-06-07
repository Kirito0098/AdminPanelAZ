import { FormEvent, useEffect, useState } from 'react'
import { ApiError, createConfig, deleteConfig, downloadProfile, getConfigs, syncConfigs } from '../api/client'
import { useAuth } from '../context/AuthContext'
import type { VpnConfig, VpnType } from '../types'

export default function DashboardPage() {
  const { user } = useAuth()
  const [configs, setConfigs] = useState<VpnConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [clientName, setClientName] = useState('')
  const [vpnType, setVpnType] = useState<VpnType>('openvpn')
  const [certDays, setCertDays] = useState(3650)
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      setConfigs(await getConfigs())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await createConfig({
        client_name: clientName,
        vpn_type: vpnType,
        cert_expire_days: vpnType === 'openvpn' ? certDays : undefined,
        description: description || undefined,
      })
      setShowForm(false)
      setClientName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка создания')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Удалить клиента "${name}"?`)) return
    try {
      await deleteConfig(id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка удаления')
    }
  }

  const handleDownload = async (config: VpnConfig, path: string, filename: string) => {
    try {
      const res = await downloadProfile(config.id, path)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Ошибка скачивания файла')
    }
  }

  const handleSync = async () => {
    try {
      await syncConfigs()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка синхронизации')
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h2>VPN Конфигурации</h2>
          <p>Управление клиентами OpenVPN и WireGuard/AmneziaWG</p>
        </div>
        <div className="actions">
          {user?.role === 'admin' && (
            <button className="btn secondary" onClick={handleSync}>Синхронизировать</button>
          )}
          <button className="btn primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Отмена' : '+ Новый клиент'}
          </button>
        </div>
      </header>

      {error && <div className="alert error">{error}</div>}

      {showForm && (
        <form className="card form-card" onSubmit={handleCreate}>
          <h3>Создать клиента</h3>
          <div className="form-grid">
            <label>
              Имя клиента
              <input value={clientName} onChange={(e) => setClientName(e.target.value)} pattern="[a-zA-Z0-9_-]{1,32}" required placeholder="my-client" />
            </label>
            <label>
              Тип VPN
              <select value={vpnType} onChange={(e) => setVpnType(e.target.value as VpnType)}>
                <option value="openvpn">OpenVPN</option>
                <option value="wireguard">WireGuard / AmneziaWG</option>
              </select>
            </label>
            {vpnType === 'openvpn' && (
              <label>
                Срок сертификата (дней)
                <input type="number" min={1} max={3650} value={certDays} onChange={(e) => setCertDays(Number(e.target.value))} />
              </label>
            )}
            <label className="full">
              Описание
              <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Необязательно" />
            </label>
          </div>
          <button className="btn primary" disabled={submitting}>{submitting ? 'Создание...' : 'Создать'}</button>
        </form>
      )}

      {loading ? (
        <div className="loading-inline">Загрузка конфигураций...</div>
      ) : configs.length === 0 ? (
        <div className="card empty-state">
          <p>Нет конфигураций. Создайте первого клиента или синхронизируйте с AntiZapret.</p>
        </div>
      ) : (
        <div className="config-grid">
          {configs.map((config) => (
            <article key={config.id} className="card config-card">
              <div className="config-card-header">
                <div>
                  <h3>{config.client_name}</h3>
                  <span className={`badge ${config.vpn_type}`}>{config.vpn_type === 'openvpn' ? 'OpenVPN' : 'WireGuard'}</span>
                </div>
                <button className="btn danger-outline small" onClick={() => handleDelete(config.id, config.client_name)}>Удалить</button>
              </div>
              {config.description && <p className="muted">{config.description}</p>}
              <div className="meta">
                {user?.role === 'admin' && config.owner_username && <span>Владелец: {config.owner_username}</span>}
                {config.cert_expire_days && <span>Сертификат: {config.cert_expire_days} дн.</span>}
                <span>Создан: {new Date(config.created_at).toLocaleDateString('ru-RU')}</span>
              </div>
              {config.profile_files.length > 0 && (
                <div className="files">
                  <strong>Файлы подключения:</strong>
                  <ul>
                    {config.profile_files.map((f) => (
                      <li key={f.path}>
                        <span>{f.variant} — {f.filename}</span>
                        <button className="btn ghost small" onClick={() => handleDownload(config, f.path, f.filename)}>Скачать</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
