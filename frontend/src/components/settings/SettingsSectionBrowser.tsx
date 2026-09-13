import { useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Search, X } from 'lucide-react'
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
          className={cn('pl-8', query && 'pr-8')}
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
        <div className="rounded-lg border border-dashed border-border/80 px-3 py-6 text-center">
          <p className="text-sm text-muted-foreground">Ничего не найдено</p>
          <Button type="button" variant="link" className="mt-1 h-auto p-0" onClick={() => setQuery('')}>
            Сбросить поиск
          </Button>
        </div>
      ) : (
        <div className={cn(isHub ? 'flex flex-col gap-6' : 'flex flex-col gap-3')}>
          {filtered.map((group) => (
            <div key={group.label}>
              {(filtered.length > 1 || isHub) && (
                <p
                  className={cn(
                    'text-xs font-medium text-muted-foreground',
                    isHub ? 'mb-2' : 'mb-1 px-2',
                  )}
                >
                  {group.label}
                </p>
              )}
              <ul className={cn(isHub ? 'grid gap-2 sm:grid-cols-2' : 'space-y-0.5')}>
                {group.items.map((item) => {
                  const Icon = item.icon
                  const active = activeSection === item.id
                  return (
                    <li key={item.id}>
                      <NavLink
                        to={`/settings/${item.id}`}
                        end
                        className={cn(
                          isHub
                            ? 'flex items-start gap-3 rounded-xl border border-border/70 bg-card px-3 py-3 text-left transition-colors hover:border-primary/30 hover:bg-muted/40'
                            : 'flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors',
                          !isHub &&
                            (active
                              ? 'bg-primary/10 font-medium text-foreground ring-1 ring-primary/20'
                              : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'),
                        )}
                      >
                        <span
                          className={cn(
                            'flex shrink-0 items-center justify-center rounded-lg border',
                            isHub ? 'h-9 w-9' : 'h-7 w-7',
                            active
                              ? 'border-primary/25 bg-primary/15 text-primary'
                              : 'border-transparent bg-muted/60 text-muted-foreground',
                          )}
                        >
                          <Icon size={isHub ? 18 : 15} strokeWidth={2} />
                        </span>
                        <span className="min-w-0">
                          <span className={cn('block truncate', isHub ? 'text-sm font-medium' : '')}>
                            {item.label}
                          </span>
                          {isHub ? (
                            <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
                              {item.description}
                            </span>
                          ) : null}
                        </span>
                      </NavLink>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
