import { Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface MiniPageHeaderProps {
  title: string
  subtitle?: string
  onRefresh?: () => void
  refreshing?: boolean
}

export default function MiniPageHeader({ title, subtitle, onRefresh, refreshing = false }: MiniPageHeaderProps) {
  return (
    <div className="tg-mini-dashboard-toolbar">
      <div className="min-w-0">
        <h2 className="tg-mini-page-title">{title}</h2>
        {subtitle && <p className="tg-mini-muted text-xs">{subtitle}</p>}
      </div>
      {onRefresh && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          disabled={refreshing}
          onClick={onRefresh}
        >
          {refreshing ? (
            <Loader2 size={16} className="animate-spin" aria-hidden />
          ) : (
            <RefreshCw size={16} aria-hidden />
          )}
          <span className="sr-only">Обновить</span>
        </Button>
      )}
    </div>
  )
}
