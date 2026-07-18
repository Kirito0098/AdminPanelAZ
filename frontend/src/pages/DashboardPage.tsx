import { FormEvent, useEffect, useRef, useState } from 'react'
import {
  Copy,
  Download,
  FileKey,
  Loader2,
  Plus,
  RefreshCw,
  Shield,
  Upload,
  Users,
  Wifi,
} from 'lucide-react'
import {
  ApiError,
  applyClientTemplate,
  createConfig,
  downloadConfigsExport,
  downloadProfile,
  fetchQrBlob,
  getClientPolicies,
  getClientTemplates,
  getConfigProfileFiles,
  getConfigQuota,
  getConfigs,
  getDashboardSummary,
  getEffectiveVisibleVpnProfiles,
  getMonitoring,
  getUsers,
  importConfigsCsv,
  syncConfigs,
} from '@/api/client'
import ConfigCardsSection from '@/components/dashboard/ConfigCardsSection'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'
import MetricCard from '@/components/noc/MetricCard'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import SettingsAlert from '@/components/settings/SettingsAlert'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import ToolbarButton from '@/components/shared/ToolbarButton'
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
import { useHaReplicaReadonly } from '@/hooks/useHaReplicaReadonly'
import { useNotifications } from '@/context/NotificationContext'
import { useProgress } from '@/context/ProgressContext'
import { useBackgroundTaskPoll } from '@/hooks/useBackgroundTaskPoll'
import { buildClientConnectionMap, type ClientConnectionMap } from '@/lib/configCardUtils'
import { cn } from '@/lib/utils'
import type {
  ClientAccessPolicy,
  ClientTemplate,
  DashboardSummary,
  SelfServiceQuota,
  User,
  VisibleVpnProfilesPolicy,
  VpnConfig,
  VpnType,
} from '@/types'

