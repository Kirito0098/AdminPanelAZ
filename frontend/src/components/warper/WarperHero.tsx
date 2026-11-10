import { Cloud, Power, RefreshCw, Server } from 'lucide-react'
import { postWarperToggle } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import PageSectionHeader from '@/components/shared/PageSectionHeader'
import { useNotifications } from '@/context/NotificationContext'
import { DOCS } from '@/lib/docsUrls'
import type { WarperHealthResponse } from '@/types'
import { cn } from '@/lib/utils'
import { warperToggleLabel } from './utils'

interface WarperHeroProps {
  health: WarperHealthResponse | null
  loading: boolean
  nodeLabel: string
  onRefresh: () => void
  onToggled: () => void
}

function statusMeta(health: WarperHealthResponse | null) {
  if (!health) {
    return { label: 'Нет данных', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
  if (health.conflict_antizapret_warp) {
    return { label: 'Конфликт WARP', variant: 'destructive' as const, dot: 'bg-destructive' }
  }
  if (!health.installed) {
    return { label: 'Не установлен', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  if (health.active) {
    return { label: 'Активен', variant: 'success' as const, dot: 'bg-emerald-500' }
  }
  if (health.dns_patch_orphaned) {
    return { label: 'Выключен не полностью', variant: 'warning' as const, dot: 'bg-amber-500' }
  }
  return { label: 'Выключен', variant: 'secondary' as const, dot: 'bg-muted-foreground' }
}

export default function WarperHero({ health, loading, nodeLabel, onRefresh, onToggled }: WarperHeroProps) {
  const { success, error: notifyError } = useNotifications()
  const status = statusMeta(health)
  const canToggle = Boolean(health?.installed && !health.conflict_antizapret_warp)

  async function handleToggle() {
    try {
      const result = await postWarperToggle()
      success(result.message ?? 'AZ-WARP переключён')
      onToggled()
    } catch (err) {
      notifyError(err instanceof Error ? err.message : 'Не удалось переключить AZ-WARP')
    }
  }

  return (
    <PageSectionHeader
      card
      icon={Cloud}
      title="AZ-WARP"
      titleAddon={
        loading ? (
          <Skeleton className="h-6 w-24 rounded-full" />
        ) : (
          <Badge variant={status.variant} className="gap-1.5">
            <span className={cn('h-2 w-2 rounded-full', status.dot, health?.active && 'animate-pulse')} />
            {status.label}
          </Badge>
        )
      }
      description={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Server className="h-3.5 w-3.5 shrink-0" />
          <span>{nodeLabel}</span>
          {health?.version && (
            <>
              <span className="text-muted-foreground/50">·</span>
              <span className="font-mono text-xs">v{health.version}</span>
            </>
          )}
        </span>
      }
      docsHref={DOCS.warper}
      actions={
        <>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw className={cn('mr-1.5 h-4 w-4', loading && 'animate-spin')} />
            Обновить
          </Button>
          <Button
            size="sm"
            variant={health?.active ? 'secondary' : 'default'}
            disabled={loading || !canToggle}
            onClick={() => void handleToggle()}
          >
            <Power className="mr-1.5 h-4 w-4" />
            {warperToggleLabel(health)}
          </Button>
        </>
      }
    />
  )
}
