import type { LucideIcon } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

type MonitoringChartCardProps = {
  title: string
  description: string
  icon: LucideIcon
  children: React.ReactNode
  className?: string
}

export default function MonitoringChartCard({
  title,
  description,
  icon: Icon,
  children,
  className,
}: MonitoringChartCardProps) {
  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon size={16} className="shrink-0 text-muted-foreground" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="monitoring-chart-panel">{children}</CardContent>
    </Card>
  )
}

export function MonitoringChartEmpty({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={cn(
        'monitoring-chart-panel flex items-center justify-center text-center text-sm text-muted-foreground',
      )}
    >
      {children}
    </div>
  )
}
