# План 14: Сервер (`/server-monitor`)

> **Маршрут:** `/server-monitor`  
> **Приоритет:** P3  
> **Файлы:** `ServerMonitorPage.tsx`, `ResourceHistoryCharts.tsx`, `ChartResponsive.tsx`

## Текущее состояние

Gauge grids `sm:grid-cols-2 xl:grid-cols-3`. Charts через ChartResponsive — в целом OK.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | vnStat SelectTrigger min-w-[220px] | Средняя |
| 2 | Period buttons + select в одном ряду | Средняя |
| 3 | Page header не stacked на mobile | Низкая |

## Промпты

### Prompt 1 — vnStat controls

```
Прочитай reviews/responsive-14-server-monitor.md.

ServerMonitorPage.tsx блок vnStat:
- Select: w-full sm:min-w-[220px] sm:max-w-[320px]
- Period buttons: flex-wrap, на <sm grid grid-cols-3 gap-1
- Card header: flex-col sm:flex-row sm:items-center sm:justify-between

npm run build.
```

### Prompt 2 — Gauge grids audit

```
Проверь все grid в ServerMonitorPage и ResourceHistoryCharts:
base grid-cols-1, sm:grid-cols-2, xl:grid-cols-3 — исправь если где-то нет base 1 col.
```

## Чеклист: 320 / 375 / 1024

## Статус: ⬜ Не начато
