import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, BellOff, Check, EyeOff, Search, Settings2 } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/EmptyState'
import NotificationCard from '@/components/notifications/NotificationCard'
import { CATEGORY_ICON, CATEGORY_LABEL } from '@/components/notifications/labels'
import { dayKey, dayLabel, snoozeUntil, type SnoozePreset } from '@/components/notifications/time'
import { useNotificationCenter, type NotificationTabKey } from '@/context/NotificationCenterContext'
import { cn } from '@/lib/utils'
import {
  fetchNotificationPreferences,
  type NotificationCategory,
  type NotificationItem,
} from '@/api/notifications'

const CATEGORY_TABS: NotificationTabKey[] = ['all', 'requests', 'security', 'nodes', 'services', 'tasks']

export default function NotificationsFeed() {
  const { items, counts, query, setQuery, loading, hasMore, loadMore, markAllRead, setState } =
    useNotificationCenter()
  const [search, setSearch] = useState(query.q)
  const [enabled, setEnabled] = useState<Record<NotificationCategory, boolean>>({
    requests: true,
    security: true,
    nodes: true,
    services: true,
    tasks: true,
  })

  useEffect(() => {
    let cancelled = false
    fetchNotificationPreferences()
      .then((prefs) => {
        if (!cancelled) setEnabled((prev) => ({ ...prev, ...prefs.categories }))
      })
      .catch(() => {
        /* настройки не загрузились — показываем все категории */
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (query.category !== 'all' && !enabled[query.category]) setQuery({ category: 'all' })
  }, [enabled, query.category, setQuery])

  const visibleTabs = CATEGORY_TABS.filter((key) => key === 'all' || enabled[key])

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

  const handleSnooze = (id: number, preset: SnoozePreset) =>
    void setState(id, { snoozed_until: snoozeUntil(preset) })

  const hasFilters =
    query.q !== '' || query.unreadOnly || query.hiddenOnly || query.level !== 'all' || query.category !== 'all'

  const statFor = (key: NotificationTabKey) =>
    key === 'all'
      ? {
          total: Object.values(counts.by_category).reduce((sum, item) => sum + item.total, 0),
          unread: counts.unread,
        }
      : counts.by_category[key]

  return (
    <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex min-w-0 flex-col gap-3">
        <div className="sticky top-0 z-10 flex flex-col gap-2 rounded-xl border border-border/60 bg-background/95 p-2 backdrop-blur">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-1 basis-52">
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
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="sm"
                variant={query.unreadOnly ? 'default' : 'outline'}
                onClick={() => setQuery({ unreadOnly: !query.unreadOnly, hiddenOnly: false })}
              >
                Непрочитанные
                {counts.unread > 0 && <span className="ml-1 opacity-70">{counts.unread}</span>}
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
              {counts.attention > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-1 text-[11px] font-medium text-destructive xl:hidden">
                  <AlertTriangle size={11} /> {counts.attention} требует внимания
                </span>
              )}
              <Button
                size="sm"
                variant="outline"
                className="ml-auto gap-1.5"
                onClick={() => void markAllRead()}
                disabled={!items.length}
              >
                <Check size={14} />
                Отметить всё
              </Button>
            </div>
          </div>

          {/* Узкий экран: категории живут здесь, на широком — в правой колонке. */}
          <div className="flex flex-wrap gap-1.5 xl:hidden">
            {visibleTabs.map((key) => {
              const Icon = CATEGORY_ICON[key]
              const stat = statFor(key)
              const active = query.category === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setQuery({ category: key })}
                  aria-pressed={active}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors',
                    active
                      ? 'border-primary/60 bg-primary/15 text-foreground'
                      : 'border-border/70 text-muted-foreground hover:bg-muted/50',
                  )}
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
            <NavLink
              to="/settings/notifications"
              className="ml-auto inline-flex items-center gap-1 self-center text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              <Settings2 size={12} />
              Настройки
            </NavLink>
          </div>
        </div>

        {loading && items.length === 0 ? (
          <div className="flex flex-col gap-2">
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-20 w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/70">
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
          </div>
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

      <aside className="hidden flex-col gap-3 self-start xl:sticky xl:top-0 xl:flex">
        <section className="rounded-xl border border-border/60 bg-card/60 p-2">
          <h2 className="px-1.5 pb-1 pt-0.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
            Категории
          </h2>
          <div className="flex flex-col gap-0.5">
            {visibleTabs.map((key) => {
              const Icon = CATEGORY_ICON[key]
              const stat = statFor(key)
              const active = query.category === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setQuery({ category: key })}
                  aria-pressed={active}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors',
                    active
                      ? 'bg-primary/10 font-medium text-foreground'
                      : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground',
                  )}
                >
                  <Icon size={14} className="shrink-0" />
                  <span className="min-w-0 flex-1 truncate text-left">{CATEGORY_LABEL[key]}</span>
                  {stat && stat.total > 0 && (
                    <span className="text-[11px] tabular-nums text-muted-foreground/70">{stat.total}</span>
                  )}
                  {stat && stat.unread > 0 && (
                    <span className="rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                      {stat.unread}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </section>

        <section className="rounded-xl border border-border/60 bg-card/60 p-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">Сводка</h2>
          <dl className="mt-2 flex flex-col gap-1 text-sm">
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Новых</dt>
              <dd className="font-semibold">{counts.unread}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Требует внимания</dt>
              <dd className={cn('font-semibold', counts.attention > 0 && 'text-destructive')}>{counts.attention}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Отложено</dt>
              <dd className="font-semibold">{counts.snoozed}</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-muted-foreground">Скрыто</dt>
              <dd className="font-semibold">{counts.hidden}</dd>
            </div>
          </dl>
        </section>

        <NavLink
          to="/settings/notifications"
          className="flex items-center gap-2 rounded-xl border border-border/60 bg-card/60 px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
        >
          <Settings2 size={14} />
          Настройки уведомлений
        </NavLink>
      </aside>
    </div>
  )
}
