import { useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  bulkConfigOp,
  createConfigTag,
  deleteConfig,
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
import ConfigCard from '@/components/dashboard/ConfigCard'
import ClientActionsDialog from '@/components/dashboard/ClientActionsDialog'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import EmptyState from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  configMatchesTab,
  getPolicyForConfig,
  matchesFilter,
  protocolLabel,
  type ClientFilter,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import { useFeatureModules } from '@/context/FeatureModulesContext'
import { useProgress } from '@/context/ProgressContext'
import type { ClientAccessPolicy, ConfigTag, OpenVpnGroupOption, User, UserRole, VpnConfig } from '@/types'
import { FileKey, Filter, Search, Shield, Tag, X } from 'lucide-react'

interface ConfigCardsSectionProps {
  configs: VpnConfig[]
  policies: Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  userRole: UserRole
  ownerCandidates?: User[]
  filesLoading?: boolean
  onRefresh: () => Promise<void>
  onQr: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onDownload: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onNotifySuccess: (msg: string) => void
  onNotifyError: (msg: string) => void
}

const TAB_ORDER: ProtocolTab[] = ['openvpn', 'amneziawg', 'wireguard']

type ConfirmAction = 'delete' | 'block' | 'unblock' | null
type BulkAction = 'block_temp' | 'block_perm' | 'unblock' | 'delete' | 'renew_cert' | null
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
  filesLoading = false,
  onRefresh,
  onQr,
  onDownload,
  onNotifySuccess,
  onNotifyError,
}: ConfigCardsSectionProps) {
  const { isEnabled } = useFeatureModules()
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
  const [bulkBusy, setBulkBusy] = useState(false)
  const [newTagName, setNewTagName] = useState('')

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
          .sort((a, b) => a.client_name.localeCompare(b.client_name, 'ru'))
        return acc
      },
      {} as Record<ProtocolTab, VpnConfig[]>,
    )
  }, [configs, search, filter, policies, tagFilterIds])

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

  const runBulkAction = async () => {
    if (!bulkAction) return
    const configIds = [...selectedIds]
    const tagIds = tagFilterIds
    if (!configIds.length && !tagIds.length) {
      onNotifyError('Выберите клиентов или фильтр по тегу')
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
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield size={18} />
            Список клиентов
          </CardTitle>
          <CardDescription>
            {activeCount > 0
              ? `${configs.length} конфигураци${configs.length === 1 ? 'я' : configs.length < 5 ? 'и' : 'й'} · ${activeCount} в текущей вкладке`
              : 'Клиенты не найдены'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ProtocolTab)}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <TabsList className="h-auto flex-wrap justify-start">
                {visibleTabs.includes('openvpn') && (
                  <TabsTrigger value="openvpn" className="gap-1.5">
                    OpenVPN
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.openvpn}
                    </Badge>
                  </TabsTrigger>
                )}
                {visibleTabs.includes('amneziawg') && (
                  <TabsTrigger value="amneziawg" className="gap-1.5">
                    AmneziaWG
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.amneziawg}
                    </Badge>
                  </TabsTrigger>
                )}
                {visibleTabs.includes('wireguard') && (
                  <TabsTrigger value="wireguard" className="gap-1.5">
                    WireGuard
                    <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                      {tabCounts.wireguard}
                    </Badge>
                  </TabsTrigger>
                )}
              </TabsList>

              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                {activeTab === 'openvpn' && openvpnTabEnabled && openvpnGroupOptions.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1 rounded-md border bg-muted/30 p-1">
                    {openvpnGroupOptions.map((option) => (
                      <Button
                        key={option.key}
                        type="button"
                        size="sm"
                        variant={openvpnGroup === option.key ? 'default' : 'ghost'}
                        className="h-7 px-2 text-xs"
                        disabled={groupBusy}
                        onClick={() => void handleOpenVpnGroupChange(option.key)}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                )}
                <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Поиск по имени..."
                    className="pl-8 pr-8"
                  />
                  {search && (
                    <button
                      type="button"
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      onClick={() => setSearch('')}
                      title="Очистить поиск"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {isAdmin && (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Filter size={12} />
                    Фильтр:
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
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Tag size={12} />
                    Теги:
                  </span>
                  {allTags.map((tag) => (
                    <Button
                      key={tag.id}
                      type="button"
                      size="sm"
                      variant={tagFilterIds.includes(tag.id) ? 'default' : 'outline'}
                      className="h-7 text-xs"
                      onClick={() => toggleTagFilter(tag.id)}
                    >
                      {tag.name}
                    </Button>
                  ))}
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
                  <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/30 p-2">
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
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => setBulkAction('block_temp')}>
                      Block
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => setBulkAction('unblock')}>
                      Unblock
                    </Button>
                    <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => setBulkAction('renew_cert')}>
                      Renew cert
                    </Button>
                    <Button type="button" size="sm" variant="destructive" className="h-7 text-xs" onClick={() => setBulkAction('delete')}>
                      Delete
                    </Button>
                  </div>
                )}
              </div>
            )}

            {visibleTabs.map((tab) => (
              <TabsContent key={tab} value={tab} className="mt-4">
                {filteredByTab[tab].length === 0 ? (
                  <EmptyState
                    icon={FileKey}
                    title="Нет клиентов"
                    description={
                      search || filter !== 'all'
                        ? `Нет результатов для «${protocolLabel(tab)}» с текущими фильтрами`
                        : `В категории ${protocolLabel(tab)} пока нет конфигураций`
                    }
                    className="py-8"
                  />
                ) : (
                  <div className="grid auto-rows-fr gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
                        onBlock={isAdmin ? () => openConfirm('block', config) : undefined}
                        onUnblock={isAdmin ? () => openConfirm('unblock', config) : undefined}
                        onDelete={
                          isAdmin || userRole === 'user' ? () => openConfirm('delete', config) : undefined
                        }
                        showQrDownloads={qrDownloadsEnabled}
                        showTrafficLink={trafficLinkEnabled}
                      />
                    ))}
                  </div>
                )}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

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
        open={bulkAction != null}
        onOpenChange={(open) => {
          if (!open && !bulkBusy) setBulkAction(null)
        }}
        title={
          bulkAction === 'delete'
            ? 'Массовое удаление'
            : bulkAction === 'renew_cert'
              ? 'Массовое продление сертификатов'
              : bulkAction === 'block_temp'
                ? 'Массовая блокировка'
                : 'Массовая операция'
        }
        description={
          <>
            Будет обработано выбранных: {selectedCount}
            {tagFilterIds.length > 0 ? ` + клиенты с выбранными тегами` : ''}. Операция выполняется в фоне.
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
      </ConfirmDialog>
    </>
  )
}
