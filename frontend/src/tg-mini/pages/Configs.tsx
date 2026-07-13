import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronRight, FileKey, Plus, Search } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import ConfigActionDialog, { type ConfigFeedback } from '@/tg-mini/components/ConfigActionDialog'
import CreateConfigDialog from '@/tg-mini/components/CreateConfigDialog'
import { splitProfileFilesByRoute } from '@/tg-mini/lib/profileFiles'
import MiniListToolbar, {
  matchesProtocolFilter,
  matchesSearchQuery,
  type ProtocolFilter,
} from '@/tg-mini/components/MiniListToolbar'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { guessInstallPlatform } from '@/tg-mini/lib/platformMeta'
import { vpnTypeBadgeClass, vpnTypeLabel } from '@/tg-mini/lib/vpnLabels'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import {
  getTgConfigFiles,
  getTgConfigQuota,
  getTgConfigs,
  getTgFeatureModules,
  getTgQrLink,
  sendTgConfig,
} from '@/tg-mini/api'
import { copyText, openExternalLink, shareViaTelegram } from '@/tg-mini/lib/shareDownloadLink'
import type { InstallPlatform, SelfServiceQuota, TgMiniConfig, TgMiniConfigFile, TgMiniQrLink } from '@/types'

const canShareInTelegram = typeof window.Telegram?.WebApp?.shareUrl === 'function'

function ConfigsSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Загрузка конфигов">
      <div className="tg-mini-skeleton" style={{ height: '2.5rem' }} />
      <div className="tg-mini-skeleton" style={{ height: '2.75rem' }} />
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="tg-mini-skeleton tg-mini-skeleton-card" />
      ))}
    </div>
  )
}

function ownerLabel(config: TgMiniConfig): string | null {
  if (config.is_mine !== false) return null
  return config.owner_username ? `@${config.owner_username}` : 'другой пользователь'
}

