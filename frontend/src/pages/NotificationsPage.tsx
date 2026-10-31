import { useEffect, useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { AlertTriangle, BellOff, EyeOff, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/EmptyState'
import NotificationCard from '@/components/notifications/NotificationCard'
import { CATEGORY_ICON, CATEGORY_LABEL } from '@/components/notifications/labels'
import { dayKey, dayLabel, snoozeUntil, type SnoozePreset } from '@/components/notifications/time'
import { useAuth } from '@/context/AuthContext'
import { useNotificationCenter, type NotificationTabKey } from '@/context/NotificationCenterContext'
import type { NotificationItem } from '@/api/notifications'

const CATEGORY_TABS: NotificationTabKey[] = ['all', 'requests', 'security', 'nodes', 'services', 'tasks']

export default function NotificationsPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { items, counts, query, setQuery, loading, hasMore, loadMore, markAllRead, setState } =
    useNotificationCenter()
  const [search, setSearch] = useState(query.q)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search !== query.q) setQuery({ q: search })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [search, query.q, setQuery])

  const groups = useMemo(() => {
    const map = new Map<string, { key: string; label: string; items: NotificationItem[] }>()
    for (const item of items) {
      const key = dayKey(item.created_at)
      const bucket = map.get(key) ?? { key, label: dayLabel(item.created_at), items: [] }
      bucket.items.push(item)
      map.set(key, bucket)
    }
    return [...map.values()]
  }, [items])

  if (!isAdmin) return <Navigate to="/" replace />

  const handleSnooze = (id: number, preset: SnoozePreset) =>
    void setState(id, { snoozed_until: snoozeUntil(preset) })

  const hasFilters =
    query.q !== '' || query.unreadOnly || query.hiddenOnly || query.level !== 'all' || query.category !== 'all'

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-semibold">Уведомления</h1>
        {counts.unread > 0 && (
          <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
            {counts.unread} новых
          </span>
        )}
        {counts.attention > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 text-xs font-medium text-destructive">
            <AlertTriangle size={12} /> {counts.attention} требует внимания
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          onClick={() => void markAllRead()}
          disabled={!items.length}
        >
          Отметить всё прочитанным
        </Button>
      </div>

      <div className="sticky top-0 z-10 flex flex-col gap-2 rounded-xl border border-border/60 bg-background/95 px-2 py-2 backdrop-blur">
        <div className="flex flex-wrap gap-1.5">
          {CATEGORY_TABS.map((key) => {
            const Icon = CATEGORY_ICON[key]
            const stat =
              key === 'all'
                ? {
                    total: Object.values(counts.by_category).reduce((sum, item) => sum + item.total, 0),
                    unread: counts.unread,
                  }
                : counts.by_category[key]
            const active = query.category === key
            return (
              <button
                key={key}
                type="button"
                onClick={() => setQuery({ category: key })}
                aria-pressed={active}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  active
                    ? 'border-primary/60 bg-primary/15 text-foreground'
                    : 'border-border/70 text-muted-foreground hover:bg-muted/50'
                }`}
              >
                <Icon size={12} />
                {CATEGORY_LABEL[key]}
                {stat && stat.total > 0 && <span className="opacity-60">{stat.total}</span>}
                {stat && stat.unread > 0 && (
                  <span className="rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                    {stat.unread}
                  </span>
                )}
              </button>
            )
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={query.unreadOnly ? 'default' : 'outline'}
            onClick={() => setQuery({ unreadOnly: !query.unreadOnly, hiddenOnly: false })}
          >
            Непрочитанные
          </Button>
          <Button
            size="sm"
            variant={query.level === 'error' ? 'default' : 'outline'}
            onClick={() => setQuery({ level: query.level === 'error' ? 'all' : 'error', hiddenOnly: false })}
          >
            Важные
          </Button>
          <Button
            size="sm"
            variant={query.hiddenOnly ? 'default' : 'outline'}
            onClick={() => setQuery({ hiddenOnly: !query.hiddenOnly, unreadOnly: false })}
          >
            Скрытые
          </Button>
          <div className="relative ml-auto w-full sm:w-64">
            <Search
              size={14}
              className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по заголовку и тексту"
              className="h-8 pl-7 text-sm"
              aria-label="Поиск уведомлений"
            />
          </div>
        </div>
      </div>


      {loading && items.length === 0 ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((key) => (
            <Skeleton key={key} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={query.hiddenOnly ? EyeOff : query.unreadOnly ? BellOff : Search}
          title={
            query.hiddenOnly
              ? 'Скрытых уведомлений нет'
              : query.unreadOnly
                ? 'Непрочитанных нет — всё разобрано'
                : 'Ничего не найдено'
          }
          description={query.q ? `По запросу «${query.q}» ничего нет.` : undefined}
          action={
            hasFilters ? (
              <Button
                variant="outline"
                onClick={() => {
                  setSearch('')
                  setQuery({ category: 'all', level: 'all', unreadOnly: false, hiddenOnly: false, q: '' })
                }}
              >
                Сбросить фильтры
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <section key={group.key} className="flex flex-col gap-2">
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
                {group.label}
              </h2>
              {group.items.map((item) => (
                <NotificationCard
                  key={item.id}
                  item={item}
                  onMarkRead={(id) => void setState(id, { read: true })}
                  onSnooze={handleSnooze}
                  onHide={(id) => void setState(id, { hidden: true })}
                  onRestore={(id) => void setState(id, { hidden: false })}
                />
              ))}
            </section>
          ))}
          {hasMore && (
            <Button
              variant="outline"
              className="self-center"
              onClick={() => void loadMore()}
              disabled={loading}
            >
              Показать ещё
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