export default function DashboardPage() {
  const { user } = useAuth()
  const { isEnabled } = useFeatureModules()
  const [visibilityPolicy, setVisibilityPolicy] = useState<VisibleVpnProfilesPolicy | null>(null)
  const openvpnEnabled =
    isEnabled('openvpn') &&
    (user?.role === 'admin' || visibilityPolicy == null || visibilityPolicy.protocols.includes('openvpn')) &&
    (user?.role === 'admin' ||
      visibilityPolicy == null ||
      (visibilityPolicy.openvpn_groups?.length ?? 0) > 0)
  const wireguardEnabled =
    (isEnabled('wireguard') || isEnabled('amneziawg')) &&
    (user?.role === 'admin' ||
      visibilityPolicy == null ||
      visibilityPolicy.protocols.includes('wireguard') ||
      visibilityPolicy.protocols.includes('amneziawg'))
  const { activeNode } = useNode()
  const haReplicaReadonly = useHaReplicaReadonly()
  const { success, error: notifyError, warning: notifyWarning } = useNotifications()
  const { startGlobal, doneGlobal, withInline } = useProgress()
  const { task: importTask, polling: importPolling, startPoll: startImportPoll } = useBackgroundTaskPoll()
  const csvInputRef = useRef<HTMLInputElement>(null)
  const [csvExporting, setCsvExporting] = useState(false)
  const [csvImporting, setCsvImporting] = useState(false)
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
  const [qrPreview, setQrPreview] = useState<{
    url: string
    filename: string
    contentMode: import('../api/client').QrContentMode
    downloadUrl?: string
  } | null>(null)
  const [policies, setPolicies] = useState<
    Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  >({})
  const [connectionMap, setConnectionMap] = useState<ClientConnectionMap | null>(null)
  const [panelUsers, setPanelUsers] = useState<User[]>([])
  const [ownerId, setOwnerId] = useState<number | null>(null)
  const [templates, setTemplates] = useState<ClientTemplate[]>([])
  const [quota, setQuota] = useState<SelfServiceQuota | null>(null)
  const isAdmin = user?.role === 'admin'
  // Hide create when can_create is false (flag off or quota exhausted) — including unlimited quota.
  const createBlocked = !isAdmin && quota != null && !quota.can_create
  const canCreateClient = (openvpnEnabled || wireguardEnabled) && !createBlocked
  const quotaReached = createBlocked && quota != null && !quota.unlimited
  const createDisabledByAdmin = createBlocked && quota != null && quota.unlimited

  useEffect(() => {
    void getEffectiveVisibleVpnProfiles()
      .then((data) => setVisibilityPolicy(data.policy))
      .catch(() => setVisibilityPolicy(null))
  }, [user?.id])

  useEffect(() => {
    if (openvpnEnabled) setVpnType('openvpn')
    else if (wireguardEnabled) setVpnType('wireguard')
  }, [openvpnEnabled, wireguardEnabled])

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
      if (user?.role !== 'admin') {
        getConfigQuota()
          .then(setQuota)
          .catch(() => setQuota(null))
      } else {
        setQuota(null)
      }
      if (configsData.length > 0) {
        const names = configsData.map((c) => c.client_name).join(',')
        getClientPolicies(names).then(setPolicies).catch(() => setPolicies({}))
      } else {
        setPolicies({})
      }
      if (user?.role === 'admin') {
        void getMonitoring('node')
          .then((data) =>
            setConnectionMap(buildClientConnectionMap(data.openvpn_clients, data.wireguard_peers)),
          )
          .catch(() => setConnectionMap(null))
      } else {
        setConnectionMap(null)
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

  useEffect(() => {
    if (!isAdmin) {
      setPanelUsers([])
      return
    }
    let cancelled = false
    void getUsers()
      .then((users) => {
        if (!cancelled) setPanelUsers(users)
      })
      .catch(() => {
        if (!cancelled) setPanelUsers([])
      })
    return () => {
      cancelled = true
    }
  }, [isAdmin])

  useEffect(() => {
    if (!canCreateClient) return
    void getClientTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]))
  }, [canCreateClient, activeNode?.id])

  const resetForm = () => {
    setClientName('')
    setDescription('')
    setVpnType('openvpn')
    setCertDays(3650)
    setOwnerId(user?.id ?? null)
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
        const created = await createConfig({
          client_name: name,
          vpn_type: vpnType,
          cert_expire_days: vpnType === 'openvpn' ? certDays : undefined,
          description: description || undefined,
          owner_id: isAdmin && ownerId ? ownerId : undefined,
        })
        closeForm()
        await load({ silent: true })
        if (created.ha_replicate_warning) {
          notifyWarning(created.ha_replicate_warning)
        }
      }, 'Создание клиента...')
      success(`Клиент «${name}» создан`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка создания клиента')
    } finally {
      setSubmitting(false)
    }
  }

  const handleApplyTemplate = async (template: ClientTemplate) => {
    const trimmedName = clientName.trim()
    if (!trimmedName) {
      notifyError('Укажите имя клиента для шаблона')
      return
    }
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(trimmedName)) {
      notifyError('Имя: латиница, цифры, _ и -, до 32 символов')
      return
    }
    setSubmitting(true)
    try {
      await withInline(async () => {
        await applyClientTemplate(template.id, {
          client_name: trimmedName,
          owner_id: isAdmin && ownerId ? ownerId : undefined,
        })
        closeForm()
        await load({ silent: true })
      }, `Создание: ${template.name}...`)
      success(`Клиент «${trimmedName}» создан по шаблону`)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка применения шаблона')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDownload = async (config: VpnConfig, path: string, filename: string) => {
    try {
      let downloadName = filename
      await withInline(async () => {
        const res = await downloadProfile(config.id, path)
        if (!res.ok) throw new Error('Ошибка скачивания')
        const blob = await res.blob()
        downloadName =
          parseContentDispositionFilename(res.headers.get('Content-Disposition')) ?? filename
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = downloadName
        a.click()
        URL.revokeObjectURL(url)
      }, 'Скачивание файла...')
      success(`Файл «${downloadName}» скачан`)
    } catch {
      notifyError('Ошибка скачивания файла')
    }
  }

  const handleQr = async (config: VpnConfig, path: string, filename: string) => {
    try {
      await withInline(async () => {
        const { blob, contentMode, downloadUrl } = await fetchQrBlob(config.id, path)
        const url = URL.createObjectURL(blob)
        setQrPreview({ url, filename, contentMode, downloadUrl })
      }, 'Генерация QR-кода...')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка генерации QR')
    }
  }

  const copyQrDownloadUrl = async () => {
    if (!qrPreview?.downloadUrl) return
    try {
      await navigator.clipboard.writeText(qrPreview.downloadUrl)
      success('Ссылка скопирована в буфер')
    } catch {
      notifyError('Не удалось скопировать ссылку')
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await withInline(async () => {
        const syncResult = await syncConfigs()
        await load({ silent: true })
        return syncResult
      }, 'Синхронизация с AntiZapret...')
      success(result?.message || 'Конфигурации синхронизированы')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка синхронизации')
    } finally {
      setSyncing(false)
    }
  }

  const handleExportCsv = async () => {
    setCsvExporting(true)
    try {
      const response = await downloadConfigsExport()
      if (!response.ok) throw new ApiError('Ошибка экспорта', response.status)
      const blob = await response.blob()
      const disposition = response.headers.get('content-disposition') || ''
      const filename = parseContentDispositionFilename(disposition) || 'vpn-configs.csv'
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
      success('CSV экспортирован')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка экспорта CSV')
    } finally {
      setCsvExporting(false)
    }
  }

  const handleImportCsv = async (file: File) => {
    setCsvImporting(true)
    try {
      const result = await importConfigsCsv(file)
      if (result.queued && result.task_id) {
        startImportPoll(result.task_id, {
          onComplete: async (task) => {
            success(task.message || 'Импорт CSV завершён')
            await load({ silent: true })
            setCsvImporting(false)
          },
          onError: (_task, message) => {
            notifyError(message)
            setCsvImporting(false)
          },
        })
        success(result.message)
        return
      }
      success(result.message)
      await load({ silent: true })
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка импорта CSV')
    } finally {
      if (!importPolling) setCsvImporting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-br from-primary/5 via-card to-card p-5 shadow-sm">
        <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary shadow-sm">
              <Shield size={26} strokeWidth={2} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">Конфигурации</h2>
                <NodeBadge name={activeNode?.name} status={activeNode?.status} />
              </div>
              <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                VPN-клиенты на узле{' '}
                <strong className="font-medium text-foreground">{activeNode?.name ?? summary?.node_name ?? 'не выбран'}</strong>
                {activeNode?.is_local ? ' (локальный controller)' : activeNode ? ' (удалённый node agent)' : ''}.
                OpenVPN и WireGuard / AmneziaWG.
              </p>
            </div>
          </div>

          <div className="flex w-full flex-wrap gap-2 lg:max-w-xl lg:justify-end">
            {user?.role === 'admin' && (
              <>
                <ToolbarButton
                  variant="outline"
                  className="bg-card/80"
                  icon={syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                  label={syncing ? 'Синхронизация...' : 'Синхронизировать'}
                  shortLabel={syncing ? '...' : 'Синхр.'}
                  onClick={handleSync}
                  disabled={syncing || haReplicaReadonly}
                />
                <ToolbarButton
                  variant="outline"
                  className="bg-card/80"
                  icon={csvExporting ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
                  label="Экспорт CSV"
                  shortLabel="Экспорт"
                  onClick={() => void handleExportCsv()}
                  disabled={csvExporting}
                />
                <ToolbarButton
                  variant="outline"
                  className="bg-card/80"
                  icon={
                    csvImporting || importPolling ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Upload size={16} />
                    )
                  }
                  label="Импорт CSV"
                  shortLabel="Импорт"
                  onClick={() => csvInputRef.current?.click()}
                  disabled={csvImporting || importPolling || haReplicaReadonly}
                />
                <input
                  ref={csvInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (file) void handleImportCsv(file)
                  }}
                />
              </>
            )}
            {canCreateClient && (
              <ToolbarButton
                size="lg"
                variant="default"
                icon={<Plus size={18} />}
                label="Новый клиент"
                shortLabel="Новый"
                onClick={() => {
                  setOwnerId(user?.id ?? null)
                  setShowForm(true)
                }}
                disabled={quotaReached || haReplicaReadonly}
              />
            )}
          </div>
        </div>
      </div>

      <HaReplicaBanner />

      {(importPolling || importTask || csvImporting) && user?.role === 'admin' && (
        <SettingsAlert variant="info" title="Импорт CSV">
          {importTask?.progress_stage || importTask?.message || 'Импорт выполняется…'}
          {importTask?.progress_percent != null ? ` (${importTask.progress_percent}%)` : ''}
        </SettingsAlert>
      )}

      {createDisabledByAdmin && (
        <SettingsAlert variant="info" title="Создание отключено">
          Администратор отключил создание конфигураций для вашей учётной записи. Доступны просмотр и скачивание.
        </SettingsAlert>
      )}

      {quota && !quota.unlimited && (
        <SettingsAlert variant={quotaReached ? 'warning' : 'info'} title="Лимит конфигураций">
          Использовано <strong>{quota.used}</strong> из <strong>{quota.limit}</strong> разрешённых клиентов.
          {quotaReached ? ' Удалите конфиг или обратитесь к администратору для увеличения квоты.' : ''}
        </SettingsAlert>
      )}

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

      {summaryLoading && !summary && (
        <div className="rounded-xl border bg-card p-6">
          <Spinner label="Загрузка сводки узла..." className="py-8" />
        </div>
      )}

      {summary && (
        <div className={cn('grid gap-3 sm:grid-cols-2', isAdmin ? 'xl:grid-cols-4' : 'xl:grid-cols-2')}>
          <MetricCard
            label={isAdmin ? 'Всего клиентов' : 'Мои конфигурации'}
            value={String(summary.total_configs)}
            sub={`OVPN ${summary.openvpn_configs} · WG ${summary.wireguard_configs}`}
            icon={Users}
            accent="cyan"
          />
          {isAdmin && (
            <>
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
            </>
          )}
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
            {isAdmin && (
              <ConfigOwnerSelect
                id="createConfigOwner"
                users={panelUsers}
                value={ownerId}
                onChange={setOwnerId}
                disabled={submitting}
                description="Пользователь с ролью «Пользователь» увидит этот конфиг в своём списке."
              />
            )}
            {templates.length > 0 && (
              <div className="space-y-2">
                <Label>Шаблоны (one-click)</Label>
                <div className="flex flex-wrap gap-2">
                  {templates.map((tpl) => (
                    <Button
                      key={tpl.id}
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={submitting || haReplicaReadonly}
                      onClick={() => void handleApplyTemplate(tpl)}
                    >
                      {tpl.name}
                    </Button>
                  ))}
                </div>
              </div>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeForm} disabled={submitting}>
                Отмена
              </Button>
              <Button type="submit" disabled={submitting || haReplicaReadonly}>
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
              {qrPreview?.contentMode === 'download-link' ? 'QR: ссылка для скачивания' : 'QR-код профиля'}
            </DialogTitle>
            <DialogDescription>
              {qrPreview?.filename}
              {qrPreview?.contentMode === 'download-link' ? (
                <span className="mt-1 block text-xs text-muted-foreground">
                  Профиль не помещается в один QR (типично для AntiZapret WG/AWG и OpenVPN). Отсканируйте
                  камерой телефона — откроется ссылка для скачивания файла, не импорт в VPN-приложение.
                </span>
              ) : (
                <span className="mt-1 block text-xs text-muted-foreground">
                  Отсканируйте VPN-приложением для импорта профиля.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {qrPreview && (
            <div className="flex justify-center rounded-lg border bg-muted/30 p-6">
              <img src={qrPreview.url} alt="QR-код конфигурации" className="max-h-72 rounded-md" />
            </div>
          )}
          {qrPreview?.downloadUrl && (
            <DialogFooter className="sm:justify-center">
              <Button type="button" variant="outline" onClick={() => void copyQrDownloadUrl()}>
                <Copy size={14} />
                Скопировать ссылку
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      {loading ? (
        <div className="rounded-xl border bg-card p-6">
          <Spinner label="Загрузка конфигураций..." className="py-16" />
        </div>
      ) : configs.length === 0 ? (
        <div className="overflow-hidden rounded-2xl border bg-card shadow-sm">
          <div className="h-1 bg-gradient-to-r from-primary/70 to-primary/10" />
          <div className="p-6">
            <EmptyState
              icon={Shield}
              title="Нет конфигураций"
              description="Создайте первого VPN-клиента или синхронизируйте существующие с AntiZapret."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  {user?.role === 'admin' && (
                    <Button variant="outline" onClick={handleSync} disabled={syncing || haReplicaReadonly}>
                      {syncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                      Синхронизировать
                    </Button>
                  )}
                  {canCreateClient && (
                    <Button
                      onClick={() => {
                        setOwnerId(user?.id ?? null)
                        setShowForm(true)
                      }}
                      disabled={quotaReached || haReplicaReadonly}
                    >
                      <Plus size={16} />
                      Создать клиента
                    </Button>
                  )}
                </div>
              }
              className="py-8"
            />
          </div>
        </div>
      ) : user ? (
        <ConfigCardsSection
          configs={configs}
          policies={policies}
          userRole={user.role}
          currentUserId={user.id}
          ownerCandidates={panelUsers}
          connectionMap={connectionMap}
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
