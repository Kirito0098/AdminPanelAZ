# Settings Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the settings hover-flyout with a `/settings` hub (search + grouped links) and a desktop secondary nav on `/settings/:section`, without changing backend or section inventory.

**Architecture:** Keep `SettingsNav.tsx` as the source of truth for groups/visibility. Add a pure filter helper + shared `SettingsSectionBrowser` UI. `SettingsPage` branches: no `section` → hub; valid section → secondary nav + tab; invalid/unavailable → redirect to `/settings`. Main sidebar gets a normal `NavLink` to `/settings`; delete `SettingsSidebarSection` flyout.

**Tech Stack:** React 18, React Router, Tailwind, lucide-react, existing shadcn `Input`/`Button`, vitest, TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-12-settings-hub-design.md`

## Global Constraints

- No command palette (⌘K); no backend/API changes; no renaming/merging settings sections.
- Do not simplify the rest of the left sidebar (ops/config modules).
- Visibility: always via `getVisibleNavGroups` / `isSectionAvailable` / feature toggles — never show gated items.
- Search: case-insensitive substring on `label` + `description`; local `useState` only (not URL).
- Empty `/settings` must render the hub (stop redirecting to `defaultSection`).
- Invalid or feature-gated `/settings/:section` → `Navigate` to `/settings` (not `personal`).
- Non-admin: keep sidebar «Мой профиль» → `/settings/personal`; hub at `/settings` may show a single personal link.
- Desktop secondary nav: `hidden lg:block` (match `MobileSettingsSectionPicker` which is `lg:hidden`).
- Russian UI copy; commit after each task; `git add -f` for `docs/superpowers/` if touched.
- Prefer deleting `SettingsSidebarSection.tsx` over leaving dead flyout code.

## File map

| File | Role |
|------|------|
| `frontend/src/components/settings/SettingsNav.tsx` | Export `filterNavGroupsByQuery` |
| `frontend/src/components/settings/SettingsNav.filter.test.ts` | Unit tests for filter |
| `frontend/src/components/settings/SettingsSectionBrowser.tsx` | Search + grouped links (`variant`: `hub` \| `nav`) |
| `frontend/src/pages/SettingsPage.tsx` | Hub branch; secondary nav layout; redirects |
| `frontend/src/components/Layout.tsx` | Admin «Настройки» → `/settings`; remove flyout |
| `frontend/src/components/settings/SettingsSidebarSection.tsx` | **Delete** |
| `frontend/src/components/settings/MobileSettingsSectionPicker.tsx` | Optional «Все настройки» link |
| `CHANGELOG.md` | Unreleased Changed note |

---

### Task 1: `filterNavGroupsByQuery` + unit tests

**Files:**
- Modify: `frontend/src/components/settings/SettingsNav.tsx` (append export after `getVisibleNavGroups`)
- Create: `frontend/src/components/settings/SettingsNav.filter.test.ts`

**Interfaces:**
- Consumes: `SettingsNavGroup`, `SettingsNavItem`
- Produces:

```ts
export function filterNavGroupsByQuery(
  groups: SettingsNavGroup[],
  query: string,
): SettingsNavGroup[]
```

Empty/whitespace query → return `groups` unchanged (same references OK). Non-empty → filter items where `label` or `description` includes query (case-insensitive); drop groups with zero items.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/components/settings/SettingsNav.filter.test.ts
import { describe, expect, it } from 'vitest'
import { User, Users } from 'lucide-react'
import { filterNavGroupsByQuery, type SettingsNavGroup } from './SettingsNav'

const SAMPLE: SettingsNavGroup[] = [
  {
    label: 'Личное',
    items: [
      {
        id: 'personal',
        label: 'Мой профиль',
        icon: User,
        description: 'Тема, пароль, Telegram',
      },
    ],
  },
  {
    label: 'Кто может войти',
    adminOnly: true,
    items: [
      {
        id: 'users',
        label: 'Пользователи',
        icon: Users,
        description: 'Учётные записи панели',
        settingsTab: 'users',
        adminOnly: true,
      },
    ],
  },
]

describe('filterNavGroupsByQuery', () => {
  it('returns groups unchanged for empty query', () => {
    expect(filterNavGroupsByQuery(SAMPLE, '')).toEqual(SAMPLE)
    expect(filterNavGroupsByQuery(SAMPLE, '   ')).toEqual(SAMPLE)
  })

  it('matches label case-insensitively', () => {
    const result = filterNavGroupsByQuery(SAMPLE, 'профиль')
    expect(result).toHaveLength(1)
    expect(result[0].items.map((i) => i.id)).toEqual(['personal'])
  })

  it('matches description', () => {
    const result = filterNavGroupsByQuery(SAMPLE, 'учётные')
    expect(result).toHaveLength(1)
    expect(result[0].items[0].id).toBe('users')
  })

  it('drops empty groups', () => {
    expect(filterNavGroupsByQuery(SAMPLE, 'нет-такого-раздела')).toEqual([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/settings/SettingsNav.filter.test.ts`

