# Sidebar IA + Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the main left sidebar by operator role (Клиенты / Сеть / Наблюдение / Панель), rename home to **Клиенты**, and polish group/link visuals without changing routes or feature gates.

**Architecture:** Extract `NAV_GROUPS` into `frontend/src/components/nav/sidebarNav.ts` so IA can be unit-tested. `Layout.tsx` imports groups, filters visibility, injects non-admin «Мой профиль» into **Панель**, and applies modest visual class tweaks. Dashboard H2 + a few `/` deep-links that say «Конфигурации» become **Клиенты**.

**Tech Stack:** React, React Router, Tailwind, lucide-react, vitest, existing `orientation-compact-sidebar-*` CSS.

**Spec:** `docs/superpowers/specs/2026-09-12-sidebar-ia-design.md`

## Global Constraints

- Groups always expanded (no collapse / accordion / icon-rail / ⌘K).
- Do **not** change route paths, `featureKey` / `featureAnyOf` / `adminOnly` per item (only regroup + rename label for `/`).
- Home sidebar label and `DashboardPage` H2 = **Клиенты**; do **not** mass-rename VPN «конфигурации» copy in dialogs/action logs.
- Non-admin «Мой профиль» injects into group label **`Панель`** (not «Система»).
- Hide groups with zero visible items after filter.
- Visual polish stays on existing primary/muted tokens; no new brand palette.
- Commit after each task; `git add -f` for `docs/superpowers/` if touched.
- Settings hub (`/settings`) must keep working unchanged.

## File map

| File | Role |
|------|------|
| `frontend/src/components/nav/sidebarNav.ts` | `SIDEBAR_NAV_GROUPS` + types + visibility helpers (moved from Layout) |
| `frontend/src/components/nav/sidebarNav.test.ts` | IA order/labels unit tests |
| `frontend/src/components/Layout.tsx` | Import groups; inject profile; visual polish |
| `frontend/src/pages/DashboardPage.tsx` | H2 → Клиенты |
| `frontend/src/pages/Awg2Page.tsx` | Link to `/` copy → Клиенты (targeted) |
| `frontend/src/components/awg2/Awg2OverviewCards.tsx` | Targeted Клиенты links |
| `frontend/src/components/awg2/Awg2Hero.tsx` | Targeted Клиенты wording |
| `frontend/src/components/nodes/NodeSyncGroupSection.tsx` | «Клиенты → Синхронизировать» |
| `CHANGELOG.md` | Unreleased Changed |

---

### Task 1: Extract `sidebarNav.ts` with new IA + tests

**Files:**
- Create: `frontend/src/components/nav/sidebarNav.ts`
- Create: `frontend/src/components/nav/sidebarNav.test.ts`

**Interfaces:**
- Produces:

```ts
export type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
  end: boolean
  adminOnly: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
}

export type SidebarNavGroup = {
  label: string
  items: SidebarNavItem[]
}

export const SIDEBAR_NAV_GROUPS: SidebarNavGroup[]

export function isSidebarNavItemVisible(
  item: SidebarNavItem,
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): boolean

export function getVisibleSidebarNavGroups(
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): SidebarNavGroup[]
```

`getVisibleSidebarNavGroups` filters items via `isSidebarNavItemVisible`, drops empty groups, and does **not** inject «Мой профиль» (Layout still does that).

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/components/nav/sidebarNav.test.ts
import { describe, expect, it } from 'vitest'
import {
  SIDEBAR_NAV_GROUPS,
  getVisibleSidebarNavGroups,
  isSidebarNavItemVisible,
} from './sidebarNav'

describe('SIDEBAR_NAV_GROUPS IA', () => {
  it('has four role groups in order', () => {
    expect(SIDEBAR_NAV_GROUPS.map((g) => g.label)).toEqual([
      'Клиенты',
      'Сеть',
      'Наблюдение',
      'Панель',
    ])
  })

  it('names home Клиенты at /', () => {
    const home = SIDEBAR_NAV_GROUPS[0].items[0]
    expect(home).toMatchObject({ to: '/', label: 'Клиенты', end: true })
  })

  it('places settings under Панель', () => {
    const panel = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Панель')
    expect(panel?.items.map((i) => i.to)).toEqual([
      '/nodes',
      '/settings',
      '/telegram',
      '/edit-files',
    ])
  })

  it('keeps network tools under Сеть', () => {
    const net = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Сеть')
    expect(net?.items.map((i) => i.to)).toEqual([
      '/routing',
      '/antizapret',
      '/proxy',
      '/warper',
      '/awg2',
    ])
  })

  it('keeps observe tools under Наблюдение', () => {
    const obs = SIDEBAR_NAV_GROUPS.find((g) => g.label === 'Наблюдение')
    expect(obs?.items.map((i) => i.to)).toEqual([
      '/monitoring',
      '/traffic',
      '/logs',
      '/server-monitor',
    ])
  })
})

