# План 02: NOC Мониторинг (`/monitoring`)

> **Маршрут:** `/monitoring`  
> **Приоритет:** P0  
> **Файлы:** `MonitoringPage.tsx`, `MonitoringConnectionsList.tsx`, `NodesCompareSection.tsx`, `ServiceMatrix.tsx`

## Текущее состояние

- Connections: карточки `<xl`, таблица `≥xl` (1280px) — **позже**, чем Traffic/Nodes (`lg`).
- Сводка по узлам (federated table): **только таблица**, `overflow-x-auto`, 9+ колонок.
- `NodesCompareSection`: таблица с `min-w-[140px]` на узел, без card view.
- Scope toggle + auto-refresh в header без `flex-wrap`.

## Проблемы

| # | Проблема | Файл | Серьёзность |
|---|----------|------|-------------|
| 1 | Node summary table без mobile cards | `MonitoringPage.tsx` | Критическая |
| 2 | Connections breakpoint `xl` vs `lg` elsewhere | `MonitoringConnectionsList.tsx` | Высокая |
| 3 | Table `min-w-[1080px]` | `MonitoringConnectionsList.tsx` | Высокая |
| 4 | NodesCompare без card fallback | `NodesCompareSection.tsx` | Высокая |
| 5 | Header controls overflow | `MonitoringPage.tsx` | Средняя |
| 6 | `whitespace-nowrap` на фильтре «Только онлайн» | `MonitoringConnectionsList.tsx` | Низкая |

## Критерии приёмки

- [ ] Все широкие таблицы имеют card view на `<lg` (1024px).
- [ ] Единый порог `lg` для connections list (как Traffic).
- [ ] На 768px нет горизонтального скролла всей страницы.
- [ ] NodesCompare: на mobile — карточка на узел со списком метрик.

## Порядок работ

1. `MonitoringConnectionsList` — сменить `xl` → `lg`.
2. `MonitoringPage` — mobile cards для federated node summary.
3. `NodesCompareSection` — mobile card layout.
4. Header `flex-wrap`.

---

## Промпты

### Prompt 1 — Connections list breakpoint

```
Прочитай reviews/responsive-02-monitoring.md.

В frontend/src/components/monitoring/MonitoringConnectionsList.tsx:
- Замени порог xl на lg для переключения ConnectionCard / Table
- lg:hidden для cards, hidden lg:block для table
- Убедись что сортировка работает в обоих режимах

npm run build.
```

### Prompt 2 — Federated node summary cards

```
Прочитай reviews/responsive-02-monitoring.md.

В frontend/src/pages/MonitoringPage.tsx найди таблицу «Сводка по узлам» (federated).
Добавь mobile альтернативу:
- <lg: карточка на каждый узел (имя, статус, CPU/RAM progress, OVPN/WG online, службы)
- lg+: существующая таблица

Паттерн как в LogsPage (md:hidden cards / hidden md:block table), но порог lg.
Вынеси NodeSummaryCard в отдельный компонент если блок >80 строк.
npm run build.
```

### Prompt 3 — NodesCompareSection cards

```
Прочитай reviews/responsive-02-monitoring.md.

В frontend/src/components/dashboard/NodesCompareSection.tsx:
- <lg: для каждого узла Card с метриками списком (не таблица)
- lg+: CompareTable как сейчас

Сохранить collapsible поведение. npm run build.
```

### Prompt 4 — Page header wrap

```
В MonitoringPage.tsx оберни ScopeToggle + AutoRefresh + заголовок в flex flex-wrap gap-2.
На <sm — column layout. Без логических изменений.
```

---

## Чеклист

| 768px | 1024px | 1280px |
|-------|--------|--------|
| Cards, no page scroll-x | Table appears | Full table |

## Статус: ⬜ Не начато
