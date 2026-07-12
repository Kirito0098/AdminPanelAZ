import { Link } from 'react-router-dom'
import { AlertTriangle, ChevronRight, Info } from 'lucide-react'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Badge } from '@/components/ui/badge'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { NocIncidentItem } from '@/types'

type NocIncidentFeedProps = {
  items: NocIncidentItem[]
}

function severityVariant(severity: NocIncidentItem['severity']): 'danger' | 'warning' | 'info' {
  if (severity === 'danger') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

export default function NocIncidentFeed({ items }: NocIncidentFeedProps) {
  if (!items.length) return null

  return (
    <SettingsAlert
      variant={items.some((i) => i.severity === 'danger') ? 'danger' : 'warning'}
      title={`Инциденты (${items.length})`}
    >
      <ul className="divide-y divide-border/60">
        {items.map((item) => (
          <li key={item.id} className="py-2 first:pt-0 last:pb-0">
            <div className="flex items-start gap-2">
              {item.severity === 'danger' ? (
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-destructive" />
              ) : (
                <Info size={14} className="mt-0.5 shrink-0 text-amber-600" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={item.severity === 'danger' ? 'destructive' : 'secondary'} className="text-[10px]">
                    {item.kind}
                  </Badge>
                  {item.href ? (
                    <Link
                      to={item.href}
                      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                    >
                      {item.title}
                      <ChevronRight size={12} />
                    </Link>
                  ) : (
                    <span className="text-sm font-medium">{item.title}</span>
                  )}
                </div>
                {item.detail && (
                  <p className={cn('mt-0.5 text-xs text-muted-foreground')}>{item.detail}</p>
                )}
                <p className="mt-0.5 text-[11px] text-muted-foreground">{formatDateTime(item.at)}</p>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </SettingsAlert>
  )
}

export { severityVariant }