describe('visibility', () => {
  it('hides adminOnly items for non-admin', () => {
    const nodes = SIDEBAR_NAV_GROUPS.flatMap((g) => g.items).find((i) => i.to === '/nodes')!
    expect(isSidebarNavItemVisible(nodes, 'user', () => true)).toBe(false)
    expect(isSidebarNavItemVisible(nodes, 'admin', () => true)).toBe(true)
  })

  it('drops empty groups when features off', () => {
    const groups = getVisibleSidebarNavGroups('admin', () => false)
    // home has featureKey null → still visible; subscription gated off
    expect(groups.some((g) => g.label === 'Клиенты')).toBe(true)
    expect(groups.find((g) => g.label === 'Клиенты')?.items.map((i) => i.to)).toEqual(['/'])
  })
})
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `cd frontend && npm test -- src/components/nav/sidebarNav.test.ts`

Expected: FAIL — module not found / export missing.

- [ ] **Step 3: Implement `sidebarNav.ts`**

Move icon imports and item defs from current `Layout.tsx` `NAV_GROUPS`. Exact group contents:

```ts
// frontend/src/components/nav/sidebarNav.ts
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ClipboardList,
  Cpu,
  FileText,
  GitBranch,
  Globe,
  HardDrive,
  LayoutDashboard,
  Network,
  Send,
  Server,
  Settings,
  Settings2,
  Shield,
  Ticket,
} from 'lucide-react'

export type SidebarNavItem = {
  to: string
  label: string
  icon: LucideIcon
  end: boolean
  adminOnly: boolean
  featureKey: string | null
  featureAnyOf?: readonly string[]
}

export type SidebarNavGroup = {
  label: string
  items: SidebarNavItem[]
}

export const SIDEBAR_NAV_GROUPS: SidebarNavGroup[] = [
  {
    label: 'Клиенты',
    items: [
      { to: '/', label: 'Клиенты', icon: LayoutDashboard, end: true, adminOnly: false, featureKey: null },
      {
        to: '/subscription',
        label: 'Подписка',
        icon: Ticket,
        end: false,
        adminOnly: true,
        featureKey: null,
        featureAnyOf: ['client_portal', 'unlock_codes'] as const,
      },
    ],
  },
  {
    label: 'Сеть',
    items: [
      { to: '/routing', label: 'Маршрутизация / CIDR', icon: GitBranch, end: false, adminOnly: true, featureKey: 'routing' },
      { to: '/antizapret', label: 'Конфиг AntiZapret', icon: Settings2, end: false, adminOnly: true, featureKey: 'antizapret_config' },
      { to: '/proxy', label: 'Прокси', icon: Network, end: false, adminOnly: true, featureKey: 'proxy_nodes' },
      { to: '/warper', label: 'AZ-WARP', icon: Globe, end: false, adminOnly: true, featureKey: 'warper' },
      { to: '/awg2', label: 'AZ-AWG2', icon: Shield, end: false, adminOnly: true, featureKey: 'awg2' },
    ],
  },
  {
    label: 'Наблюдение',
    items: [
      { to: '/monitoring', label: 'NOC Мониторинг', icon: Activity, end: false, adminOnly: true, featureKey: 'logs_dashboard' },
      { to: '/traffic', label: 'Мониторинг трафика', icon: HardDrive, end: false, adminOnly: false, featureKey: 'traffic_sync' },
      {
        to: '/logs',
        label: 'Журналы',
        icon: ClipboardList,
        end: false,
        adminOnly: true,
        featureKey: null,
        featureAnyOf: ['logs_dashboard', 'action_logs'] as const,
      },
      { to: '/server-monitor', label: 'Сервер', icon: Cpu, end: false, adminOnly: true, featureKey: 'server_monitor' },
    ],
  },
  {
    label: 'Панель',
    items: [
      { to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, featureKey: 'nodes' },
      { to: '/settings', label: 'Настройки', icon: Settings, end: false, adminOnly: true, featureKey: null },
      { to: '/telegram', label: 'Telegram', icon: Send, end: false, adminOnly: true, featureKey: 'telegram' },
      { to: '/edit-files', label: 'Редактор файлов', icon: FileText, end: false, adminOnly: true, featureKey: 'edit_files' },
    ],
  },
]

export function isSidebarNavItemVisible(
  item: SidebarNavItem,
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): boolean {
  if (item.featureAnyOf?.length) {
    if (!item.featureAnyOf.some((key) => isEnabled(key))) return false
  } else if (item.featureKey && !isEnabled(item.featureKey)) {
    return false
  }
  if (item.adminOnly) return userRole === 'admin'
  return true
}

export function getVisibleSidebarNavGroups(
  userRole: string | undefined,
  isEnabled: (key: string) => boolean,
): SidebarNavGroup[] {
  return SIDEBAR_NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => isSidebarNavItemVisible(item, userRole, isEnabled)),
  })).filter((group) => group.items.length > 0)
}
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd frontend && npm test -- src/components/nav/sidebarNav.test.ts`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/nav/sidebarNav.ts frontend/src/components/nav/sidebarNav.test.ts
git commit -m "$(cat <<'EOF'
Add role-based sidebar nav definitions and tests.

