import type { ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type SidebarNavGroupProps = {
  /** Стабильный id группы: из него строится id панели для aria-controls. */
  id: string
  label: string
  open: boolean
  onToggle: () => void
  children: ReactNode
  badge?: number
}

/**
 * Родитель-аккордеон в сайдбаре: раскрытие только по клику (не по hover),
 * дети рендерятся лишь при `open`. Клик по родителю мобильный drawer не закрывает.
 */
export function SidebarNavGroup({ id, label, open, onToggle, children, badge }: SidebarNavGroupProps) {
  const panelId = `sidebar-group-panel-${id}`

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className={cn(
          'orientation-compact-sidebar-group-label flex w-full items-center gap-1 rounded-md px-3 pb-1 pt-3 text-left',
          'text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80 transition-colors',
          'first:pt-1 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        )}
      >
        {open ? (
          <ChevronDown size={12} className="shrink-0" aria-hidden />
        ) : (
          <ChevronRight size={12} className="shrink-0" aria-hidden />
        )}
        <span className="min-w-0 truncate">{label}</span>
        {badge != null && badge > 0 ? (
          <Badge variant="destructive" className="ml-auto text-[10px]">
            {badge > 9 ? '9+' : badge}
          </Badge>
        ) : null}
      </button>
      {open ? (
        <ul id={panelId} className="space-y-0.5">
          {children}
        </ul>
      ) : null}
    </div>
  )
}