Expected: FAIL — `filterNavGroupsByQuery` is not exported / not a function.

- [ ] **Step 3: Implement helper**

Append to `SettingsNav.tsx`:

```ts
export function filterNavGroupsByQuery(
  groups: SettingsNavGroup[],
  query: string,
): SettingsNavGroup[] {
  const q = query.trim().toLowerCase()
  if (!q) return groups
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q),
      ),
    }))
    .filter((group) => group.items.length > 0)
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- src/components/settings/SettingsNav.filter.test.ts`

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/SettingsNav.tsx \
  frontend/src/components/settings/SettingsNav.filter.test.ts
git commit -m "$(cat <<'EOF'
Add settings nav search filter helper.

EOF
)"
```

---

### Task 2: `SettingsSectionBrowser` shared UI

**Files:**
- Create: `frontend/src/components/settings/SettingsSectionBrowser.tsx`
- Reuse: `@/components/ui/input`, `@/components/ui/button`, `cn`, `NavLink`, `filterNavGroupsByQuery`

**Interfaces:**
- Consumes: `filterNavGroupsByQuery`, `SettingsNavGroup`, `getVisibleNavGroups` (caller passes already-visible groups)
- Produces:

```tsx
type SettingsSectionBrowserProps = {
  groups: SettingsNavGroup[]
  variant: 'hub' | 'nav'
  /** When set, highlights active section link (nav variant). */
  activeSection?: SettingsSection
  className?: string
}

export default function SettingsSectionBrowser(props: SettingsSectionBrowserProps): JSX.Element
```

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/settings/SettingsSectionBrowser.tsx
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
```

- [ ] **Step 2: Typecheck the new file**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | head -40`

Expected: no errors referencing `SettingsSectionBrowser` (project may already be clean).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/SettingsSectionBrowser.tsx
git commit -m "$(cat <<'EOF'
Add SettingsSectionBrowser for hub and secondary nav.

EOF
)"
```

---

### Task 3: Hub branch on `SettingsPage`

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Interfaces:**
- Consumes: `SettingsSectionBrowser`, `getVisibleNavGroups`
- Produces: when `!sectionParam`, render hub (do **not** treat missing param as redirect)

- [ ] **Step 1: Split redirect logic and add hub render**

Replace the block that currently does:

```tsx
if (!activeSection) {
  return <Navigate to={`/settings/${defaultSection}`} replace />
}
```

with:

```tsx
const visibleGroups = useMemo(
  () => getVisibleNavGroups(isAdmin, isSettingsTabEnabled, isEnabled),
  [isAdmin, isSettingsTabEnabled, isEnabled],
)

// Invalid or gated section → hub (not defaultSection)
if (sectionParam && !activeSection) {
  return <Navigate to="/settings" replace />
}

if (!sectionParam) {
  return (
    <div className="flex flex-col gap-6 orientation-compact-settings-page">
      <HaReplicaBanner />
      <PageSectionHeader
        icon={isAdmin ? Settings : UserIcon}
        title={isAdmin ? 'Настройки' : 'Мой профиль'}
        titleAddon={<NodeBadge name={activeNode?.name ?? settings?.node_name} status={activeNode?.status} />}
        description={
          isAdmin
            ? 'Профиль, доступ, VPN и работа панели — выберите раздел'
            : 'Тема, пароль, Telegram и дополнительная защита при входе'
        }
      />
      <SettingsSectionBrowser groups={visibleGroups} variant="hub" />
    </div>
  )
}

// activeSection is non-null below
```