EOF
)"
```

---

### Task 2: Wire `Layout.tsx` + visual polish

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Optionally tweak group label classes only in `Layout.tsx` (prefer Tailwind on `NavGroupHeader` / group wrapper; avoid broad CSS rewrites unless needed)

**Interfaces:**
- Consumes: `SIDEBAR_NAV_GROUPS` or `getVisibleSidebarNavGroups`, `SidebarNavItem`, `isSidebarNavItemVisible`
- Produces: sidebar rendering with new IA; non-admin profile under **Панель**

- [ ] **Step 1: Replace local `NAV_GROUPS` / visibility with imports**

1. Remove local `NavItemDef` / `NavGroupDef` / `NAV_GROUPS` / `isNavItemVisible` if fully replaced.
2. Import from `@/components/nav/sidebarNav`.
3. Build visible groups:

```ts
const visibleGroups = getVisibleSidebarNavGroups(user?.role, isEnabled).map((group) => {
  if (group.label === 'Панель' && !isAdmin) {
    return {
      ...group,
      items: [
        ...group.items,
        {
          to: '/settings/personal',
          label: 'Мой профиль',
          icon: User,
          end: false,
          adminOnly: false,
          featureKey: null,
        },
      ],
    }
  }
  return group
})
// If non-admin has no Панель group yet (all panel items admin-only), still show profile:
```

Handle edge case: when `!isAdmin` and `getVisibleSidebarNavGroups` has **no** «Панель» group (all items adminOnly), append a synthetic group:

```ts
let groups = getVisibleSidebarNavGroups(user?.role, isEnabled)
if (!isAdmin) {
  const profileItem = {
    to: '/settings/personal',
    label: 'Мой профиль',
    icon: User,
    end: false,
    adminOnly: false,
    featureKey: null,
  } as const
  const panelIdx = groups.findIndex((g) => g.label === 'Панель')
  if (panelIdx >= 0) {
    groups = groups.map((g, i) =>
      i === panelIdx ? { ...g, items: [...g.items, profileItem] } : g,
    )
  } else {
    groups = [...groups, { label: 'Панель', items: [profileItem] }]
  }
}
const visibleGroups = groups
```

Use a mutable typed `SidebarNavItem` for profile (icon `User` still imported in Layout).

4. Remove old `group.label === 'Система'` inject.
5. Keep `SidebarNavLink` / sheet / footer behavior.

- [ ] **Step 2: Visual polish (Layout only)**

Update `NavGroupHeader`:

```tsx
function NavGroupHeader({ label }: { label: string }) {
  return (
    <p className="orientation-compact-sidebar-group-label px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80 first:pt-1">
      {label}
    </p>
  )
}
```

Wrap each group for separation:

```tsx
{visibleGroups.map((group, index) => (
  <div
    key={group.label}
    className={cn(index > 0 && 'mt-1 border-t border-border/40 pt-1')}
  >
    <NavGroupHeader label={group.label} />
    <ul className="space-y-0.5">
      ...
    </ul>
  </div>
))}
```

Softened active link (drop ring if present, keep bar + fill):

```tsx
isActive
  ? 'bg-primary/10 text-foreground'
  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
```

Keep left bar + icon chip as today.

- [ ] **Step 3: Smoke-check imports**

Run: `cd frontend && npm test -- src/components/nav/sidebarNav.test.ts`

Expected: PASS. Grep: `rg "Система|NAV_GROUPS|Конфигурации" frontend/src/components/Layout.tsx` → no old group labels / no «Конфигурации».

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "$(cat <<'EOF'
Wire role-based sidebar groups and polish nav visuals.

EOF
)"
```

