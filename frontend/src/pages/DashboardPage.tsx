import { useEffect, useRef, useState } from 'react'
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
  downloadConfigsExport,
  downloadProfile,
  fetchQrBlob,
  getClientPolicies,
  getConfigProfileFiles,
  getConfigQuota,
  getConfigs,
  getAwg2Health,
  getEffectiveVisibleVpnProfiles,
  getMonitoring,
  getUsers,
  importConfigsCsv,
  syncConfigs,
} from '@/api/client'
import { buildDashboardSummary } from '@/lib/dashboardSummary'
import ConfigCardsSection from '@/components/dashboard/ConfigCardsSection'
import CreateClientDialog from '@/components/dashboard/CreateClientDialog'
import { parseContentDispositionFilename } from '@/lib/profileDownloadName'
import { triggerFileDownload } from '@/lib/triggerFileDownload'
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
  DashboardSummary,
  SelfServiceQuota,
  User,
  VisibleVpnProfilesPolicy,
  VpnConfig,
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
  const awg2ToggleOn = isEnabled('awg2')
  const awg2Visible =
    awg2ToggleOn &&
    (user?.role === 'admin' ||
      visibilityPolicy == null ||
      visibilityPolicy.protocols.includes('amneziawg2'))
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
  const [syncing, setSyncing] = useState(false)
  const [awg2Installed, setAwg2Installed] = useState(false)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [qrPreview, setQrPreview] = useState<{
    url: string
    filename: string
    contentMode: import('../api/client').QrContentMode
    downloadUrl?: string
  } | null>(null)
  const [policies, setPolicies] = useState<Record<string, import('../types').ClientPoliciesResponseEntry>>({})
  const [connectionMap, setConnectionMap] = useState<ClientConnectionMap | null>(null)
  const [panelUsers, setPanelUsers] = useState<User[]>([])
  const [quota, setQuota] = useState<SelfServiceQuota | null>(null)
  const isAdmin = user?.role === 'admin'
  const awg2CreateEnabled = awg2Visible && awg2Installed
  // Hide create when can_create is false (flag off or quota exhausted) — including unlimited quota.
  const createBlocked = !isAdmin && quota != null && !quota.can_create
  const canCreateClient = (openvpnEnabled || wireguardEnabled || awg2CreateEnabled) && !createBlocked
  const quotaReached = createBlocked && quota != null && !quota.unlimited
  const createDisabledByAdmin = createBlocked && quota != null && quota.unlimited

  useEffect(() => {
    void getEffectiveVisibleVpnProfiles()
      .then((data) => setVisibilityPolicy(data.policy))
      .catch(() => setVisibilityPolicy(null))
  }, [user?.id])

  useEffect(() => {
    if (!awg2ToggleOn) {
      setAwg2Installed(false)
      return
    }
    // Health is admin-only; users with visibility rely on backend 409 if layer missing.
    if (!isAdmin) {
      setAwg2Installed(true)
      return
    }
    let cancelled = false
    void getAwg2Health()
      .then((health) => {
        if (!cancelled) setAwg2Installed(Boolean(health.installed))
      })
      .catch(() => {
        if (!cancelled) setAwg2Installed(false)
      })
    return () => {
      cancelled = true
    }
  }, [awg2ToggleOn, isAdmin, activeNode?.id])

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

    // Admin: one live probe via /monitoring/overview (feeds cards + connectionMap).
    // Config counts come from getConfigs — avoids a second /monitoring/summary probe.
    const monitoringPromise =
      user?.role === 'admin'
        ? getMonitoring('node')
            .then((data) => {
              setConnectionMap(
                buildClientConnectionMap(data.openvpn_clients, data.wireguard_peers),
              )
              return data
            })
            .catch((err) => {
              setConnectionMap(null)
              notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки мониторинга')
              return null
            })
        : Promise.resolve(null)

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
      const monitoring = await monitoringPromise
      if (user?.role !== 'admin') {
        setConnectionMap(null)
      }
      setSummary(buildDashboardSummary(configsData, monitoring, activeNode?.name))
      void loadProfileFiles(configsData)
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки конфигураций')
      try {
        const monitoring = await monitoringPromise
        setSummary(buildDashboardSummary([], monitoring, activeNode?.name))
      } catch {
        setSummary(null)
      }
    } finally {
      setSummaryLoading(false)
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

  const handleDownload = async (config: VpnConfig, path: string, filename: string) => {
    try {
      let downloadName = filename
      await withInline(async () => {
        const res = await downloadProfile(config.id, path)
        if (!res.ok) throw new Error('Ошибка скачивания')
        const blob = await res.blob()
        downloadName =
          parseContentDispositionFilename(res.headers.get('Content-Disposition')) ?? filename
        triggerFileDownload(blob, downloadName)
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
                onClick={() => setShowForm(true)}
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

      <CreateClientDialog
        open={showForm}
        onOpenChange={setShowForm}
        openvpnEnabled={openvpnEnabled}
        wireguardEnabled={wireguardEnabled}
        awg2CreateEnabled={awg2CreateEnabled}
        isAdmin={isAdmin}
        currentUserId={user?.id}
        panelUsers={panelUsers}
        haReplicaReadonly={haReplicaReadonly}
        onCreated={() => load({ silent: true })}
        onSuccess={success}
        onError={notifyError}
        onWarning={notifyWarning}
        withProgress={withInline}
      />

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
                      onClick={() => setShowForm(true)}
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
