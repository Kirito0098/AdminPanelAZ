import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronRight, FileKey, Plus, Search } from 'lucide-react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import ConfigActionDialog, { type ConfigFeedback } from '@/tg-mini/components/ConfigActionDialog'
import CreateConfigDialog from '@/tg-mini/components/CreateConfigDialog'
import MiniListToolbar, {
  matchesProtocolFilter,
  matchesSearchQuery,
  type ProtocolFilter,
} from '@/tg-mini/components/MiniListToolbar'
import MiniNodeSelector from '@/tg-mini/components/MiniNodeSelector'
import MiniPageHeader from '@/tg-mini/components/MiniPageHeader'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'
import {
  getTgConfigs,
  getTgPanelConfigFiles,
  getTgPanelQrLink,
  sendTgPanelConfig,
} from '@/tg-mini/api'
import { guessInstallPlatform } from '@/tg-mini/lib/platformMeta'
import { splitProfileFilesByRoute } from '@/tg-mini/lib/profileFiles'
import { copyText, openExternalLink, shareViaTelegram } from '@/tg-mini/lib/shareDownloadLink'
import { vpnTypeBadgeClass, vpnTypeLabel } from '@/tg-mini/lib/vpnLabels'
import type { InstallPlatform, TgMiniConfig, TgMiniConfigFile, TgMiniQrLink } from '@/types'

const canShareInTelegram = typeof window.Telegram?.WebApp?.shareUrl === 'function'