---

### Task 3: Dashboard title + targeted «Клиенты» links

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx` (H2 only; keep toast «Конфигурации синхронизированы» — that refers to VPN configs)
- Modify: `frontend/src/pages/Awg2Page.tsx` — breadcrumb/link to `/`
- Modify: `frontend/src/components/awg2/Awg2OverviewCards.tsx`
- Modify: `frontend/src/components/awg2/Awg2Hero.tsx`
- Modify: `frontend/src/components/nodes/NodeSyncGroupSection.tsx` (two strings «Конфигурации → Синхронизировать»)

**Do not change:** `CreateClientDialog` / tg-mini labels «Конфигурации» (protocol selection), `actionLogLabels` comment, `haVerifySummary` WireGuard configs.

- [ ] **Step 1: Dashboard H2**

In `DashboardPage.tsx` replace:

```tsx
<h2 className="text-xl font-semibold tracking-tight sm:text-2xl">Клиенты</h2>
```

- [ ] **Step 2: Targeted deep-links**

Examples (match existing phrasing, only `/` navigation copy):

- Awg2Page: `Клиенты · AmneziaWG 2.0`
- Awg2OverviewCards: `title="Открыть Клиенты"`, `sub="Клиенты → AmneziaWG 2.0"`
- Awg2Hero: `Клиенты — на странице Клиенты; здесь…` → prefer `Клиенты — на главной странице Клиенты; здесь…` or shorter: `Управление клиентами — в разделе Клиенты; здесь обфускация и backup слоя.`
- NodeSyncGroupSection: `Клиенты → Синхронизировать`

Leave `Awg2HelpStub` «Конфигурации (вкладка AmneziaWG 2.0)» if it means the configs tab concept — if it links users to `/`, change to Клиенты.

- [ ] **Step 3: Verify grep**

Run: `rg "Конфигурации" frontend/src/pages/DashboardPage.tsx frontend/src/components/Layout.tsx`

Expected: no H2/menu hits (sync toast may remain).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx \
  frontend/src/pages/Awg2Page.tsx \
  frontend/src/components/awg2/Awg2OverviewCards.tsx \
  frontend/src/components/awg2/Awg2Hero.tsx \
  frontend/src/components/nodes/NodeSyncGroupSection.tsx
git commit -m "$(cat <<'EOF'
Rename dashboard and deep-links from Конфигурации to Клиенты.

EOF
)"
```

---

### Task 4: Changelog + acceptance

**Files:**
- Modify: `CHANGELOG.md` under `## [Unreleased]` → `### 🔄 Changed`
- Optionally: set spec status `implemented` + `git add -f`

- [ ] **Step 1: Changelog bullet**

```markdown
- **Сайдбар: группы по ролям** — Клиенты / Сеть / Наблюдение / Панель; домашний пункт и дашборд переименованы в **Клиенты**; лёгкий visual refresh заголовков/active (`sidebarNav.ts`, `Layout.tsx`, `DashboardPage.tsx`).
```

- [ ] **Step 2: Acceptance checklist (code-verify + note browser smoke)**

1. Four groups always expanded, order per spec.  
2. `/` + dashboard = Клиенты.  
3. Feature-gated items still hide; empty groups gone.  
4. Non-admin: profile under Панель.  
5. `/settings` hub still works.  
6. Mobile sheet matches IA.

Run: `cd frontend && npm test -- src/components/nav/sidebarNav.test.ts`

- [ ] **Step 3: Commit changelog (+ optional spec status)**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
Document sidebar IA refresh in changelog.

EOF
)"
```

Optional:

```bash
# set **Статус:** implemented in docs/superpowers/specs/2026-09-12-sidebar-ia-design.md
git add -f docs/superpowers/specs/2026-09-12-sidebar-ia-design.md
git commit -m "$(cat <<'EOF'
Mark sidebar IA design spec as implemented.

EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|------------------|------|
| Four role groups + item table | 1 |
| Клиенты at `/` | 1–3 |
| Visual group headers / active polish | 2 |
| Non-admin → Панель | 2 |
| Empty groups hidden | 1 (`getVisibleSidebarNavGroups`) |
| No route/gate changes | Global + 1 |
| No mass VPN «конфигурации» rename | 3 scope |
| Dashboard title | 3 |
| Targeted `/` links | 3 |
| Changelog | 4 |
| Settings hub untouched | Global |

**Placeholder scan:** none.  
**Type consistency:** `SidebarNavItem` / `getVisibleSidebarNavGroups` used as defined in Task 1.