export default function Configs() {
  const { isAdmin, settings } = useTgAuth()
  const [configs, setConfigs] = useState<TgMiniConfig[]>([])
  const [quota, setQuota] = useState<SelfServiceQuota | null>(null)
  const [openvpnEnabled, setOpenvpnEnabled] = useState(true)
  const [wireguardEnabled, setWireguardEnabled] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [protocol, setProtocol] = useState<ProtocolFilter>('all')
  const [activeConfig, setActiveConfig] = useState<TgMiniConfig | null>(null)
  const [files, setFiles] = useState<TgMiniConfigFile[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [sheetLoading, setSheetLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [feedback, setFeedback] = useState<ConfigFeedback | null>(null)
  const [downloadLink, setDownloadLink] = useState<TgMiniQrLink | null>(null)
  const [platform, setPlatform] = useState<InstallPlatform>(() => guessInstallPlatform())

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      const [data, quotaData] = await Promise.all([getTgConfigs(), getTgConfigQuota()])
      setConfigs(data.configs)
      setQuota(quotaData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void getTgFeatureModules()
      .then((data) => {
        const policy = settings?.visible_vpn_profiles
        const allowOpenvpn =
          Boolean(data.features.openvpn) &&
          (isAdmin ||
            !policy ||
            (policy.protocols.includes('openvpn') && policy.openvpn_groups.length > 0))
        const allowWireguard =
          (Boolean(data.features.wireguard) || Boolean(data.features.amneziawg)) &&
          (isAdmin ||
            !policy ||
            policy.protocols.includes('wireguard') ||
            policy.protocols.includes('amneziawg'))
        setOpenvpnEnabled(allowOpenvpn)
        setWireguardEnabled(allowWireguard)
      })
      .catch(() => {
        setOpenvpnEnabled(true)
        setWireguardEnabled(true)
      })
  }, [isAdmin, settings?.visible_vpn_profiles])

  useEffect(() => {
    void load()
  }, [load])

  const protocolCounts = useMemo(
    () => ({
      all: configs.length,
      openvpn: configs.filter((c) => c.vpn_type === 'openvpn').length,
      wireguard: configs.filter((c) => c.vpn_type === 'wireguard').length,
    }),
    [configs],
  )

  const filteredConfigs = useMemo(
    () =>
      configs.filter(
        (config) =>
          matchesProtocolFilter(config.vpn_type, protocol) &&
          matchesSearchQuery(config.client_name, search) &&
          matchesSearchQuery(config.owner_username || '', search),
      ),
    [configs, protocol, search],
  )

  const resetFilters = () => {
    setSearch('')
    setProtocol('all')
  }

  const hasActiveFilters = search.trim().length > 0 || protocol !== 'all'
  const isForeignConfig = Boolean(activeConfig && activeConfig.is_mine === false)
  const canCreate =
    settings?.role !== 'viewer' &&
    (openvpnEnabled || wireguardEnabled) &&
    (quota?.can_create ?? true)
  const canManageConfig = (config: TgMiniConfig) => isAdmin || config.is_mine !== false

  const openActions = async (config: TgMiniConfig) => {
    setActiveConfig(config)
    setFeedback(null)
    setDownloadLink(null)
    setPlatform(guessInstallPlatform())
    setSheetLoading(true)
    try {
      const data = await getTgConfigFiles(config.id)
      setFiles(data.files)
      const { vpn, antizapret } = splitProfileFilesByRoute(data.files)
      const defaultFile = vpn[0] ?? antizapret[0] ?? data.files[0]
      setSelectedPath(defaultFile?.path || '')
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка загрузки файлов',
      })
      setFiles([])
    } finally {
      setSheetLoading(false)
    }
  }

  const closeSheet = () => {
    setActiveConfig(null)
    setFiles([])
    setSelectedPath('')
    setFeedback(null)
    setDownloadLink(null)
  }

  const handleSelectedPathChange = (path: string) => {
    setSelectedPath(path)
    setDownloadLink(null)
    setFeedback(null)
  }

  const handleSend = async (destination: 'self' | 'owner') => {
    if (!activeConfig || !selectedPath) return
    setActionLoading(true)
    setFeedback(null)
    try {
      const result = await sendTgConfig(activeConfig.id, {
        path: selectedPath,
        destination,
        platform,
      })
      setFeedback({ tone: 'success', text: result.message })
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка отправки',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleCreateDownloadLink = async () => {
    if (!activeConfig || !selectedPath) return
    setActionLoading(true)
    setFeedback(null)
    setDownloadLink(null)
    try {
      const link = await getTgQrLink(activeConfig.id, selectedPath)
      setDownloadLink(link)
      const copied = await copyText(link.url)
      setFeedback({
        tone: 'success',
        text: copied
          ? 'Ссылка создана и скопирована — отправьте её в нужный чат'
          : 'Ссылка создана — скопируйте или поделитесь ею',
      })
      window.Telegram?.WebApp.HapticFeedback?.notificationOccurred('success')
    } catch (err) {
      setFeedback({
        tone: 'error',
        text: err instanceof ApiError ? err.message : 'Ошибка создания ссылки',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleCopyDownloadLink = async () => {
    if (!downloadLink) return
    const copied = await copyText(downloadLink.url)
    setFeedback({
      tone: copied ? 'success' : 'error',
      text: copied ? 'Ссылка скопирована' : 'Не удалось скопировать — выделите ссылку вручную',
    })
  }

  const handleShareDownloadLink = async () => {
    if (!downloadLink) return
    if (shareViaTelegram(downloadLink.url, `VPN-конфиг: ${activeConfig?.client_name ?? ''}`)) {
      setFeedback({ tone: 'info', text: 'Выберите чат, куда отправить ссылку' })
      return
    }
    const copied = await copyText(downloadLink.url)
    setFeedback({
      tone: 'info',
      text: copied
        ? 'Поделиться недоступно — ссылка скопирована, вставьте в чат вручную'
        : 'Поделиться недоступно — скопируйте ссылку вручную',
    })
  }

  const handleOpenDownloadLink = () => {
    if (!downloadLink) return
    openExternalLink(downloadLink.url)
    setFeedback({
      tone: 'info',
      text: 'Ссылка открыта. Если она одноразовая — на другом устройстве уже не сработает',
    })
  }

  const handleConfigDeleted = () => {
    closeSheet()
    void load({ silent: true })
  }

  const handleConfigUpdated = () => {
    void load({ silent: true })
  }

  if (loading && configs.length === 0) {
    return <ConfigsSkeleton />
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Конфиги"
        subtitle={
          configs.length > 0
            ? `${configs.length} ${configs.length === 1 ? 'конфиг' : configs.length < 5 ? 'конфига' : 'конфигов'}`
            : 'Создайте или получите VPN-профиль'
        }
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {canCreate && (
        <Button type="button" className="w-full gap-2" onClick={() => setShowCreate(true)}>
          <Plus size={18} aria-hidden />
          Новый конфиг
        </Button>
      )}

      {quota && !quota.unlimited && (
        <p className="text-xs text-muted-foreground">
          Лимит: {quota.used} из {quota.limit}
          {!quota.can_create ? ' — достигнут' : ''}
        </p>
      )}

      {error && <p className="text-destructive text-sm">{error}</p>}

      {configs.length > 0 && (
        <>
          <MiniListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder={isAdmin ? 'Поиск по имени или владельцу…' : 'Поиск по имени…'}
            protocol={protocol}
            onProtocolChange={setProtocol}
            protocolCounts={protocolCounts}
          />

          {hasActiveFilters && (
            <p className="tg-mini-results-meta">
              Показано {filteredConfigs.length}
              {filteredConfigs.length !== configs.length ? ` из ${configs.length}` : ''}
            </p>
          )}
        </>
      )}

      {configs.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <FileKey size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Нет конфигов</p>
          <p className="text-xs text-muted-foreground">
            {canCreate ? 'Создайте первый профиль кнопкой выше' : 'Профили появятся после создания в панели'}
          </p>
        </div>
      ) : filteredConfigs.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <Search size={20} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Ничего не найдено</p>
          <p className="text-xs text-muted-foreground">Измените поиск или сбросьте фильтр</p>
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={resetFilters}>
            Сбросить
          </Button>
        </div>
      ) : (
        filteredConfigs.map((config) => {
          const owner = ownerLabel(config)
          return (
            <Card key={config.id} className="tg-mini-config-card">
              <CardContent className="p-0">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 p-4 text-left"
                  onClick={() => void openActions(config)}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium">{config.client_name}</span>
                      <span className={`tg-mini-protocol-badge ${vpnTypeBadgeClass(config.vpn_type)}`}>
                        {vpnTypeLabel(config.vpn_type)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {owner ? `Владелец: ${owner}` : 'Получить в Telegram с инструкцией'}
                    </p>
                  </div>
                  <ChevronRight size={18} className="shrink-0 text-muted-foreground" aria-hidden />
                </button>
              </CardContent>
            </Card>
          )
        })
      )}

      <ConfigActionDialog
        config={activeConfig}
        files={files}
        selectedPath={selectedPath}
        onSelectedPathChange={handleSelectedPathChange}
        platform={platform}
        onPlatformChange={setPlatform}
        loading={sheetLoading}
        actionLoading={actionLoading}
        feedback={feedback}
        downloadLink={downloadLink}
        canShareLink={canShareInTelegram}
        isForeignConfig={isForeignConfig}
        ownerLabel={activeConfig ? ownerLabel(activeConfig) : null}
        canManage={activeConfig ? canManageConfig(activeConfig) : false}
        isAdmin={isAdmin}
        onClose={closeSheet}
        onSend={(destination) => void handleSend(destination)}
        onCreateDownloadLink={() => void handleCreateDownloadLink()}
        onCopyDownloadLink={() => void handleCopyDownloadLink()}
        onShareDownloadLink={handleShareDownloadLink}
        onOpenDownloadLink={handleOpenDownloadLink}
        onConfigDeleted={handleConfigDeleted}
        onConfigUpdated={handleConfigUpdated}
      />

      <CreateConfigDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        isAdmin={isAdmin}
        currentUserId={settings?.user_id}
        openvpnEnabled={openvpnEnabled}
        wireguardEnabled={wireguardEnabled}
        quota={quota}
        onCreated={() => void load({ silent: true })}
      />
    </div>
  )
}
