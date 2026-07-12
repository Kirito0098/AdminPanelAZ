import { RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { MonitoringService } from '@/types'

interface ServiceMatrixProps {
  services: MonitoringService[]
  allowRestart?: boolean
  onRestart?: (serviceName: string) => void
  restartingName?: string | null
}

export default function ServiceMatrix({
  services,
  allowRestart = false,
  onRestart,
  restartingName = null,
}: ServiceMatrixProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {services.map((s) => (
        <div
          key={s.name}
          className={cn(
            'flex items-center gap-3 rounded-lg border p-3',
            s.active ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-destructive/20 bg-destructive/5',
          )}
        >
          <div className={cn('rounded-md p-2', s.active ? 'text-emerald-500' : 'text-muted-foreground')}>
            {s.active ? <Wifi size={14} /> : <WifiOff size={14} />}
          </div>
          <div className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">{s.name}</span>
            <Badge variant={s.active ? 'success' : 'destructive'} className="mt-1">
              {s.status}
            </Badge>
          </div>
          {allowRestart && onRestart && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0 gap-1"
              disabled={restartingName === s.name}
              onClick={() => onRestart(s.name)}
              title={s.active ? 'Перезапустить службу' : 'Перезапустить неактивную службу'}
            >
              <RefreshCw size={12} className={cn(restartingName === s.name && 'animate-spin')} />
            </Button>
          )}
        </div>
      ))}
    </div>
  )
}
