import { useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  deleteConfig,
  openvpnPermanentBlock,
  openvpnTempBlock,
  openvpnUnblock,
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
import type { ClientAccessPolicy, UserRole, VpnConfig } from '@/types'
import { FileKey, Filter, Search, Shield, X } from 'lucide-react'

interface ConfigCardsSectionProps {
  configs: VpnConfig[]
  policies: Record<string, { openvpn: ClientAccessPolicy; wireguard: ClientAccessPolicy }>
  userRole: UserRole
  onRefresh: () => Promise<void>
  onQr: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onDownload: (config: VpnConfig, path: string, filename: string) => Promise<void>
  onNotifySuccess: (msg: string) => void
  onNotifyError: (msg: string) => void
}

const TAB_ORDER: ProtocolTab[] = ['openvpn', 'amneziawg', 'wireguard']

type ConfirmAction = 'delete' | 'block' | 'unblock' | null
type LoadingKey = `${number}-${'download' | 'qr' | 'block' | 'unblock' | 'delete'}` | null

function useVisibleTabs(): ProtocolTab[] {
  const { isEnabled } = useFeatureModules()
  return TAB_ORDER.filter((tab) => {
    if (tab === 'openvpn') return isEnabled('openvpn')
    return isEnabled('wireguard')
  })
}

export default function ConfigCardsSection({
  configs,
  policies,
  userRole,
  onRefresh,
  onQr,
  onDownload,
  onNotifySuccess,
  onNotifyError,
}: ConfigCardsSectionProps) {
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

  const isAdmin = userRole === 'admin'

  const filteredByTab = useMemo(() => {
    const q = search.trim().toLowerCase()
    return TAB_ORDER.reduce(
      (acc, tab) => {
        acc[tab] = configs
          .filter((c) => configMatchesTab(c, tab))
          .filter((c) => !q || c.client_name.toLowerCase().includes(q))
          .filter((c) => matchesFilter(c, tab, filter, getPolicyForConfig(c, policies)))
          .sort((a, b) => a.client_name.localeCompare(b.client_name, 'ru'))
        return acc
      },
      {} as Record<ProtocolTab, VpnConfig[]>,
    )
  }, [configs, search, filter, policies])

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
              <div className="mt-3 flex flex-wrap items-center gap-2">
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
                  <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {filteredByTab[tab].map((config) => (
                      <ConfigCard
                        key={`${tab}-${config.id}`}
                        config={config}
                        tab={tab}
                        policy={getPolicyForConfig(config, policies)}
                        userRole={userRole}
                        loadingAction={getCardLoading(config.id)}
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
        open={!!selectedConfig}
        onOpenChange={(open) => !open && setSelectedConfig(null)}
        onRefresh={onRefresh}
        onQr={onQr}
        onDownload={onDownload}
        onNotifySuccess={onNotifySuccess}
        onNotifyError={onNotifyError}
      />

      <ConfirmDialog
        open={confirmAction === 'delete'}
        onOpenChange={(open) => !open && closeConfirm()}
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
        onOpenChange={(open) => !open && closeConfirm()}
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
        onOpenChange={(open) => !open && closeConfirm()}
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
    </>
  )
}
