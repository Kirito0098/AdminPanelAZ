# План 07: Узлы (`/nodes`)

> **Маршрут:** `/nodes`  
> **Приоритет:** P1  
> **Файлы:** `NodesPage.tsx`, `NodeSyncGroupSection.tsx`, `NodePolicySummarySection.tsx`

## Текущее состояние

**Эталонный паттерн:** `lg:hidden` NodeCard / `hidden lg:block` table (10 колонок).

## Проблемы

| # | Проблема | Компонент | Серьёзность |
|---|----------|-----------|-------------|
| 1 | NodeCard grid-cols-2 metadata на 320px | `NodesPage.tsx` | Средняя |
| 2 | Table actions column много иконок | `NodesPage.tsx` | Средняя |
| 3 | NodeBulkActionsBar crowded | `NodesPage.tsx` | Средняя |
| 4 | Zone 1024–1100px table tight | table | Средняя |
| 5 | NodeSyncGroupSection tables | related | Средняя |
| 6 | NodePolicySummarySection overflow table | related | Средняя |

## Промпты

### Prompt 1 — NodeCard metadata

```
Прочитай reviews/responsive-07-nodes.md.

В NodesPage.tsx компонент NodeCard:
metadata grid-cols-2 → grid-cols-1 xs:grid-cols-2 (или sm:grid-cols-2)
actions row: flex-wrap
npm run build.
```

### Prompt 2 — Table actions mobile menu

```
NodesPage.tsx desktop table колонка «Действия»:
на lg (не xl!) если не помещается — DropdownMenu «⋯» с действиями вместо 5+ icon buttons
ИЛИ оставить table только xl+ и cards lg:hidden до xl — выбери минимальный diff.

Предпочтение: улучшить NodeCard actions на lg-hidden path, table для xl+.
```

### Prompt 3 — NodeBulkActionsBar

```
NodeBulkActionsBar: на <md свернуть в Dropdown «Действия с выбранными»,
на md+ — текущие кнопки в flex-wrap.
```

### Prompt 4 — NodeSyncGroupSection tables

```
NodeSyncGroupSection.tsx + NodePolicySummarySection.tsx:
добавь lg:hidden card views для таблиц sync groups / policy summary
или horizontal scroll с sticky first column — card view предпочтительнее.
npm run build.
```

## Чеклист: 375 / 1024 / 1100 / 1280

## Статус: ⬜ Не начато
