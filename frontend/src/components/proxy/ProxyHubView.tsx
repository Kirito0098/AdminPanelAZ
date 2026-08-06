import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  ExternalLink,
  Network,
  Puzzle,
  RefreshCw,
  Server,
  Settings2,
} from 'lucide-react'
import { ApiError, getNodes } from '@/api/client'
import HaReplicaBanner from '@/components/dashboard/HaReplicaBanner'
import { NodeStatusBadge } from '@/components/NodeSelector'
import ProxyNodePanel, { AZ_PROXY_SH_DOCS_URL } from '@/components/nodes/ProxyNodePanel'
import RemoteHostsCard from '@/components/proxy/RemoteHostsCard'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import EmptyState from '@/components/ui/EmptyState'
import Spinner from '@/components/ui/Spinner'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import type { Node } from '@/types'

const PROXY_NODES_DOCS_URL =
  'https://github.com/Kirito0098/AdminPanelAZ/blob/main/docs/proxy-nodes.md'

const ANTIZAPRET_REMOTES_HASH = encodeURIComponent('section-Адреса подключения')

function isProxyNode(node: Node): boolean {
  return (node.node_kind || 'vpn') === 'proxy'
}

const QUICK_LINKS = [
  {
    to: '/nodes',
    label: 'Узлы',
    description: 'Добавить или изменить прокси-узел',
    icon: Server,
  },
  {
    to: `/antizapret#${ANTIZAPRET_REMOTES_HASH}`,
    label: 'Конфиг AntiZapret',
    description: 'Адреса подключения и параметры setup',
    icon: Settings2,
  },
  {
    to: '/monitoring',
    label: 'NOC → Подключения',
    description: 'Домашний IP и пометка «через прокси»',
    icon: Activity,
  },
  {
    to: '/settings/modules',
    label: 'Настройки → Модули',
    description: 'Включить или выключить Прокси-узлы',
    icon: Puzzle,
  },
] as const

export default function ProxyHubView() {
  const { activeNode, refreshNodes } = useNode()
  const { error: notifyError } = useNotifications()
  const [proxyNodes, setProxyNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const nodes = await getNodes()
      setProxyNodes(nodes.filter(isProxyNode))
      await refreshNodes()
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Не удалось загрузить прокси-узлы'
      setLoadError(message)
      notifyError(message)
      setProxyNodes([])
    } finally {
      setLoading(false)
    }
  }, [notifyError, refreshNodes])

  useEffect(() => {
    void load()
  }, [load])

  const activeNodeLabel = useMemo(() => {
    if (!activeNode) return null
    return activeNode.name
  }, [activeNode])

  return (
    <div className="space-y-6">
      <HaReplicaBanner />

      <PageSectionHeader
        icon={Network}
        title="Прокси"
        description={
          <>
            Сводка по прокси-узлам и адресам OpenVPN активного VPN. Панель не ставит и не запускает{' '}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">proxy.sh</code>.
          </>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => void load()} disabled={loading}>
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Обновить
            </Button>
            <Button type="button" variant="outline" size="sm" asChild>
              <a href={AZ_PROXY_SH_DOCS_URL} target="_blank" rel="noopener noreferrer">
                AntiZapret proxy.sh
                <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
              </a>
            </Button>
            <Button type="button" variant="outline" size="sm" asChild>
              <a href={PROXY_NODES_DOCS_URL} target="_blank" rel="noopener noreferrer">
                docs/proxy-nodes.md
                <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
              </a>
            </Button>
          </div>
        }
      />

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold tracking-tight">Прокси-узлы</h3>
          {!loading && (
            <Badge variant="secondary">{proxyNodes.length}</Badge>
          )}
        </div>

        {loading ? (
          <Spinner label="Загрузка прокси-узлов..." className="py-8" />
        ) : loadError ? (
          <div className="space-y-3">
            <SettingsAlert variant="danger" title="Ошибка загрузки">
              {loadError}
            </SettingsAlert>
            <Button type="button" variant="secondary" size="sm" onClick={() => void load()}>
              <RefreshCw className="mr-1.5 h-4 w-4" />
              Повторить
            </Button>
          </div>
        ) : proxyNodes.length === 0 ? (
          <EmptyState
            icon={Network}
            title="Нет прокси-узлов"
            description="Добавьте узел типа «Прокси» на странице Узлы (модуль Прокси-узлы должен быть включён)."
            action={
              <Button asChild>
                <Link to="/nodes">Добавить на Узлах</Link>
              </Button>
            }
          />
        ) : (
          <div className="space-y-4">
            {proxyNodes.map((node) => (
              <Card key={node.id}>
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-base">{node.name}</CardTitle>
                        <Badge variant="outline" className="text-[10px]">
                          Прокси
                        </Badge>
                        <NodeStatusBadge status={node.status} />
                      </div>
                      <CardDescription className="font-mono text-xs">
                        {node.host}:{node.port}
                      </CardDescription>
                    </div>
                    <Button type="button" variant="ghost" size="sm" asChild>
                      <Link to="/nodes">Открыть на Узлах</Link>
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <ProxyNodePanel node={node} onUpdated={load} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold tracking-tight">Адреса подключения (активный VPN)</h3>
          <p className="text-xs text-muted-foreground">
            Список remote OpenVPN для{' '}
            {activeNodeLabel ? (
              <span className="font-medium text-foreground">{activeNodeLabel}</span>
            ) : (
              'активного узла'
            )}
            . Полный блок setup — в{' '}
            <Link
              to={`/antizapret#${ANTIZAPRET_REMOTES_HASH}`}
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Конфиг AntiZapret
            </Link>
            .
          </p>
        </div>
        <RemoteHostsCard nodeId={activeNode?.id ?? null} variant="card" />
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold tracking-tight">Быстрые ссылки</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {QUICK_LINKS.map((item) => {
            const Icon = item.icon
            return (
              <Link
                key={item.to}
                to={item.to}
                className="group flex items-start gap-3 rounded-xl border bg-card p-4 transition-colors hover:bg-muted/40"
              >
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium group-hover:text-foreground">{item.label}</p>
                  <p className="text-xs text-muted-foreground">{item.description}</p>
                </div>
              </Link>
            )
          })}
        </div>
      </section>
    </div>
  )
}
