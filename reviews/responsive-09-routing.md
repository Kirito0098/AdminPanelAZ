# План 09: Маршрутизация / CIDR (`/routing`)

> **Маршрут:** `/routing`  
> **Приоритет:** P2  
> **Файлы:** `RoutingPage.tsx`, `ProvidersTab.tsx`, `AnalysisTab.tsx`, `PipelineStatusBar.tsx`, `RoutingPageHeader.tsx`, `CidrPipelineTab.tsx`, `RoutingOverviewTab.tsx`

## Текущее состояние

Страница с 5+ вкладками. Табы с short label на `<sm` — хорошо. Providers и Pipeline — основные проблемы.

## Проблемы

| # | Проблема | Компонент | Серьёзность |
|---|----------|-----------|-------------|
| 1 | `CidrCountsGrid` grid-cols-3 всегда | `ProvidersTab.tsx` | Высокая |
| 2 | Search `min-w-[200px]` | `ProvidersTab.tsx` | Средняя |
| 3 | PipelineStatusBar до xl:grid-cols-6 | `PipelineStatusBar.tsx` | Средняя |
| 4 | AnalysisTab DPI table scroll only | `AnalysisTab.tsx` | Средняя |
| 5 | RoutingPageHeader dense on mobile | `RoutingPageHeader.tsx` | Средняя |
| 6 | Provider row actions wrap awkwardly | `ProvidersTab.tsx` | Низкая |

## Критерии приёмки

- [ ] CidrCounts: 1 col `<sm`, 3 col `sm+`.
- [ ] Pipeline steps: 2 col mobile, 3 md, 6 xl.
- [ ] Search full-width на mobile.
- [ ] Analysis table: card view `<lg` или collapsible rows.

## Промпты

### Prompt 1 — ProvidersTab CidrCountsGrid

```
Прочитай reviews/responsive-09-routing.md.

В frontend/src/components/routing/ProvidersTab.tsx:
- CidrCountsGrid: grid-cols-1 sm:grid-cols-3 (убрать divide-x на mobile, использовать divide-y sm:divide-x)
- Search field: w-full min-w-0, родитель flex-col sm:flex-row
- ProviderListItem: проверить flex-wrap на action buttons

npm run build.
```

### Prompt 2 — PipelineStatusBar

```
В frontend/src/components/routing/PipelineStatusBar.tsx:
grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6
Укоротить labels на <sm если есть step.description.
npm run build.
```

### Prompt 3 — AnalysisTab mobile

```
В frontend/src/components/routing/AnalysisTab.tsx:
Для широкой таблицы DPI/логов добавь <lg card view (одна карточка = одна строка)
или accordion по домену. Порог lg.
npm run build.
```

### Prompt 4 — RoutingPageHeader

```
В RoutingPageHeader.tsx: flex-col gap-3 на <md, кнопки w-full sm:w-auto.
```

## Чеклист: 375 / 768 / 1280

## Статус: ⬜ Не начато
