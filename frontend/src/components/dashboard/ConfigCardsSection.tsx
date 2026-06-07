import { useMemo, useState } from 'react'
import { Search, X } from 'lucide-react'
import ConfigCard from '@/components/dashboard/ConfigCard'
import ClientActionsDialog from '@/components/dashboard/ClientActionsDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  configMatchesTab,
  getPolicyForConfig,
  matchesFilter,
  type ClientFilter,
  type ProtocolTab,
} from '@/lib/configCardUtils'
import type { ClientAccessPolicy, UserRole, VpnConfig } from '@/types'

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
  const [activeTab, setActiveTab] = useState<ProtocolTab>('openvpn')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ClientFilter>('all')
  const [selectedConfig, setSelectedConfig] = useState<VpnConfig | null>(null)
  const [selectedTab, setSelectedTab] = useState<ProtocolTab>('openvpn')

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

  const copyName = async (name: string) => {
    try {
      await navigator.clipboard.writeText(name)
      onNotifySuccess(`Имя «${name}» скопировано`)
    } catch {
      onNotifyError('Не удалось скопировать имя')
    }
  }

  return (
    <>
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as ProtocolTab)} className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <TabsList className="h-auto flex-wrap justify-start">
            <TabsTrigger value="openvpn" className="gap-1.5">
              <span>OpenVPN</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold">{tabCounts.openvpn}</span>
            </TabsTrigger>
            <TabsTrigger value="amneziawg" className="gap-1.5">
              <span>AmneziaWG</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold">{tabCounts.amneziawg}</span>
            </TabsTrigger>
            <TabsTrigger value="wireguard" className="gap-1.5">
              <span>WireGuard</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-bold">{tabCounts.wireguard}</span>
            </TabsTrigger>
          </TabsList>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative min-w-[220px] flex-1">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по имени клиента..."
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
            {isAdmin && (
              <div className="flex flex-wrap gap-1">
                {(
                  [
                    ['all', 'Все'],
                    ['active', '✓ Активные'],
                    ['expiring', '⚠ Истекают'],
                    ['expired', '✗ Истекшие'],
                  ] as const
                ).map(([key, label]) => (
                  <Button
                    key={key}
                    type="button"
                    size="sm"
                    variant={filter === key ? 'default' : 'secondary'}
                    onClick={() => setFilter(key)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
            )}
          </div>
        </div>

        {TAB_ORDER.map((tab) => (
          <TabsContent key={tab} value={tab} className="mt-0">
            {filteredByTab[tab].length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">Нет клиентов в этой категории</p>
            ) : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-2">
                {filteredByTab[tab].map((config) => (
                  <ConfigCard
                    key={`${tab}-${config.id}`}
                    config={config}
                    tab={tab}
                    policy={getPolicyForConfig(config, policies)}
                    onOpen={() => {
                      setSelectedTab(tab)
                      setSelectedConfig(config)
                    }}
                    onCopyName={() => void copyName(config.client_name)}
                  />
                ))}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>

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
    </>
  )
}
