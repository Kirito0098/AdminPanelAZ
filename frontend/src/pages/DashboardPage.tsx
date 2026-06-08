import { FormEvent, useEffect, useState } from 'react'
import {
  FileKey,
  Loader2,
  Plus,
  RefreshCw,
  Shield,
  Users,
  Wifi,
} from 'lucide-react'
import {
  ApiError,
  createConfig,
  downloadProfile,
  fetchQrBlob,
  getClientPolicies,
  getConfigProfileFiles,
  getConfigs,
  getDashboardSummary,
  syncConfigs,
} from '@/api/client'
import ConfigCardsSection from '@/components/dashboard/ConfigCardsSection'
import MetricCard from '@/components/noc/MetricCard'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { InlineProgressBar } from '@/components/ui/ProgressBar'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { NodeBadge } from '@/components/NodeSelector'
import { useAuth } from '@/context/AuthContext'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import type { ClientAccessPolicy, DashboardSummary, VpnConfig, VpnType } from '@/types'

export default function DashboardPage() {
  const { user } = useAuth()
  const { isEnabled } = useFeatureModules()
  const openvpnEnabled = isEnabled('openvpn')
  const wireguardEnabled = isEnabled('wireguard') || isEnabled('amneziawg')
  const canCreateClient = openvpnEnabled || wireguardEnabled
  const { activeNode } = useNode()
  const { success, error: notifyError } = useNotifications()
  const { startGlobal, doneGlobal, inline, withInline } = useProgress()
  const [configs, setConfigs] = useState<VpnConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [clientName, setClientName] = useState('')
  const [vpnType, setVpnType] = useState<VpnType>('openvpn')
  const [certDays, setCertDays] = useState(3650)
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [qrPreview, setQrPreview] = useState<{ url: string; filename: string } | null>(null)
  const [policies, setPolicies] = useState<
    Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  >({})

  const nodeOffline = activeNode?.status === 'offline'
  const nodeUnknown = activeNode?.status === 'unknown'

  const loadProfileFiles = async (configsData: VpnConfig[]) => {
    if (configsData.length === 0) return
    setLoadingFiles(true)
    try {
      const filesMap = await getConfigProfileFiles(configsData.map((c) => c.id))
      setConfigs((prev) =>
        prev.map((config) => ({
          ...config,
          profile_files: filesMap[String(config.id)] ?? config.profile_files,
        })),
      )
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки файлов профилей')
    } finally {
      setLoadingFiles(false)
    }
  }

  const load = async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) {
      setLoading(true)
      setSummaryLoading(true)
      startGlobal()
    }
    void getDashboardSummary()
      .then((summaryData) => {
        setSummary(summaryData)
      })
      .catch((err) => {
        notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки сводки')
      })
      .finally(() => {
        setSummaryLoading(false)
      })

    try {
      const configsData = await getConfigs(false)
      setConfigs(configsData)
      if (user?.role === 'admin' && configsData.length > 0) {
        const names = configsData.map((c) => c.client_name).join(',')
        getClientPolicies(names).then(setPolicies).catch(() => {})
      } else {
        setPolicies({})
      }
      void loadProfileFiles(configsData)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки конфигураций')
    } finally {
      if (!opts.silent) {
        setLoading(false)
        doneGlobal()
      }
    }
  }

  useEffect(() => {
    load()
  }, [activeNode?.id])

  const resetForm = () => {
    setClientName('')
    setDescription('')
    setVpnType('openvpn')
    setCertDays(3650)
  }

  const closeForm = () => {
    setShowForm(false)
    resetForm()
  }

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()

    const trimmedName = clientName.trim()
    if (!trimmedName) {
      notifyError('Укажите имя клиента')
      return
    }
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(trimmedName)) {
      notifyError('Имя: латиница, цифры, _ и -, до 32 символов')
      return
    }
    if (vpnType === 'openvpn' && (!Number.isFinite(certDays) || certDays < 1 || certDays > 3650)) {
      notifyError('Срок сертификата: от 1 до 3650 дней')
      return
    }

    setSubmitting(true)
    const name = trimmedName
    try {
      await withInline(async () => {
        await createConfig({
          client_name: name,
          vpn_type: vpnType,
          cert_expire_days: vpnType === 'openvpn' ? certDays : undefined,
          description: description || undefined,
        })
        closeForm()
        await load({ silent: true })
      }, 'Создание клиента...')
      success(`Клиент «${name}» создан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания клиента')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDownload = async (config: VpnConfig, path: string, filename: string) => {
    try {
      await withInline(async () => {
        const res = await downloadProfile(config.id, path)
        if (!res.ok) throw new Error('Ошибка скачивания')
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
      }, 'Скачивание файла...')
      success(`Файл «${filename}» скачан`)
    } catch {
      notifyError('Ошибка скачивания файла')
    }
  }

  const handleQr = async (config: VpnConfig, path: string, filename: string) => {
    try {
      await withInline(async () => {
        const blob = await fetchQrBlob(config.id, path)
        const url = URL.createObjectURL(blob)
        setQrPreview({ url, filename })
      }, 'Генерация QR-кода...')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка генерации QR')
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      await withInline(async () => {
        await syncConfigs()
        await load({ silent: true })
      }, 'Синхронизация с AntiZapret...')
      success('Конфигурации синхронизированы')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка синхронизации')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Shield size={22} />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold tracking-tight">Конфигурации</h2>
              <NodeBadge name={activeNode?.name} status={activeNode?.status} />
            </div>
            <p className="text-sm text-muted-foreground">
              Управление клиентами OpenVPN и WireGuard/AmneziaWG на активном узле
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {user?.role === 'admin' && (
            <Button variant="outline" onClick={handleSync} disabled={syncing}>
              {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              {syncing ? 'Синхронизация...' : 'Синхронизировать'}
            </Button>
          )}
          {user?.role !== 'viewer' && canCreateClient && (
            <Button onClick={() => setShowForm(true)}>
              <Plus size={16} />
              Новый клиент
            </Button>
          )}
        </div>
      </div>

      <SettingsAlert variant="info" title="Конфигурации активного узла">
        Список клиентов привязан к узлу <strong>{activeNode?.name ?? summary?.node_name ?? 'не выбран'}</strong>
        {activeNode?.is_local ? ' (локальный controller)' : ' (удалённый node agent)'} — при переключении узла
        отображаются только его конфигурации. Управление — в шапке или на странице «Узлы».
      </SettingsAlert>

      {nodeOffline && (
        <SettingsAlert variant="warning" title="Узел офлайн">
          Активный узел недоступен. Создание и изменение конфигураций может не работать. Проверьте связь с node
          agent.
        </SettingsAlert>
      )}

      {nodeUnknown && !nodeOffline && (
        <SettingsAlert variant="warning" title="Статус узла неизвестен">
          Связь с узлом не подтверждена. Запустите проверку здоровья на странице «Узлы».
        </SettingsAlert>
      )}

      <InlineProgressBar active={inline.active} label={inline.label} />

      {summaryLoading && !summary && (
        <Card>
          <CardContent>
            <Spinner label="Загрузка сводки узла..." className="py-8" />
          </CardContent>
        </Card>
      )}

      {summary && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Всего клиентов"
            value={String(summary.total_configs)}
            sub={`OVPN ${summary.openvpn_configs} · WG ${summary.wireguard_configs}`}
            icon={Users}
            accent="cyan"
          />
          <MetricCard
            label="Онлайн"
            value={String(summary.connected_openvpn + summary.connected_wireguard)}
            sub={`OVPN ${summary.connected_openvpn} · WG ${summary.connected_wireguard}`}
            icon={Wifi}
            accent="green"
          />
          <MetricCard
            label="VPN-службы"
            value={`${summary.active_services}/${summary.total_services}`}
            sub="активных на узле"
            icon={Shield}
            accent="amber"
          />
          <MetricCard
            label="IP сервера"
            value={summary.server_ip || '—'}
            sub={summary.node_name || 'активный узел'}
            icon={FileKey}
          />
        </div>
      )}

      <Dialog
        open={showForm}
        onOpenChange={(open) => {
          if (!open && !submitting) closeForm()
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Plus size={18} />
              Новый клиент
            </DialogTitle>
            <DialogDescription>Создание VPN-клиента через AntiZapret client.sh</DialogDescription>
          </DialogHeader>
          <form noValidate onSubmit={handleCreate} className="space-y-4">
            <SettingsAlert variant="info">
              Имя клиента: латиница, цифры, <strong>_</strong> и <strong>-</strong>, до 32 символов.
            </SettingsAlert>
            <div className="space-y-2">
              <Label htmlFor="clientName">Имя клиента</Label>
              <Input
                id="clientName"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="my-client"
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label>Тип VPN</Label>
              <Select value={vpnType} onValueChange={(v) => setVpnType(v as VpnType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {openvpnEnabled && <SelectItem value="openvpn">OpenVPN</SelectItem>}
                  {wireguardEnabled && <SelectItem value="wireguard">WireGuard / AmneziaWG</SelectItem>}
                </SelectContent>
              </Select>
            </div>
            {vpnType === 'openvpn' && (
              <div className="space-y-2">
                <Label htmlFor="certDays">Срок сертификата (дней)</Label>
                <Input
                  id="certDays"
                  type="number"
                  min={1}
                  max={3650}
                  value={certDays}
                  onChange={(e) => setCertDays(Number(e.target.value))}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="description">Описание</Label>
              <Input
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Необязательно"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeForm} disabled={submitting}>
                Отмена
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Создание...
                  </>
                ) : (
                  <>
                    <Plus size={16} />
                    Создать
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!qrPreview}
        onOpenChange={(open) => {
          if (!open && qrPreview) {
            URL.revokeObjectURL(qrPreview.url)
            setQrPreview(null)
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileKey size={18} />
              QR-код
            </DialogTitle>
            <DialogDescription>{qrPreview?.filename}</DialogDescription>
          </DialogHeader>
          {qrPreview && (
            <div className="flex justify-center rounded-lg border bg-muted/30 p-6">
              <img src={qrPreview.url} alt="QR-код конфигурации" className="max-h-72 rounded-md" />
            </div>
          )}
        </DialogContent>
      </Dialog>

      {loading ? (
        <Card>
          <CardContent>
            <Spinner label="Загрузка конфигураций..." className="py-16" />
          </CardContent>
        </Card>
      ) : configs.length === 0 ? (
        <Card>
          <CardContent>
            <EmptyState
              icon={Shield}
              title="Нет конфигураций"
              description="Создайте первого VPN-клиента или синхронизируйте существующие с AntiZapret."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  {user?.role === 'admin' && (
                    <Button variant="outline" onClick={handleSync} disabled={syncing}>
                      {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                      Синхронизировать
                    </Button>
                  )}
                  {user?.role !== 'viewer' && canCreateClient && (
                    <Button onClick={() => setShowForm(true)}>
                      <Plus size={16} />
                      Создать клиента
                    </Button>
                  )}
                </div>
              }
              className="py-8"
            />
          </CardContent>
        </Card>
      ) : user ? (
        <ConfigCardsSection
          configs={configs}
          policies={policies}
          userRole={user.role}
          filesLoading={loadingFiles}
          onRefresh={() => load({ silent: true })}
          onQr={handleQr}
          onDownload={handleDownload}
          onNotifySuccess={success}
          onNotifyError={notifyError}
        />
      ) : null}
    </div>
  )
}