/** Admin «Конфиги»: все конфиги на активном узле, полное управление (без QR и CSV). */
export default function AdminConfigs() {
  const { settings, features } = useTgAuth()
  const [configs, setConfigs] = useState<TgMiniConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [protocol, setProtocol] = useState<ProtocolFilter>('all')
  const [showCreate, setShowCreate] = useState(false)
  const [activeConfig, setActiveConfig] = useState<TgMiniConfig | null>(null)
  const [files, setFiles] = useState<TgMiniConfigFile[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [sheetLoading, setSheetLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [feedback, setFeedback] = useState<ConfigFeedback | null>(null)
  const [downloadLink, setDownloadLink] = useState<TgMiniQrLink | null>(null)
  const [platform, setPlatform] = useState<InstallPlatform>(() => guessInstallPlatform())

  const load = useCallback(async (options?: { silent?: boolean }) => {
    if (options?.silent) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const data = await getTgConfigs()
      setConfigs(data.configs)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openvpnEnabled = Boolean(features.openvpn ?? true)
  const wireguardEnabled = Boolean(features.wireguard ?? true) || Boolean(features.amneziawg)
  const awg2Enabled = Boolean(features.awg2)

  const protocolCounts = useMemo(
    () => ({
      all: configs.length,
      openvpn: configs.filter((c) => c.vpn_type === 'openvpn').length,
      wireguard: configs.filter((c) => c.vpn_type === 'wireguard').length,
      amneziawg2: configs.filter((c) => c.vpn_type === 'amneziawg2').length,
    }),
    [configs],
  )

  const filtered = useMemo(
    () =>
      configs.filter(
        (config) =>
          matchesProtocolFilter(config.vpn_type, protocol) &&
          matchesSearchQuery(
            `${config.client_name} ${config.owner_username ?? ''}`,
            search,
          ),
      ),
    [configs, protocol, search],
  )

  const openActions = async (config: TgMiniConfig) => {
    setActiveConfig(config)
    setFeedback(null)
    setDownloadLink(null)
    setPlatform(guessInstallPlatform())
    setSheetLoading(true)
    try {
      const data = await getTgPanelConfigFiles(config.id)
      setFiles(data.files)
      const { vpn, antizapret } = splitProfileFilesByRoute(data.files)
      setSelectedPath((vpn[0] ?? antizapret[0] ?? data.files[0])?.path ?? '')
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

  const handleSend = async (destination: 'self' | 'owner') => {
    if (!activeConfig || !selectedPath) return
    setActionLoading(true)
    setFeedback(null)
    try {
      const result = await sendTgPanelConfig(activeConfig.id, {
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
      const link = await getTgPanelQrLink(activeConfig.id, selectedPath)
      setDownloadLink(link)
      const copied = await copyText(link.url)
      setFeedback({
        tone: 'success',
        text: copied ? 'Ссылка создана и скопирована' : 'Ссылка создана',
      })
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
      text: copied ? 'Ссылка скопирована' : 'Не удалось скопировать',
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
      text: copied ? 'Поделиться недоступно — ссылка скопирована' : 'Скопируйте ссылку вручную',
    })
  }

  const handleOpenDownloadLink = () => {
    if (!downloadLink) return
    openExternalLink(downloadLink.url)
    setFeedback({ tone: 'info', text: 'Ссылка открыта (если она одноразовая — на другом устройстве не сработает)' })
  }

  return (
    <div className="tg-mini-dashboard space-y-3">
      <MiniPageHeader
        title="Конфиги"
        subtitle={`${configs.length} конфиг${configs.length === 1 ? '' : 'ов'} на активном сервере`}
        onRefresh={() => void load({ silent: true })}
        refreshing={refreshing}
      />

      <MiniNodeSelector onChanged={() => void load({ silent: true })} />

      <Button type="button" className="w-full gap-2" onClick={() => setShowCreate(true)}>
        <Plus size={18} aria-hidden />
        Создать конфиг
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <MiniListToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Имя клиента или владелец…"
        protocol={protocol}
        onProtocolChange={setProtocol}
        protocolCounts={protocolCounts}
        protocolOptions={['all', 'openvpn', 'wireguard', 'amneziawg2']}
      />

      {loading && configs.length === 0 ? (
        <div className="tg-mini-skeleton tg-mini-skeleton-section" aria-busy="true" />
      ) : filtered.length === 0 ? (
        <div className="tg-mini-filter-empty">
          {configs.length === 0 ? <FileKey size={22} className="text-muted-foreground" aria-hidden /> : <Search size={20} className="text-muted-foreground" aria-hidden />}
          <p className="text-sm font-medium">
            {configs.length === 0 ? 'Нет конфигов' : 'Ничего не найдено'}
          </p>
          <p className="text-xs text-muted-foreground">
            {configs.length === 0
              ? 'Создайте первый конфиг кнопкой выше'
              : 'Измените поиск или сбросьте фильтр'}
          </p>
        </div>
      ) : (
        filtered.map((config) => (
          <Card key={config.id} className="tg-mini-config-card">
            <CardContent className="p-0">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 p-3 text-left hover:bg-muted/50"
                onClick={() => void openActions(config)}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">{config.client_name}</span>
                    <span className={`tg-mini-protocol-badge ${vpnTypeBadgeClass(config.vpn_type)}`}>
                      {vpnTypeLabel(config.vpn_type)}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {config.owner_username ? `Владелец: ${config.owner_username}` : 'Без владельца'}
                  </p>
                </div>
                <ChevronRight size={18} className="shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </CardContent>
          </Card>
        ))
      )}

      <ConfigActionDialog
        config={activeConfig}
        files={files}
        selectedPath={selectedPath}
        onSelectedPathChange={(path) => {
          setSelectedPath(path)
          setDownloadLink(null)
          setFeedback(null)
        }}
        platform={platform}
        onPlatformChange={setPlatform}
        loading={sheetLoading}
        actionLoading={actionLoading}
        feedback={feedback}
        downloadLink={downloadLink}
        canShareLink={canShareInTelegram}
        isForeignConfig={Boolean(activeConfig && !activeConfig.is_mine)}
        ownerLabel={activeConfig?.owner_username ?? null}
        canManage
        isAdmin
        onClose={closeSheet}
        onSend={(destination) => void handleSend(destination)}
        onCreateDownloadLink={() => void handleCreateDownloadLink()}
        onCopyDownloadLink={() => void handleCopyDownloadLink()}
        onShareDownloadLink={() => void handleShareDownloadLink()}
        onOpenDownloadLink={handleOpenDownloadLink}
        onConfigDeleted={() => {
          closeSheet()
          void load({ silent: true })
        }}
        onConfigUpdated={() => void load({ silent: true })}
      />

      <CreateConfigDialog
        open={showCreate}
        onOpenChange={setShowCreate}
        isAdmin
        currentUserId={settings?.user_id}
        openvpnEnabled={openvpnEnabled}
        wireguardEnabled={wireguardEnabled}
        awg2Enabled={awg2Enabled}
        quota={null}
        onCreated={() => void load({ silent: true })}
      />
    </div>
  )
}
