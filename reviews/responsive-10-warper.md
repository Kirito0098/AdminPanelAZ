# План 10: AZ-WARP (`/warper`)

> **Маршрут:** `/warper`  
> **Приоритет:** P2  
> **Файлы:** `WarperPage.tsx`, `DomainsTab.tsx`, `CatalogTab.tsx`, `IpRangesTab.tsx`, `MonitoringTab.tsx`, `SettingsTab.tsx`, `TrafficTab.tsx`, `OverviewCards.tsx`

## Текущее состояние

5 вкладок в `TabsList` с `grid-cols-2` на mobile — сетка 2+2+1. Вложенные табы в MonitoringTab.

## Проблемы

| # | Проблема | Компонент | Серьёзность |
|---|----------|-----------|-------------|
| 1 | 5 tabs в grid-cols-2 | `WarperPage.tsx` | Высокая |
| 2 | IpRanges filter min-w-[220px] | `IpRangesTab.tsx` | Средняя |
| 3 | TrafficTab grid-cols-2 stats | `TrafficTab.tsx` | Средняя |
| 4 | MonitoringTab nested grid-cols-3 | `MonitoringTab.tsx` | Средняя |
| 5 | pre blocks wide commands | разные | Низкая |

## Критерии приёмки

- [ ] Вкладки: на mobile scrollable horizontal tabs ИЛИ 1 col list, не 2+2+1 grid.
- [ ] Все filter inputs `w-full min-w-0` на `<sm`.
- [ ] Overview cards: `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`.

## Промпты

### Prompt 1 — Warper tabs layout

```
Прочитай reviews/responsive-10-warper.md.

В frontend/src/pages/WarperPage.tsx переделай TabsList для 5 вкладок:
Вариант A (предпочтительно): flex overflow-x-auto snap-x на <sm, sm:inline-flex как сейчас
Вариант B: grid-cols-1 на <sm (вертикальный список табов)

Убрать grid-cols-2 для 5 tabs. Short labels на <sm если длинные.
npm run build.
```

### Prompt 2 — IpRangesTab + TrafficTab

```
IpRangesTab.tsx: min-w-[220px] → w-full sm:min-w-[220px] sm:flex-1
TrafficTab.tsx: grid-cols-2 → grid-cols-1 sm:grid-cols-2 lg:grid-cols-4
npm run build.
```

### Prompt 3 — MonitoringTab nested tabs

```
MonitoringTab.tsx: TabsList grid-cols-3 на mobile заменить на flex flex-wrap или horizontal scroll.
Согласовать с родительским WarperPage.
```

## Чеклист: 320 / 375 / 640 / 1024

## Статус: ⬜ Не начато
