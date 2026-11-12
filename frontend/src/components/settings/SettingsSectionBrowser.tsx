import { useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { ChevronRight, Puzzle, Router, Search, Server, Settings, Shield, User, X } from 'lucide-react'
import {
  filterNavGroupsByQuery,
  type SettingsNavGroup,
  type SettingsSection,
} from '@/components/settings/SettingsNav'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

type SettingsSectionBrowserProps = {
  groups: SettingsNavGroup[]
  variant: 'hub' | 'nav'
  activeSection?: SettingsSection
  className?: string
}

const GROUP_ICONS: Record<string, LucideIcon> = {
  Личное: User,
  Доступ: Shield,
  VPN: Router,
  Сервер: Server,
  Панель: Puzzle,
}

export default function SettingsSectionBrowser({
  groups,
  variant,
  activeSection,
  className,
}: SettingsSectionBrowserProps) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => filterNavGroupsByQuery(groups, query), [groups, query])
  const isHub = variant === 'hub'

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div className="relative">
        <Search
          size={16}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Найти раздел…"
          className={cn('h-9 rounded-lg pl-8', query && 'pr-8')}
          aria-label="Поиск раздела настроек"
        />
        {query ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2"
            onClick={() => setQuery('')}
            aria-label="Сбросить поиск"
          >
            <X size={14} />
          </Button>
        ) : null}
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/80 px-3 py-6 text-center">
          <p className="text-sm text-muted-foreground">Ничего не найдено</p>
          <Button type="button" variant="link" className="mt-1 h-auto p-0" onClick={() => setQuery('')}>
            Сбросить поиск
          </Button>
        </div>
      ) : (
        <div className={cn(isHub ? 'flex flex-col gap-5' : 'flex flex-col gap-3')}>
          {filtered.map((group) => {
            const GroupIcon = GROUP_ICONS[group.label] ?? Settings
            return (
              <div key={group.label}>
                {isHub ? (
                  <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 border-b border-border/60 pb-1.5">
                    <GroupIcon
                      size={13}
                      className="shrink-0 text-muted-foreground/70"
                      aria-hidden
                    />
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      {group.label}
                    </p>
                    {group.description ? (
                      <p className="text-[11px] text-muted-foreground/70">{group.description}</p>
                    ) : null}
                    <span className="ml-auto rounded-full border border-border/60 px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground/70">
                      {group.items.length}
                    </span>
                  </div>
                ) : filtered.length > 1 ? (
                  <p className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
                    {group.label}
                  </p>
                ) : null}
                <ul
                  className={cn(
                    isHub ? 'grid gap-2 sm:grid-cols-2 xl:grid-cols-3' : 'space-y-0.5',
                  )}
                >
                  {group.items.map((item) => {
                    const Icon = item.icon
                    const active = activeSection === item.id
                    return (
                      <li key={item.id}>
                        <NavLink
                          to={`/settings/${item.id}`}
                          end
                          className={cn(
                            'group/item',
                            isHub
                              ? 'flex min-h-[56px] items-center gap-2.5 rounded-xl border border-border/70 bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/30 hover:bg-muted/40'
                              : 'flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors',
                            !isHub &&
                              (active
                                ? 'bg-primary/10 font-medium text-foreground ring-1 ring-primary/20'
                                : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'),
                          )}
                        >
                          <span
                            className={cn(
                              'flex shrink-0 items-center justify-center rounded-lg',
                              isHub
                                ? 'h-8 w-8 bg-primary/10 text-primary ring-1 ring-primary/15'
                                : 'h-7 w-7',
                              !isHub &&
                                (active
                                  ? 'bg-primary/10 text-primary'
                                  : 'text-muted-foreground/80 group-hover/item:text-foreground'),
                            )}
                          >
                            <Icon size={isHub ? 16 : 15} strokeWidth={2} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span
                              className={cn(
                                'block truncate',
                                isHub ? 'text-[13px] font-medium' : '',
                              )}
                            >
                              {item.label}
                            </span>
                            {isHub ? (
                              <span className="mt-0.5 line-clamp-1 text-[11px] leading-snug text-muted-foreground">
                                {item.description}
                              </span>
                            ) : null}
                          </span>
                          {isHub ? (
                            <ChevronRight
                              size={14}
                              className="shrink-0 text-muted-foreground/40 transition-colors group-hover/item:text-primary/70"
                              aria-hidden
                            />
                          ) : null}
                        </NavLink>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
