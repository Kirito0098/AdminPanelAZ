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
import {
  isVpnTypeVisibleInPolicy,
  protocolFiltersForPolicy,
} from '@/tg-mini/lib/vpnVisibility'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import {
  createTgMePlanConfig,
  getTgConfigFiles,
  getTgConfigQuota,
  getTgMeConfigs,
  getTgQrLink,
  sendTgConfig,
} from '@/tg-mini/api'
import { copyText, openExternalLink, shareViaTelegram } from '@/tg-mini/lib/shareDownloadLink'
import type {
  InstallPlatform,
  SelfServiceQuota,
  TgMeConfig,
  TgMeConfigNode,
  TgMiniConfigFile,
  TgMiniQrLink,
} from '@/types'
import { Badge } from '@/components/ui/badge'

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

export default function Configs() {
  const { isAdmin, settings, features } = useTgAuth()
  const [configs, setConfigs] = useState<TgMeConfig[]>([])
  const [quota, setQuota] = useState<SelfServiceQuota | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [protocol, setProtocol] = useState<ProtocolFilter>('all')
  const [activeConfig, setActiveConfig] = useState<TgMeConfigNode & { clientName: string } | null>(null)
  const [files, setFiles] = useState<TgMiniConfigFile[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [sheetLoading, setSheetLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [feedback, setFeedback] = useState<ConfigFeedback | null>(null)
  const [downloadLink, setDownloadLink] = useState<TgMiniQrLink | null>(null)
  const [platform, setPlatform] = useState<InstallPlatform>(() => guessInstallPlatform())
  const [planAdding, setPlanAdding] = useState(false)

  const load = useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }
    setError(null)
    try {
      const [data, quotaData] = await Promise.all([getTgMeConfigs(), getTgConfigQuota()])
      setConfigs(data.configs)
      setQuota(quotaData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  const { openvpnEnabled, wireguardEnabled, awg2Enabled } = useMemo(() => {
    const policy = settings?.visible_vpn_profiles
    const allowOpenvpn =
      Boolean(features.openvpn ?? true) &&
      isVpnTypeVisibleInPolicy('openvpn', policy, isAdmin)
    const allowWireguard =
      (Boolean(features.wireguard ?? true) || Boolean(features.amneziawg ?? true)) &&
      isVpnTypeVisibleInPolicy('wireguard', policy, isAdmin)
    const allowAwg2 =
      Boolean(features.awg2) && isVpnTypeVisibleInPolicy('amneziawg2', policy, isAdmin)
    return {
      openvpnEnabled: allowOpenvpn,
      wireguardEnabled: allowWireguard,
      awg2Enabled: allowAwg2,
    }
  }, [features, isAdmin, settings?.visible_vpn_profiles])

  const protocolOptions = useMemo(
    () => protocolFiltersForPolicy(settings?.visible_vpn_profiles, isAdmin),
    [isAdmin, settings?.visible_vpn_profiles],
  )

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (protocol !== 'all' && !protocolOptions.includes(protocol)) {
      setProtocol('all')
    }
  }, [protocol, protocolOptions])

  const visibleGroups = useMemo(() => {
    return configs.filter((group) =>
      group.nodes.some((n) => isVpnTypeVisibleInPolicy(n.vpn_type, settings?.visible_vpn_profiles, isAdmin)),
    )
  }, [configs, isAdmin, settings?.visible_vpn_profiles])

  const protocolCounts = useMemo(
    () => ({
      all: visibleGroups.reduce((s, g) => s + g.nodes.length, 0),
      openvpn: visibleGroups.reduce((s, g) => s + g.nodes.filter((n) => n.vpn_type === 'openvpn').length, 0),
      wireguard: visibleGroups.reduce((s, g) => s + g.nodes.filter((n) => n.vpn_type === 'wireguard').length, 0),
      amneziawg2: visibleGroups.reduce((s, g) => s + g.nodes.filter((n) => n.vpn_type === 'amneziawg2').length, 0),
    }),
    [visibleGroups],
  )

  const allNodes = useMemo(
    () =>
      visibleGroups.flatMap((g) =>
        g.nodes.map((n) => ({ ...n, clientName: g.name })),
      ),
    [visibleGroups],
  )

  const filteredNodes = useMemo(() => {
    const q = search.trim()
    return allNodes.filter((n) => {
      if (protocol !== 'all' && !matchesProtocolFilter(n.vpn_type, protocol)) return false
      if (!q) return true
      return matchesSearchQuery(n.clientName, q)
    })
  }, [allNodes, protocol, search])

  const resetFilters = () => {
    setSearch('')
    setProtocol('all')
  }

  const hasActiveFilters = search.trim().length > 0 || protocol !== 'all'
  const used = quota?.used ?? 0
  const limit = quota?.limit
  const unlimited = quota?.unlimited ?? false
  const canCreate =
    (openvpnEnabled || wireguardEnabled || awg2Enabled) &&
    (quota?.can_create ?? true) &&
    (unlimited || (limit != null && used < limit))

  const openActions = async (entry: TgMeConfigNode & { clientName: string }) => {
    setActiveConfig(entry)
    setFeedback(null)
    setDownloadLink(null)
    setPlatform(guessInstallPlatform())
    setSheetLoading(true)
    try {
      const data = await getTgConfigFiles(entry.config_id)
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
      const result = await sendTgConfig(activeConfig.config_id, {
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
      const link = await getTgQrLink(activeConfig.config_id, selectedPath)
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
    if (shareViaTelegram(downloadLink.url, `VPN-конфиг: ${activeConfig?.clientName ?? ''}`)) {
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

  const handlePlanAdd = async () => {
    setPlanAdding(true)
    try {
      await createTgMePlanConfig()
      void load({ silent: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка добавления конфига')
    } finally {
      setPlanAdding(false)
    }
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

  const nodeCount = allNodes.length
  const groupCount = visibleGroups.length

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Конфиги"
        subtitle={
          nodeCount > 0
            ? `${nodeCount} конфиг${nodeCount === 1 ? '' : 'а'} на ${groupCount} имени${
                groupCount !== 1 ? 'ах' : ''
              }`
            : 'Создайте или получите VPN-профиль'
        }
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      {canCreate && (
        <Button type="button" className="w-full gap-2" onClick={handlePlanAdd} disabled={planAdding}>
          <Plus size={18} aria-hidden />
          {planAdding ? 'Добавление…' : 'Добавить конфиг'}
        </Button>
      )}

      {!canCreate && (
        <p className="text-xs text-muted-foreground">
          Запросите ещё конфиг у администратора.
        </p>
      )}

      {quota && !unlimited && (
        <p className="text-xs text-muted-foreground">
          Лимит: {used} из {limit} имён{!canCreate ? ' — лимит достигнут' : ''}
        </p>
      )}

      {error && <p className="text-destructive text-sm">{error}</p>}

      {allNodes.length > 0 && (
        <>
          <MiniListToolbar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder={isAdmin ? 'Поиск по имени…' : 'Поиск по имени…'}
            protocol={protocol}
            onProtocolChange={setProtocol}
            protocolCounts={protocolCounts}
            protocolOptions={protocolOptions}
          />

          {hasActiveFilters && (
            <p className="tg-mini-results-meta">
              Показано {filteredNodes.length}
              {filteredNodes.length !== allNodes.length ? ` из ${allNodes.length}` : ''}
            </p>
          )}
        </>
      )}

      {visibleGroups.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <FileKey size={22} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Нет конфигов</p>
          <p className="text-xs text-muted-foreground">
            {canCreate ? 'Добавьте первый конфиг кнопкой выше' : 'Конфиги появятся после создания в панели'}
          </p>
        </div>
      ) : filteredNodes.length === 0 ? (
        <div className="tg-mini-filter-empty">
          <Search size={20} className="text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">Ничего не найдено</p>
          <p className="text-xs text-muted-foreground">Измените поиск или сбросьте фильтр</p>
          <Button type="button" variant="outline" size="sm" className="mt-1" onClick={resetFilters}>
            Сбросить
          </Button>
        </div>
      ) : (
        <>
          {visibleGroups.map((group) => {
            const visibleNodes = group.nodes.filter((n) =>
              protocol === 'all' || matchesProtocolFilter(n.vpn_type, protocol),
            )
            if (visibleNodes.length === 0) return null
            return (
              <Card key={group.name} className="tg-mini-config-card">
                <CardContent className="p-0">
                  <div className="flex w-full items-center justify-between gap-3 p-3 border-b border-border/80">
                    <div className="min-w-0">
                      <span className="font-medium truncate">{group.name}</span>
                      <p className="text-xs text-muted-foreground">
                        {visibleNodes.length} узел{visibleNodes.length !== 1 ? 'а' : ''}
                      </p>
                    </div>
                  </div>
                  <div className="divide-y divide-border/80">
                    {visibleNodes.map((entry) => {
                      const created = entry.config_id != null
                      return (
                        <button
                          key={`${group.name}-${entry.config_id ?? entry.node_id}`}
                          type="button"
                          className="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-muted/50"
                          onClick={() => void openActions({ ...entry, clientName: group.name })}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium">{entry.node_label}</span>
                              <span className={`tg-mini-protocol-badge ${vpnTypeBadgeClass(entry.vpn_type)}`}>
                                {vpnTypeLabel(entry.vpn_type)}
                              </span>
                              <Badge variant={created ? 'success' : 'secondary'} className="text-[10px]">
                                {created ? 'создан' : 'не создан'}
                              </Badge>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              узел ID {entry.node_id}{created ? ` · конфиг #${entry.config_id}` : ''}
                            </p>
                          </div>
                          <ChevronRight size={18} className="shrink-0 text-muted-foreground" aria-hidden />
                        </button>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </>
      )}

      <ConfigActionDialog
        config={
          activeConfig
            ? {
                id: activeConfig.config_id,
                client_name: activeConfig.clientName,
                vpn_type: activeConfig.vpn_type,
                is_mine: true,
              }
            : null
        }
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
        isForeignConfig={false}
        ownerLabel={null}
        canManage={activeConfig ? true : false}
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
        awg2Enabled={awg2Enabled}
        quota={quota}
        onCreated={() => void load({ silent: true })}
      />
    </div>
  )
}
