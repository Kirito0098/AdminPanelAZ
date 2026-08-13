import { RefreshCw, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { NodeBadge } from '@/components/NodeSelector'
import { useNode } from '@/context/NodeContext'
import type { Awg2HealthResponse } from '@/types'
import { cn } from '@/lib/utils'
import Awg2InstallDialog from './Awg2InstallDialog'
import { awg2StatusMeta } from './utils'

interface Awg2HeroProps {
  health: Awg2HealthResponse | null
  loading: boolean
  nodeLabel: string
  onRefresh: () => void
  onUpdated: () => void
}

export default function Awg2Hero({ health, loading, nodeLabel, onRefresh, onUpdated }: Awg2HeroProps) {
  const { activeNode } = useNode()
  const status = awg2StatusMeta(health)

  return (
    <PageSectionHeader
      icon={Shield}
      title="AZ-AWG2"
      titleAddon={
        <>
          <NodeBadge name={activeNode?.name} status={activeNode?.status} />
          {loading ? (
            <Skeleton className="h-5 w-24 rounded-full" />
          ) : (
            <Badge variant={status.variant} className="gap-1.5">
              <span className={cn('h-2 w-2 rounded-full', status.dot)} />
              {status.label}
            </Badge>
          )}
        </>
      }
      description={
        <>
          AmneziaWG 2.0 на узле <strong className="font-medium text-foreground">{nodeLabel}</strong>
          {activeNode?.is_local ? ' (локальный controller)' : activeNode ? ' (удалённый node agent)' : ''}.
          Клиенты — на странице Конфигурации; здесь обфускация и backup слоя.
        </>
      }
      actions={
        <>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
          {health?.installed && (
            <Awg2InstallDialog
              mode="update"
              triggerLabel="Обновить слой"
              triggerVariant="outline"
              onCompleted={onUpdated}
            />
          )}
        </>
      }
    />
  )
}