Add imports:

```ts
import SettingsSectionBrowser from '@/components/settings/SettingsSectionBrowser'
import { getVisibleNavGroups, /* existing */ } from '@/components/settings/SettingsNav'
```

Remove unused `defaultSection` / `getDefaultSection` if nothing else references them after this change.

Keep the existing section render path for when `activeSection` is set (Task 4 wraps it with secondary nav).

- [ ] **Step 2: Manual sanity via tsc**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "$(cat <<'EOF'
Render settings hub at /settings instead of redirecting.

EOF
)"
```

---

### Task 4: Desktop secondary nav on section pages

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx` (section return JSX)
- Modify: `frontend/src/components/settings/MobileSettingsSectionPicker.tsx` (hub link)

**Interfaces:**
- Consumes: `SettingsSectionBrowser` `variant="nav"`, `activeSection`
- Produces: two-column layout on `lg+`; mobile picker unchanged in role

- [ ] **Step 1: Wrap section content**

Replace the section page outer return (the one after hub/redirect guards) so structure is:

```tsx
return (
  <div className="flex flex-col gap-6 orientation-compact-settings-page">
    <ConfirmDialogHost dialogProps={dialogProps} />
    <HaReplicaBanner />
    <PageSectionHeader
      icon={isAdmin ? Settings : UserIcon}
      title={isAdmin ? 'Настройки' : 'Мой профиль'}
      titleAddon={<NodeBadge name={activeNode?.name ?? settings?.node_name} status={activeNode?.status} />}
      description={
        isAdmin
          ? 'Профиль, доступ, VPN и работа панели'
          : 'Тема, пароль, Telegram и дополнительная защита при входе'
      }
    />

    <div className="flex items-center gap-3 lg:hidden">
      <div className="min-w-0 flex-1">
        <MobileSettingsSectionPicker value={activeSection} />
      </div>
      <NavLink
        to="/settings"
        className="shrink-0 text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Все настройки
      </NavLink>
    </div>

    <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-8">
      <aside className="hidden w-56 shrink-0 lg:sticky lg:top-4 lg:block">
        <SettingsSectionBrowser
          groups={visibleGroups}
          variant="nav"
          activeSection={activeSection}
        />
      </aside>

      <div className="min-w-0 flex-1 flex flex-col gap-4 orientation-compact-settings-section">
        <div className="orientation-compact-settings-section-header">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="text-base font-semibold tracking-tight">{sectionMeta.title}</h3>
            <p className="text-xs text-muted-foreground">{sectionMeta.description}</p>
          </div>
          {sectionMeta.hint ? (
            <p className="mt-1 text-xs text-muted-foreground/80">{sectionMeta.hint}</p>
          ) : null}
        </div>
        {renderSection()}
      </div>
    </div>
  </div>
)
```

Import `NavLink` from `react-router-dom` if not already imported.

Note: `MobileSettingsSectionPicker` returns `null` when ≤1 item — the «Все настройки» link should still show (wrap so link is always visible on mobile even if picker is null):

```tsx
<div className="flex items-center justify-between gap-3 lg:hidden">
  <div className="min-w-0 flex-1">
    <MobileSettingsSectionPicker value={activeSection} />
  </div>
  <NavLink to="/settings" className="...">Все настройки</NavLink>
</div>
```

- [ ] **Step 2: tsc**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx \
  frontend/src/components/settings/MobileSettingsSectionPicker.tsx
git commit -m "$(cat <<'EOF'
Add settings secondary nav and hub link on section pages.

