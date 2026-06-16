import { Pause, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PercentBar } from '@/components/ui/percent-bar'
import { cn } from '@/lib/utils'

interface AutoRefreshControlProps {
  enabled: boolean
  onToggle: () => void
  countdown: number
  intervalSec: number
  refreshing: boolean
  onManualRefresh: () => void
}

export default function AutoRefreshControl({
  enabled,
  onToggle,
  countdown,
  intervalSec,
  refreshing,
  onManualRefresh,
}: AutoRefreshControlProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant={enabled ? 'secondary' : 'outline'}
        size="sm"
        onClick={onToggle}
        title={enabled ? 'Приостановить автообновление' : 'Включить автообновление'}
      >
        {enabled ? <Pause size={14} /> : <Play size={14} />}
        {enabled ? 'Авто' : 'Пауза'}
      </Button>
      {enabled && (
        <span className="mono relative flex h-9 min-w-[4rem] items-center justify-center overflow-hidden rounded-md border bg-muted px-3 text-xs">
          <PercentBar
            value={countdown}
            max={intervalSec}
            className="absolute inset-0 h-full rounded-none bg-transparent"
            barClassName="fill-primary/20 transition-all"
          />
          <span className="relative">{countdown}с</span>
        </span>
      )}
      <Button type="button" variant="secondary" size="sm" onClick={onManualRefresh} disabled={refreshing}>
        <RefreshCw size={14} className={cn(refreshing && 'animate-spin')} />
        {refreshing ? '...' : 'Обновить'}
      </Button>
    </div>
  )
}
