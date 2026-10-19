import { useCallback, useMemo } from 'react'
import { NavLink } from 'react-router-dom'
import { Bell, Clock, Shield, Server, Network, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFeatureModules } from '@/context/FeatureModulesContext'

export type NotificationCategory = 'requests' | 'security' | 'nodes' | 'services' | 'tasks'

type TabKey = 'all' | 'requests' | 'security' | 'nodes' | 'services' | 'tasks'

export interface NotificationItem {
  id: number
  category: NotificationCategory
  level: string
  event_type: string
  title: string
  message: string
  created_at: string
}

export interface NotificationPopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sheet?: boolean
  items: NotificationItem[]
  unreadCount: number
  pendingRequestsCount: number
  category: TabKey
  onCategoryChange: (key: TabKey) => void
  onMarkAllRead: () => void
}

const CATEGORY_ICON: Record<TabKey, React.ElementType> = {
  all: Bell,
  requests: Clock,
  security: Shield,
  nodes: Server,
  services: Network,
  tasks: Mail,
}

const CATEGORY_LABEL: Record<TabKey, string> = {
  all: 'Все',
  requests: 'Заявки',
  security: 'Безопасность',
  nodes: 'Серверы',
  services: 'Сервисы и сеть',
  tasks: 'Задачи',
}

const LEVEL_VARIANT: Record<string, BadgeVariant> = {
  info: 'secondary',
  warning: 'warning',
  error: 'destructive',
}

type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'outline'
  | 'success'
  | 'warning'

function formatCreatedAt(value: string): string {
  try {
    return new Date(value).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function renderItem(item: NotificationItem, onItemClick?: (item: NotificationItem) => void) {
  const Icon = CATEGORY_ICON[item.category as TabKey] ?? Bell
  return (
    <div
      key={item.id}
      className="border-b border-border/60 last:border-0 py-2"
      onClick={() => onItemClick?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault()
          onItemClick?.(item)
        }
      }}
    >
      <div className="flex items-start gap-2">
        <Icon size={14} className="shrink-0 mt-0.5 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold">{item.title}</span>
            <Badge variant={LEVEL_VARIANT[item.level] ?? 'secondary'} className="text-[10px]">
              {item.level}
            </Badge>
          </div>
          {item.message && (
            <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{item.message}</p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {item.event_type} · {formatCreatedAt(item.created_at)}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function NotificationPopover({
  open,
  onOpenChange,
  sheet = false,
  items,
  unreadCount,
  pendingRequestsCount,
  category,
  onCategoryChange,
  onMarkAllRead,
}: NotificationPopoverProps) {
  const { isEnabled } = useFeatureModules()
  const requestsTabEnabled = isEnabled('user_provisioning')

  const tabs = useMemo<TabKey[]>(() => {
    const list: TabKey[] = ['all']
    if (requestsTabEnabled) list.push('requests')
    list.push('security', 'nodes', 'services', 'tasks')
    return list
  }, [requestsTabEnabled])

  const activeTab = category === 'requests' && !requestsTabEnabled ? 'all' : category
  const visibleItems = items.filter((item) => activeTab === 'all' || item.category === activeTab)

  const markAll = useCallback(() => {
    onMarkAllRead()
  }, [onMarkAllRead])

  const body = (
    <div className="flex flex-col gap-0">
      <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs border-b border-border/60 bg-muted/50">
        <span className="font-semibold">Центр уведомлений</span>
        <Button variant="outline" size="sm" onClick={markAll} disabled={!items.length}>
          Отметить всё как прочитанное
        </Button>
      </div>
      <Tabs value={activeTab} onValueChange={(value) => onCategoryChange(value as TabKey)} className="w-full">
        <TabsList className="w-auto gap-1 bg-muted/40 p-1">
          {tabs.map((key) => {
            const TabIcon = CATEGORY_ICON[key]
            return (
              <TabsTrigger key={key} value={key} className="text-xs font-medium">
                <TabIcon size={13} className="mr-1.5 shrink-0" />
                {CATEGORY_LABEL[key]}
              </TabsTrigger>
            )
          })}
        </TabsList>
        {tabs.map((key) => (
          <TabsContent key={key} value={key} className="p-3 overflow-y-auto max-h-[44vh]">
            {visibleItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-sm text-muted-foreground">
                Нет уведомлений
              </div>
            ) : (
              <div className="space-y-0">{visibleItems.map((item) => renderItem(item))}</div>
            )}
          </TabsContent>
        ))}
      </Tabs>
      <div className="border-t border-border/60 pt-2 pb-3 px-3">
        <NavLink
          to="/logs"
          className="text-xs text-primary underline-offset-4 hover:underline"
          onClick={() => onOpenChange(false)}
        >
          Журнал аудита
        </NavLink>
      </div>
    </div>
  )

  if (sheet) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-96 p-0">
          <SheetHeader className="px-4 pb-2">
            <SheetTitle>Центр уведомлений</SheetTitle>
            <SheetDescription className="text-xs">
              Непрочитано: <span className="font-semibold">{unreadCount}</span>{' '}
              {pendingRequestsCount > 0 ? `· заявок: ${pendingRequestsCount}` : ''}
            </SheetDescription>
          </SheetHeader>
          {body}
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <div
      className="fixed right-0 top-14 z-50 w-96 rounded-xl border border-border/80 bg-background shadow-lg"
      hidden={!open}
    >
      {body}
    </div>
  )
}
