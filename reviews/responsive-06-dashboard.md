# План 06: Dashboard / Конфигурации (`/`)

> **Маршрут:** `/`  
> **Приоритет:** P1  
> **Файлы:** `DashboardPage.tsx`, `ConfigCardsSection.tsx`, `ConfigCard.tsx`, `MetricCard.tsx`

## Текущее состояние

- Hero с метриками: `sm:grid-cols-2 xl:grid-cols-4`.
- Тулбар админа: `flex-wrap`, но длинные кнопки.
- Список клиентов: вкладки с `flex-wrap`, фильтры в несколько рядов.
- Карточки клиентов: плотность через `gridColsClass` (см. global plan).

## Проблемы

| # | Проблема | Компонент | Серьёзность |
|---|----------|-----------|-------------|
| 1 | Hero toolbar: 4–5 широких кнопки на 375px | `DashboardPage.tsx` | Высокая |
| 2 | `ConfigCard` metadata `grid-cols-2` без sm base | `ConfigCard.tsx` | Высокая |
| 3 | Кнопки действий карточки `whitespace-nowrap` | `ConfigCard.tsx` | Средняя |
| 4 | Hero split на `xl` вместо `lg` — несогласованность | `DashboardPage.tsx` | Средняя |
| 5 | OpenVPN group buttons — много кнопок в ряд | `ConfigCardsSection.tsx` | Средняя |
| 6 | Bulk actions bar плотный на mobile | `ConfigCardsSection.tsx` | Средняя |

## Критерии приёмки

- [ ] На 375px hero: кнопки не вызывают overflow-x; читаемая «лесенка» или icon+short label.
- [ ] Карточка клиента: метаданные 1 колонка на `<sm`, 2 на `sm+`.
- [ ] Сетка карточек: всегда 1 колонка на `<640px` (после fix gridColsClass).
- [ ] Фильтры и вкладки переносятся без обрезания текста.

## Порядок работ

1. `ConfigCard.tsx` — responsive metadata grid + action buttons.
2. `DashboardPage.tsx` — hero toolbar (ToolbarButton или short labels).
3. `ConfigCardsSection.tsx` — bulk bar, OpenVPN groups.

---

## Промпты

### Prompt 1 — ConfigCard mobile

```
Прочитай reviews/responsive-06-dashboard.md.

Адаптируй frontend/src/components/dashboard/ConfigCard.tsx:
1. Блоки с grid-cols-2 → grid-cols-1 sm:grid-cols-2
2. Ряд кнопок действий: flex-wrap gap-2; на <sm кнопки flex-1 min-w-0 или icon-only с aria-label
3. Длинные значения: [overflow-wrap:anywhere] где уже есть truncate-конфликт

Не менять бизнес-логику. Минимальный diff. npm run build.
```

### Prompt 2 — Hero toolbar

```
Прочитай reviews/responsive-06-dashboard.md.

Адаптируй тулбар в frontend/src/pages/DashboardPage.tsx (кнопки Синхронизировать, CSV, Новый клиент):
- <sm: короткие подписи или icon + aria-label (Синхр., Экспорт, Импорт, + Клиент)
- sm+: текущие полные подписи
- сохранить flex-wrap

Опционально используй ToolbarButton из shared/ если уже создан.
npm run build.
```

### Prompt 3 — ConfigCardsSection filters

```
Прочитай reviews/responsive-06-dashboard.md.

В frontend/src/components/dashboard/ConfigCardsSection.tsx:
- OpenVPN group selector: на <sm вертикальный stack или горизонтальный scroll с snap, не overflow страницы
- Bulk actions: на <md кнопки в 2 колонки grid или accordion «Массовые действия»
- TabsList: убедиться что flex-wrap работает на 320px

npm run build.
```

### Prompt 4 — Hero layout breakpoint (опционально)

```
В DashboardPage.tsx замени xl:flex-row на lg:flex-row для hero блока,
если визуально не ломает 1024px. Согласовать с остальными страницами.
```

---

## Чеклист

| 375px | 640px | 1024px | 1280px |
|-------|-------|--------|--------|
| 1 col cards | Toolbar OK | Hero 2-col | Metrics 4-col |

## Статус: ⬜ Не начато