EOF
)"
```

---

### Task 5: Replace sidebar flyout with NavLink

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Delete: `frontend/src/components/settings/SettingsSidebarSection.tsx`

**Interfaces:**
- Produces: admin «Система» includes `{ to: '/settings', label: 'Настройки', icon: Settings, end: false, adminOnly: true, featureKey: null }`
- Non-admin still injects «Мой профиль» → `/settings/personal`

- [ ] **Step 1: Wire Layout**

1. Import `Settings` from `lucide-react` (in addition to existing icons).
2. Remove: `import SettingsSidebarSection from '...'`.
3. Append to `NAV_GROUPS` «Система» `items` array:

```ts
{ to: '/settings', label: 'Настройки', icon: Settings, end: false, adminOnly: true, featureKey: null },
```

4. Remove the JSX line:

```tsx
{group.label === 'Система' && isAdmin && <SettingsSidebarSection onNavigate={onNavigate} />}
```

5. Keep non-admin push of «Мой профиль» to `/settings/personal` as-is.

- [ ] **Step 2: Delete flyout file**

```bash
rm frontend/src/components/settings/SettingsSidebarSection.tsx
```

Grep to confirm no remaining imports:

```bash
rg "SettingsSidebarSection" frontend
```

Expected: no matches.

- [ ] **Step 3: tsc + filter tests**

Run:

```bash
cd frontend && npm test -- src/components/settings/SettingsNav.filter.test.ts && npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout.tsx
git add -u frontend/src/components/settings/SettingsSidebarSection.tsx
git commit -m "$(cat <<'EOF'
Replace settings hover flyout with sidebar link to hub.

EOF
)"
```

---

### Task 6: Changelog + acceptance checklist

**Files:**
- Modify: `CHANGELOG.md` under `## [Unreleased]` → `### 🔄 Changed`

- [ ] **Step 1: Add changelog bullet**

```markdown
- **Настройки: hub вместо flyout** — пункт «Настройки» ведёт на `/settings` с поиском и группами разделов; на `/settings/:section` — sticky secondary nav (desktop) и picker (mobile); hover-flyout удалён (`SettingsPage.tsx`, `SettingsSectionBrowser.tsx`, `Layout.tsx`).
```

- [ ] **Step 2: Manual acceptance (browser or smoke notes)**

Checklist (tick in PR/commit message body if not automated):

1. Sidebar: no section list / no hover panel; «Настройки» active on any `/settings*`.
2. `/settings` shows hub + search; empty search message + reset works.
3. Click section → content; deep-link `/settings/modules` works.
4. Fake `/settings/not-a-section` and gated section → `/settings`.
5. Mobile: picker + «Все настройки»; desktop: left nav sticky.
6. Non-admin: «Мой профиль» still works.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
Document settings hub navigation in changelog.

EOF
)"
```

- [ ] **Step 4: Mark spec status (optional)**

In `docs/superpowers/specs/2026-09-12-settings-hub-design.md` set `**Статус:** implemented` and force-add:

```bash
git add -f docs/superpowers/specs/2026-09-12-settings-hub-design.md
git commit -m "$(cat <<'EOF'
Mark settings hub design spec as implemented.

EOF
)"
```

Only after all prior tasks are done and acceptance checked.

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Sidebar NavLink `/settings`, no flyout | 5 |
| Hub with search + groups | 1–3 |
| Secondary nav desktop + mobile picker | 4 |
| Search label+description, empty state | 1–2 |
| Invalid/gated → `/settings` | 3 |
| Feature gates via existing helpers | 3–4 (reuse `getVisibleNavGroups`) |
| Non-admin personal deep-link | 5 (unchanged inject) |
| Out of scope: palette, backend, other sidebar | Global Constraints |
| Changelog | 6 |
| tsc | 3–5 |

**Placeholder scan:** none.  
**Type consistency:** `filterNavGroupsByQuery`, `SettingsSectionBrowser` props used as defined in Tasks 1–2.
