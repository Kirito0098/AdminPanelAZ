# План 12: Конфиг AntiZapret (`/antizapret`)

> **Маршрут:** `/antizapret`  
> **Приоритет:** P3  
> **Файлы:** `AntizapretConfigPage.tsx`, `AntizapretConfigTab.tsx`

## Текущее состояние

Формы и опции, `lg:grid-cols-2` для панелей. Sticky save bar с кнопками.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | Sticky action bar + header — много кнопок на 375px | Средняя |
| 2 | Option groups `sm:grid-cols-2` с divide-x | Низкая |
| 3 | Breadcrumb arrows hidden на mobile | Низкая |
| 4 | Длинные формы — много скролла | Ожидаемо |

## Промпты

### Prompt 1 — Sticky action bar

```
Прочитай reviews/responsive-12-antizapret.md.

В AntizapretConfigTab.tsx (или AntizapretConfigPage.tsx):
- Sticky toolbar: flex-wrap gap-2
- <sm: primary save full-width, secondary в row of 2
- Проверить что sticky top не перекрывает mobile header (z-index)

npm run build.
```

### Prompt 2 — Option groups

```
В AntizapretConfigTab.tsx option groups:
sm:grid-cols-2 → grid-cols-1 sm:grid-cols-2
На mobile divide-y вместо divide-x между опциями.
```

## Чеклист: 375 / 1024

## Статус: ⬜ Не начато
