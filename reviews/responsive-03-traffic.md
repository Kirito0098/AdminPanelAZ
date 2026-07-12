# План 03: Мониторинг трафика (`/traffic`)

> **Маршрут:** `/traffic`  
> **Приоритет:** P0  
> **Файлы:** `TrafficPage.tsx`, `TrafficClientDetails.tsx`

## Текущее состояние

- **Хорошо:** основной список клиентов — `lg:hidden` cards / `hidden lg:block` table.
- **Плохо:** таблицы «Никогда не подключался» и «Осиротевшая статистика» — только table + scroll.
- Admin toolbar: фиксированные `w-[160px]`, `w-[180px]` на Select.
- `TrafficClientDetails`: charts в `grid-cols-2` без mobile base.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | Вторичные таблицы без mobile cards | Высокая |
| 2 | Admin Select фиксированной ширины | Средняя |
| 3 | Основная table ~12 колонок с nowrap | Средняя (desktop) |
| 4 | TrafficClientDetails grid-cols-2 | Средняя |
| 5 | TrafficShareBar min-w на 320px | Низкая |

## Критерии приёмки

- [ ] Все три табличных блока имеют card view на `<lg`.
- [ ] Admin controls: `w-full sm:w-[160px]` pattern.
- [ ] Детали клиента: графики 1 col на `<sm`.

## Промпты

### Prompt 1 — Secondary tables cards

```
Прочитай reviews/responsive-03-traffic.md.

В frontend/src/pages/TrafficPage.tsx добавь mobile card views для:
1. «Никогда не подключался»
2. «Осиротевшая статистика»

Порог lg (как основной список). Переиспользуй стиль карточек из основного списка клиентов.
npm run build.
```

### Prompt 2 — Admin toolbar selects

```
В TrafficPage.tsx замени фиксированные w-[160px]/w-[180px] на w-full sm:w-[...].
Toolbar: flex-col sm:flex-row на admin панели.
```

### Prompt 3 — TrafficClientDetails grid

```
В frontend/src/components/traffic/TrafficClientDetails.tsx:
grid-cols-2 → grid-cols-1 sm:grid-cols-2 для stat tiles и chart grid.
npm run build.
```

## Чеклист: 375px / 1024px / 1280px

## Статус: ⬜ Не начато
