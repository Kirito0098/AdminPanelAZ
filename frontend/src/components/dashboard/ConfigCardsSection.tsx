import {
  ApiError,
  bulkConfigOp,
  createConfigTag,
  deleteConfig,
  deleteConfigTag,
  getConfigTags,
  getOpenVpnGroup,
  openvpnPermanentBlock,
  openvpnTempBlock,
  openvpnUnblock,
  setOpenVpnGroup,
  wgPermanentBlock,
  wgTempBlock,
  wgUnblock,
} from '@/api/client'
import ClientActionsDialog from '@/components/dashboard/ClientActionsDialog'
import ConfigCard from '@/components/dashboard/ConfigCard'
import ConfigCardViewSettings from '@/components/dashboard/ConfigCardViewSettings'
import ConfigOwnerSelect from '@/components/dashboard/ConfigOwnerSelect'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useProgress } from '@/context/ProgressContext'
import { useHaReplicaReadonly } from '@/hooks/useHaReplicaReadonly'
import {
  configMatchesTab,
  getPolicyForConfig,
  isConfigConnected,
  matchesFilter,
  matchesPresenceFilter,
  protocolLabel,
  type ClientConnectionMap,
  type ClientFilter,
  type ClientPresenceFilter,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { configOwnerCandidates } from '@/lib/configOwners'
import {
  DEFAULT_CONFIG_CARD_VIEW_PREFS,
  gridColsClass,
  loadConfigCardViewPrefs,
  saveConfigCardViewPrefs,
  type ConfigCardViewPrefs,
} from '@/lib/configCardViewPrefs'
import { cn } from '@/lib/utils'
import type { ClientAccessPolicy, ConfigTag, OpenVpnGroupOption, User, UserRole, VpnConfig } from '@/types'
import { FileKey, Filter, Search, Shield, Tag, Wifi, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

interface ConfigCardsSectionProps {
  configs: VpnConfig[]
  policies: Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  userRole: UserRole
  ownerCandidates?: User[]
  connectionMap?: ClientConnectionMap | null
  filesLoading?: boolean
  onRefresh: () => Promise<void>
  onQr: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onDownload: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onNotifySuccess: (msg: string) => void
  onNotifyError: (msg: string) => void
}

const TAB_ORDER: ProtocolTab[] = ['openvpn', 'amneziawg', 'wireguard']

type ConfirmAction = 'delete' | 'block' | 'unblock' | null
type BulkAction = 'block_temp' | 'block_perm' | 'unblock' | 'delete' | 'renew_cert' | 'change_owner' | null
type LoadingKey = `${number}-${'download' | 'qr' | 'block' | 'unblock' | 'delete'}` | null

function useVisibleTabs(): ProtocolTab[] {
  const { isEnabled } = useFeatureModules()
  return TAB_ORDER.filter((tab) => {
    if (tab === 'openvpn') return isEnabled('openvpn')
    if (tab === 'amneziawg') return isEnabled('amneziawg')
    return isEnabled('wireguard')
  })
}

export default function ConfigCardsSection({
  configs,
  policies,
  userRole,
  ownerCandidates = [],
  connectionMap = null,
  filesLoading = false,
  onRefresh,
  onQr,
  onDownload,
  onNotifySuccess,
  onNotifyError,
}: ConfigCardsSectionProps) {
  const { isEnabled } = useFeatureModules()
  const haReplicaReadonly = useHaReplicaReadonly()
  const { trackBackgroundTask } = useProgress()
  const qrDownloadsEnabled = isEnabled('qr_downloads')
  const trafficLinkEnabled = isEnabled('traffic_sync')
  const visibleTabs = useVisibleTabs()
  const [activeTab, setActiveTab] = useState<ProtocolTab>(visibleTabs[0] ?? 'openvpn')
  useEffect(() => {
    if (!visibleTabs.includes(activeTab) && visibleTabs.length > 0) {
      setActiveTab(visibleTabs[0])
    }
  }, [activeTab, visibleTabs])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ClientFilter>('all')
  const [presenceFilter, setPresenceFilter] = useState<ClientPresenceFilter>('all')
  const [selectedConfig, setSelectedConfig] = useState<VpnConfig | null>(null)
  const [selectedTab, setSelectedTab] = useState<ProtocolTab>('openvpn')
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null)
  const [confirmTarget, setConfirmTarget] = useState<VpnConfig | null>(null)
  const [blockDays, setBlockDays] = useState('7')
  const [actionBusy, setActionBusy] = useState(false)
  const [loadingAction, setLoadingAction] = useState<LoadingKey>(null)
  const [openvpnGroup, setOpenvpnGroup] = useState('GROUP_UDP\\TCP')
  const [openvpnGroupOptions, setOpenvpnGroupOptions] = useState<OpenVpnGroupOption[]>([])
  const [groupBusy, setGroupBusy] = useState(false)
  const [allTags, setAllTags] = useState<ConfigTag[]>([])
  const [tagFilterIds, setTagFilterIds] = useState<number[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkAction, setBulkAction] = useState<BulkAction>(null)
  const [bulkDays, setBulkDays] = useState('7')
  const [bulkOwnerId, setBulkOwnerId] = useState<number | null>(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [newTagName, setNewTagName] = useState('')
  const [tagToDelete, setTagToDelete] = useState<ConfigTag | null>(null)
  const [viewPrefs, setViewPrefs] = useState<ConfigCardViewPrefs>(DEFAULT_CONFIG_CARD_VIEW_PREFS)

  useEffect(() => {
    setViewPrefs(loadConfigCardViewPrefs())
  }, [])

  const handleViewPrefsChange = (next: ConfigCardViewPrefs) => {
    setViewPrefs(next)
    saveConfigCardViewPrefs(next)
  }
  const [tagDeleteBusy, setTagDeleteBusy] = useState(false)

  const isAdmin = userRole === 'admin'
  const openvpnTabEnabled = isEnabled('openvpn')

  useEffect(() => {
    if (!openvpnTabEnabled) return
    void getOpenVpnGroup()
      .then((state) => {
        setOpenvpnGroup(state.group)
        setOpenvpnGroupOptions(state.options)
      })
      .catch(() => {
        /* group selector is optional; ignore load errors */
      })
  }, [openvpnTabEnabled])

  useEffect(() => {
    if (!isAdmin) return
    void getConfigTags()
      .then(setAllTags)
      .catch(() => setAllTags([]))
  }, [isAdmin, configs.length])

  const matchesTagFilter = (config: VpnConfig) => {
    if (!tagFilterIds.length) return true
    const configTagIds = new Set((config.tags ?? []).map((t) => t.id))
    return tagFilterIds.some((id) => configTagIds.has(id))
  }

  const filteredByTab = useMemo(() => {
    const q = search.trim().toLowerCase()
    return TAB_ORDER.reduce(
      (acc, tab) => {
        acc[tab] = configs
          .filter((c) => configMatchesTab(c, tab))
          .filter((c) => matchesTagFilter(c))
          .filter((c) => !q || c.client_name.toLowerCase().includes(q))
          .filter((c) => matchesFilter(c, tab, filter, getPolicyForConfig(c, policies)))
          .filter((c) =>
            matchesPresenceFilter(c, tab, presenceFilter, getPolicyForConfig(c, policies), connectionMap),
          )
          .sort((a, b) => a.client_name.localeCompare(b.client_name, 'ru'))
        return acc
      },
      {} as Record<ProtocolTab, VpnConfig[]>,
    )
  }, [configs, search, filter, presenceFilter, policies, tagFilterIds, connectionMap])

  const tabCounts = useMemo(
    () =>
      TAB_ORDER.reduce(
        (acc, tab) => {
          acc[tab] = configs.filter((c) => configMatchesTab(c, tab)).length
          return acc
        },
        {} as Record<ProtocolTab, number>,
      ),
    [configs],
  )

  const activeCount = filteredByTab[activeTab]?.length ?? 0

  const copyName = async (name: string) => {
    try {
      await navigator.clipboard.writeText(name)
      onNotifySuccess(`Имя «${name}» скопировано`)
    } catch {
      onNotifyError('Не удалось скопировать имя')
    }
  }

  const setCardLoading = (configId: number, action: 'download' | 'qr' | 'block' | 'unblock' | 'delete' | null) => {
    setLoadingAction(action ? `${configId}-${action}` : null)
  }

  const handleCardDownload = async (config: VpnConfig, path: string, filename: string) => {
    setCardLoading(config.id, 'download')
    try {
      await onDownload(config, path, filename)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка скачивания')
    } finally {
      setCardLoading(config.id, null)
    }
  }

  const handleCardQr = async (config: VpnConfig, path: string, filename: string) => {
    setCardLoading(config.id, 'qr')
    try {
      await onQr(config, path, filename)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка генерации QR')
    } finally {
      setCardLoading(config.id, null)
    }
  }

  const openConfirm = (action: ConfirmAction, config: VpnConfig) => {
    setConfirmAction(action)
    setConfirmTarget(config)
    if (action === 'block') setBlockDays('7')
  }

  const closeConfirm = () => {
    setConfirmAction(null)
    setConfirmTarget(null)
  }

  const runConfirm = async () => {
    if (!confirmTarget || !confirmAction) return
    setActionBusy(true)
    setCardLoading(confirmTarget.id, confirmAction)
    try {
      const name = confirmTarget.client_name
      const isOvpn = confirmTarget.vpn_type === 'openvpn'

      if (confirmAction === 'delete') {
        await deleteConfig(confirmTarget.id)
        onNotifySuccess(`Клиент «${name}» удалён`)
        if (selectedConfig?.id === confirmTarget.id) setSelectedConfig(null)
        closeConfirm()
        await onRefresh()
        return
      }

      if (confirmAction === 'unblock') {
        if (isOvpn) {
          await openvpnUnblock(name)
        } else {
          await wgUnblock(name)
        }
        onNotifySuccess('Блокировка снята')
        closeConfirm()
        await onRefresh()
        return
      }

      if (confirmAction === 'block') {
        const days = Number.parseInt(blockDays, 10)
        if (!Number.isFinite(days) || days < 1 || days > 3650) {
          onNotifyError('Срок блокировки: от 1 до 3650 дней')
          return
        }
        if (days >= 3650) {
          if (isOvpn) await openvpnPermanentBlock(name)
          else await wgPermanentBlock(name)
          onNotifySuccess('Клиент заблокирован до ручной разблокировки')
        } else {
          if (isOvpn) await openvpnTempBlock(name, days)
          else await wgTempBlock(name, days)
          onNotifySuccess(`Клиент заблокирован на ${days} дн.`)
        }
        closeConfirm()
        await onRefresh()
      }
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка выполнения действия')
    } finally {
      setActionBusy(false)
      setCardLoading(confirmTarget?.id ?? 0, null)
    }
  }

  const getCardLoading = (configId: number): 'download' | 'qr' | 'block' | 'unblock' | 'delete' | null => {
    if (!loadingAction?.startsWith(`${configId}-`)) return null
    return loadingAction.split('-').slice(1).join('-') as 'download' | 'qr' | 'block' | 'unblock' | 'delete'
  }

  const handleOpenVpnGroupChange = async (group: string) => {
    if (group === openvpnGroup || groupBusy) return
    setGroupBusy(true)
    try {
      const state = await setOpenVpnGroup(group)
      setOpenvpnGroup(state.group)
      setOpenvpnGroupOptions(state.options)
      await onRefresh()
      onNotifySuccess('Группа OpenVPN обновлена')
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка смены группы OpenVPN')
    } finally {
      setGroupBusy(false)
    }
  }

  const toggleTagFilter = (tagId: number) => {
    setTagFilterIds((prev) =>
      prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId],
    )
  }

  const handleCreateTag = async () => {
    const name = newTagName.trim()
    if (!name) return
    try {
      const tag = await createConfigTag({ name })
      setAllTags((prev) => [...prev, tag].sort((a, b) => a.name.localeCompare(b.name, 'ru')))
      setNewTagName('')
      onNotifySuccess(`Тег «${name}» создан`)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка создания тега')
    }
  }

  const handleDeleteTag = async () => {
    if (!tagToDelete) return
    const deletedName = tagToDelete.name
    setTagDeleteBusy(true)
    try {
      await deleteConfigTag(tagToDelete.id)
      setAllTags((prev) => prev.filter((t) => t.id !== tagToDelete.id))
      setTagFilterIds((prev) => prev.filter((id) => id !== tagToDelete.id))
      setTagToDelete(null)
      await onRefresh()
      onNotifySuccess(`Тег «${deletedName}» удалён`)
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка удаления тега')
    } finally {
      setTagDeleteBusy(false)
    }
  }

  const toggleSelected = (configId: number, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(configId)
      else next.delete(configId)
      return next
    })
  }

  const selectAllVisible = () => {
    const visible = filteredByTab[activeTab] ?? []
    setSelectedIds(new Set(visible.map((c) => c.id)))
  }

  const clearSelection = () => setSelectedIds(new Set())

  const openBulkAction = (action: Exclude<BulkAction, null>) => {
    setBulkAction(action)
    if (action === 'change_owner' && bulkOwnerId == null) {
      const firstOwner = configOwnerCandidates(ownerCandidates)[0]
      if (firstOwner) setBulkOwnerId(firstOwner.id)
    }
  }

  const runBulkAction = async () => {
    if (!bulkAction) return
    const configIds = [...selectedIds]
    const tagIds = tagFilterIds
    if (!configIds.length && !tagIds.length) {
      onNotifyError('Выберите клиентов или фильтр по тегу')
      return
    }
    if (bulkAction === 'change_owner' && !bulkOwnerId) {
      onNotifyError('Выберите нового владельца')
      return
    }
    setBulkBusy(true)
    try {
      const days = Number.parseInt(bulkDays, 10)
      const resp = await bulkConfigOp({
        operation: bulkAction,
        config_ids: configIds,
        tag_ids: tagIds,
        block_days: bulkAction === 'block_temp' ? days : undefined,
        renew_cert_days: bulkAction === 'renew_cert' ? days : undefined,
        owner_id: bulkAction === 'change_owner' ? bulkOwnerId ?? undefined : undefined,
      })
      setBulkAction(null)
      clearSelection()
      trackBackgroundTask(resp.task_id, {
        okMessage: 'Массовая операция завершена',
        onComplete: () => void onRefresh(),
      })
      onNotifySuccess('Массовая операция запущена')
    } catch (err) {
      onNotifyError(err instanceof ApiError ? err.message : 'Ошибка массовой операции')
    } finally {
      setBulkBusy(false)
    }
  }

  const selectedCount = selectedIds.size

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-border/80 bg-card shadow-sm">
        <div className="h-1 bg-gradient-to-r from-primary/80 via-primary/40 to-transparent" />
        <CardHeader className="border-b border-border/60 bg-muted/15 pb-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <Shield size={18} />
                Список клиентов
              </CardTitle>
              <CardDescription className="mt-1">
                {activeCount > 0
                  ? `${configs.length} конфигураци${configs.length === 1 ? 'я' : configs.length < 5 ? 'и' : 'й'} · ${activeCount} в текущей вкладке`
                  : 'Клиенты не найдены'}
              </CardDescription>
            </div>
            <div className="flex w-full items-center gap-2 lg:max-w-md">
              <div className="relative min-w-0 flex-1">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск по имени..."
                  className="h-10 bg-background pl-9 pr-9"
                />
                {search && (
                  <button
                    type="button"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setSearch('')}
                    title="Очистить поиск"
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              <ConfigCardViewSettings prefs={viewPrefs} onChange={handleViewPrefsChange} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4 sm:p-5">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ProtocolTab)}>
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <TabsList className="h-auto w-full flex-wrap justify-start bg-muted/40 p-1 sm:w-auto">
                {visibleTabs.includes('openvpn') && (
                  <TabsTrigger value="openvpn" className="gap-1.5 data-[state=active]:shadow-sm">
                    OpenVPN
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.openvpn}
                    </Badge>
                  </TabsTrigger>
                )}
                {visibleTabs.includes('amneziawg') && (
                  <TabsTrigger value="amneziawg" className="gap-1.5 data-[state=active]:shadow-sm">
                    AmneziaWG
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.amneziawg}
                    </Badge>
                  </TabsTrigger>
                )}
                {visibleTabs.includes('wireguard') && (
                  <TabsTrigger value="wireguard" className="gap-1.5 data-[state=active]:shadow-sm">
                    WireGuard
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.wireguard}
                    </Badge>
                  </TabsTrigger>
                )}
              </TabsList>

              {activeTab === 'openvpn' && openvpnTabEnabled && openvpnGroupOptions.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 rounded-xl border bg-muted/30 p-1">
                  {openvpnGroupOptions.map((option) => (
                    <Button
                      key={option.key}
                      type="button"
                      size="sm"
                      variant={openvpnGroup === option.key ? 'default' : 'ghost'}
                      className="h-8 px-2.5 text-xs"
                      disabled={groupBusy}
                      onClick={() => void handleOpenVpnGroupChange(option.key)}
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              )}
            </div>

            {isAdmin && (
              <div className="space-y-3 rounded-xl border border-dashed bg-muted/15 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Filter size={13} />
                    Срок
                  </span>
                  {(
                    [
                      ['all', 'Все'],
                      ['active', 'Активные'],
                      ['expiring', 'Истекают'],
                      ['expired', 'Истекшие'],
                    ] as const
                  ).map(([key, label]) => (
                    <Button
                      key={key}
                      type="button"
                      size="sm"
                      variant={filter === key ? 'default' : 'outline'}
                      onClick={() => setFilter(key)}
                      className="h-7 text-xs"
                    >
                      {label}
                    </Button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Wifi size={13} />
                    Состояние
                  </span>
                  {(
                    [
                      ['all', 'Все'],
                      ['online', 'Онлайн'],
                      ['offline', 'Офлайн'],
                      ['blocked', 'Заблокированные'],
                    ] as const
                  ).map(([key, label]) => (
                    <Button
                      key={key}
                      type="button"
                      size="sm"
                      variant={presenceFilter === key ? 'default' : 'outline'}
                      onClick={() => setPresenceFilter(key)}
                      className="h-7 text-xs"
                    >
                      {label}
                    </Button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Tag size={13} />
                    Теги
                  </span>
                  {allTags.map((tag) => {
                    const active = tagFilterIds.includes(tag.id)
                    return (
                      <span
                        key={tag.id}
                        className={cn(
                          'inline-flex h-7 items-stretch overflow-hidden rounded-md border text-xs',
                          active
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-input bg-background',
                        )}
                      >
                        <button
                          type="button"
                          className={cn('px-2 transition-colors', !active && 'hover:bg-muted')}
                          onClick={() => toggleTagFilter(tag.id)}
                        >
                          {tag.name}
                          {tag.config_count != null && tag.config_count > 0 ? (
                            <span className={cn('ml-1 opacity-70', active && 'opacity-90')}>
                              {tag.config_count}
                            </span>
                          ) : null}
                        </button>
                        <button
                          type="button"
                          title={`Удалить тег «${tag.name}»`}
                          disabled={haReplicaReadonly || tagDeleteBusy}
                          className={cn(
                            'border-l px-1.5 transition-colors disabled:opacity-50',
                            active
                              ? 'border-primary-foreground/25 hover:bg-primary-foreground/10'
                              : 'border-input hover:bg-destructive/10 hover:text-destructive',
                          )}
                          onClick={() => setTagToDelete(tag)}
                        >
                          <X size={12} />
                        </button>
                      </span>
                    )
                  })}
                  <div className="flex items-center gap-1">
                    <Input
                      value={newTagName}
                      onChange={(e) => setNewTagName(e.target.value)}
                      placeholder="Новый тег"
                      className="h-7 w-28 text-xs"
                    />
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => void handleCreateTag()}>
                      +
                    </Button>
                  </div>
                </div>
                {(selectedCount > 0 || tagFilterIds.length > 0) && (
                  <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-background/80 p-2.5">
                    <span className="text-xs text-muted-foreground">
                      Выбрано: {selectedCount}
                      {tagFilterIds.length > 0 ? ` · теги: ${tagFilterIds.length}` : ''}
                    </span>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={selectAllVisible}>
                      Все на вкладке
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={clearSelection}>
                      Сброс
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={haReplicaReadonly} onClick={() => openBulkAction('block_temp')}>
                      Заблокировать
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={haReplicaReadonly} onClick={() => openBulkAction('unblock')}>
                      Разблокировать
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={haReplicaReadonly} onClick={() => openBulkAction('renew_cert')}>
                      Продлить сертификат
                    </Button>
                    {ownerCandidates.length > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        disabled={haReplicaReadonly}
                        onClick={() => openBulkAction('change_owner')}
                      >
                        Сменить владельца
                      </Button>
                    )}
                    <Button type="button" size="sm" variant="destructive" className="h-7 text-xs" disabled={haReplicaReadonly} onClick={() => openBulkAction('delete')}>
                      Удалить
                    </Button>
                  </div>
                )}
              </div>
            )}

            {visibleTabs.map((tab) => (
              <TabsContent key={tab} value={tab} className="mt-2">
                {filteredByTab[tab].length === 0 ? (
                  <EmptyState
                    icon={FileKey}
                    title="Нет клиентов"
                    description={
                      search || filter !== 'all' || presenceFilter !== 'all' || tagFilterIds.length > 0
                        ? `Нет результатов для «${protocolLabel(tab)}» с текущими фильтрами`
                        : `В категории ${protocolLabel(tab)} пока нет конфигураций`
                    }
                    className="py-10"
                  />
                ) : (
                  <div className={cn('grid items-stretch gap-3', gridColsClass(viewPrefs.gridCols))}>
                    {filteredByTab[tab].map((config) => (
                      <ConfigCard
                        key={`${tab}-${config.id}`}
                        config={config}
                        tab={tab}
                        policy={getPolicyForConfig(config, policies)}
                        userRole={userRole}
                        filesLoading={filesLoading}
                        loadingAction={getCardLoading(config.id)}
                        selected={selectedIds.has(config.id)}
                        showSelect={isAdmin}
                        onSelectChange={(checked) => toggleSelected(config.id, checked)}
                        onOpenDetails={() => {
                          setSelectedTab(tab)
                          setSelectedConfig(config)
                        }}
                        onCopyName={() => void copyName(config.client_name)}
                        onDownload={(path, filename) => void handleCardDownload(config, path, filename)}
                        onQr={(path, filename) => void handleCardQr(config, path, filename)}
                        onBlock={isAdmin && !haReplicaReadonly ? () => openConfirm('block', config) : undefined}
                        onUnblock={isAdmin && !haReplicaReadonly ? () => openConfirm('unblock', config) : undefined}
                        onDelete={
                          !haReplicaReadonly && (isAdmin || userRole === 'user')
                            ? () => openConfirm('delete', config)
                            : undefined
                        }
                        showQrDownloads={qrDownloadsEnabled}
                        showTrafficLink={trafficLinkEnabled}
                        isOnline={isConfigConnected(config.client_name, tab, connectionMap)}
                        viewPrefs={viewPrefs}
                      />
                    ))}
                  </div>
                )}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </div>

      <ClientActionsDialog
        config={selectedConfig}
        tab={selectedTab}
        policy={selectedConfig ? getPolicyForConfig(selectedConfig, policies) : undefined}
        userRole={userRole}
        ownerCandidates={ownerCandidates}
        allTags={allTags}
        open={!!selectedConfig}
        onOpenChange={(open) => !open && setSelectedConfig(null)}
        onRefresh={onRefresh}
        onQr={onQr}
        onDownload={onDownload}
        onNotifySuccess={onNotifySuccess}
        onNotifyError={onNotifyError}
        showQrDownloads={qrDownloadsEnabled}
      />

      <ConfirmDialog
        open={confirmAction === 'delete'}
        onOpenChange={(open) => {
          if (!open && !actionBusy) closeConfirm()
        }}
        title="Удалить клиента?"
        description={
          <>Профиль «{confirmTarget?.client_name}» будет удалён без возможности восстановления.</>
        }
        alert={{
          variant: 'danger',
          title: 'Необратимое действие',
          children: 'Все файлы конфигурации и ключи клиента будут удалены с активного узла.',
        }}
        confirmLabel="Удалить"
        destructive
        loading={actionBusy}
        onConfirm={runConfirm}
      />

      <ConfirmDialog
        open={confirmAction === 'unblock'}
        onOpenChange={(open) => {
          if (!open && !actionBusy) closeConfirm()
        }}
        title="Снять блокировку?"
        description={
          <>Разблокировать клиента «{confirmTarget?.client_name}» и восстановить доступ?</>
        }
        confirmLabel="Разблокировать"
        loading={actionBusy}
        onConfirm={runConfirm}
      />

      <ConfirmDialog
        open={confirmAction === 'block'}
        onOpenChange={(open) => {
          if (!open && !actionBusy) closeConfirm()
        }}
        title="Заблокировать клиента"
        description={
          <>
            Укажите срок блокировки для «{confirmTarget?.client_name}». 3650 дней — до ручной
            разблокировки.
          </>
        }
        confirmLabel="Заблокировать"
        destructive
        loading={actionBusy}
        onConfirm={runConfirm}
      >
        <div className="space-y-2">
          <Label htmlFor="blockDays">Срок (дни, 1–3650)</Label>
          <Input
            id="blockDays"
            type="number"
            min={1}
            max={3650}
            value={blockDays}
            onChange={(e) => setBlockDays(e.target.value)}
            autoFocus
          />
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={tagToDelete != null}
        onOpenChange={(open) => {
          if (!open && !tagDeleteBusy) setTagToDelete(null)
        }}
        title="Удалить тег?"
        description={
          <>
            Тег «{tagToDelete?.name}» будет удалён без возможности восстановления.
            {tagToDelete?.config_count != null && tagToDelete.config_count > 0
              ? ` Он будет снят с ${tagToDelete.config_count} клиентов.`
              : ''}
          </>
        }
        confirmLabel="Удалить"
        destructive
        loading={tagDeleteBusy}
        onConfirm={() => void handleDeleteTag()}
      />

      <ConfirmDialog
        open={bulkAction != null}
        onOpenChange={(open) => {
          if (!open && !bulkBusy) setBulkAction(null)
        }}
        title={
          bulkAction === 'delete'
            ? 'Массовое удаление'
            : bulkAction === 'renew_cert'
              ? 'Массовое продление сертификатов'
              : bulkAction === 'change_owner'
                ? 'Массовая смена владельца'
              : bulkAction === 'block_temp'
                ? 'Массовая блокировка'
                : 'Массовая операция'
        }
        description={
          <>
            Будет обработано выбранных: {selectedCount}
            {tagFilterIds.length > 0 ? ` + клиенты с выбранными тегами` : ''}. Операция выполняется в фоне.
            {bulkAction === 'change_owner' && bulkOwnerId
              ? ` Новый владелец: ${ownerCandidates.find((user) => user.id === bulkOwnerId)?.username ?? '—'}.`
              : ''}
          </>
        }
        confirmLabel="Запустить"
        destructive={bulkAction === 'delete'}
        loading={bulkBusy}
        onConfirm={() => void runBulkAction()}
      >
        {(bulkAction === 'block_temp' || bulkAction === 'renew_cert') && (
          <div className="space-y-2">
            <Label htmlFor="bulkDays">
              {bulkAction === 'renew_cert' ? 'Срок сертификата (дни)' : 'Срок блокировки (дни)'}
            </Label>
            <Input
              id="bulkDays"
              type="number"
              min={1}
              max={3650}
              value={bulkDays}
              onChange={(e) => setBulkDays(e.target.value)}
            />
          </div>
        )}
        {bulkAction === 'change_owner' && ownerCandidates.length > 0 && (
          <ConfigOwnerSelect
            id="bulkOwner"
            users={ownerCandidates}
            value={bulkOwnerId}
            onChange={setBulkOwnerId}
            label="Новый владелец"
            description="Будет назначен всем выбранным клиентам и клиентам с выбранными тегами."
          />
        )}
      </ConfirmDialog>
    </>
  )
}
