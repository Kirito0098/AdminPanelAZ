# План 08: Настройки (`/settings/:section`)

> **Маршрут:** `/settings/personal|users|security|...` (12 разделов)  
> **Приоритет:** P1  
> **Файлы:** `SettingsPage.tsx`, `SettingsSidebarSection.tsx`, все `*Tab.tsx` в `settings/`

## Разделы

| ID | Компонент | Основные responsive риски |
|----|-----------|---------------------------|
| `personal` | `PersonalTab.tsx` | sm:grid-cols-2 lg:grid-cols-3 |
| `users` | `UsersTab.tsx` | таблица пользователей, grid-cols-3 |
| `security` | `SecurityTab.tsx` | плотные формы, 2FA |
| `config_delivery` | `ConfigDeliveryTab.tsx` | md:grid-cols-2, hero grid |
| `maintenance` | `MaintenanceTab.tsx` | sm:grid-cols-3, длинные формы |
| `backup` | `BackupTab.tsx` | lg:grid-cols-4 |
| `monitoring` | `MonitoringTab.tsx` | MonitorSettingsCard grids |
| `vpn_network` | `VpnNetworkTab.tsx` | формы сети |
| `modules` | `FeatureTogglesTab.tsx` | md:grid-cols-3, много toggles |
| `updates` | `UpdatesTab.tsx` | sm:grid-cols-3/4 |
| `panel_ops` | `PanelOpsTab.tsx` | wizard dialogs |
| `tests` | `RunbookTab.tsx` | lg:grid-cols-4 |

## Текущее состояние

- Навигация только через сайдбар (`SettingsSidebarSection` — mobile accordion уже исправлен).
- На странице нет picker текущего раздела для mobile.
- Большинство табов: `md:grid-cols-2` outer, inner `sm:grid-cols-3` — плотно на 640–767px.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | Нет mobile section picker на странице | Высокая |
| 2 | FeatureTogglesTab / UsersTab плотные сетки | Высокая |
| 3 | TwoFactorTab grid-cols-2 backup codes | Средняя |
| 4 | UsersTab table без cards | Средняя |
| 5 | Sticky save bars на нескольких табах | Средняя |
| 6 | Publish wizards / dialogs | Низкая |

## Критерии приёмки

- [ ] На mobile видно текущий раздел и можно переключить без сайдбара.
- [ ] Все grid: base `grid-cols-1`.
- [ ] Users table: cards `<lg`.
- [ ] Toggles: 1 col mobile, 2 sm, 3 lg.

## Порядок работ

1. Mobile section picker на `SettingsPage`.
2. Shared grid utilities / audit всех Tab.
3. UsersTab table/cards.
4. FeatureTogglesTab density.

---

## Промпты

### Prompt 1 — Mobile section picker

```
Прочитай reviews/responsive-08-settings.md.

Добавь на SettingsPage.tsx (под заголовком) mobile-only (<lg) Select или Sheet
для переключения между разделами настроек.
Используй getVisibleNavGroups из SettingsNav.tsx — те же пункты что в сайдбаре.
Navigate to /settings/:section on change.
Не дублировать логику видимости — reuse getVisibleNavGroups.
npm run build.
```

### Prompt 2 — Grid audit all settings tabs

```
Прочитай reviews/responsive-08-settings.md.

Пройди все frontend/src/components/settings/*Tab.tsx:
Замени любые grid-cols-N без breakpoint на grid-cols-1 sm:grid-cols-2 lg:grid-cols-N.
Особое внимание: FeatureTogglesTab, UsersTab, BackupTab, UpdatesTab, RunbookTab.

Один коммит, минимальные className изменения. npm run build.
```

### Prompt 3 — UsersTab table cards

```
UsersTab.tsx:
<lg: card per user (username, role, actions)
lg+: existing table
Destructive actions в Dropdown на mobile.
npm run build.
```

### Prompt 4 — TwoFactorTab backup codes

```
TwoFactorTab.tsx:
grid-cols-2 sm:grid-cols-3 → grid-cols-1 sm:grid-cols-2 md:grid-cols-3
font-mono text-xs с break-all для кодов.
```

### Prompt 5 — SecurityTab + PersonalTab forms

```
SecurityTab.tsx, PersonalTab.tsx:
form rows flex-col sm:flex-row, inputs w-full
sticky footer buttons flex-col-reverse sm:flex-row на mobile
```

### Prompt 6 — Panel ops wizards (низкий приоритет)

```
PublishAccessWizard.tsx, PublishAwaitDialog.tsx:
проверить DialogContent на mobile — max-h-[90vh] overflow-y-auto, padding p-4
DialogDescription sr-only если нужно для a11y.
```

---

## Чеклист по разделам

| Раздел | 375px | 768px | 1024px |
|--------|-------|-------|--------|
| personal | ⬜ | ⬜ | ⬜ |
| users | ⬜ | ⬜ | ⬜ |
| security | ⬜ | ⬜ | ⬜ |
| config_delivery | ⬜ | ⬜ | ⬜ |
| maintenance | ⬜ | ⬜ | ⬜ |
| backup | ⬜ | ⬜ | ⬜ |
| monitoring | ⬜ | ⬜ | ⬜ |
| vpn_network | ⬜ | ⬜ | ⬜ |
| modules | ⬜ | ⬜ | ⬜ |
| updates | ⬜ | ⬜ | ⬜ |
| panel_ops | ⬜ | ⬜ | ⬜ |
| tests | ⬜ | ⬜ | ⬜ |

## Статус: ⬜ Не начато
