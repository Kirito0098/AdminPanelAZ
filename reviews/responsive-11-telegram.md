# План 11: Telegram (`/telegram`)

> **Маршрут:** `/telegram`  
> **Приоритет:** P2  
> **Файлы:** `TelegramPage.tsx`, `TelegramOverviewCards.tsx`, `TelegramSettingsPanel.tsx`, `TelegramRecipientsPanel.tsx`, `TelegramBotCommandsGuide.tsx`

## Текущее состояние

Табы с shortLabel на `<sm` — хороший паттерн. CommandTable скрывает колонку на mobile — эталон.

## Проблемы

| # | Проблема | Компонент | Серьёзность |
|---|----------|-----------|-------------|
| 1 | Overview xl:grid-cols-5 — скачок layout | `TelegramOverviewCards.tsx` | Средняя |
| 2 | SettingsPanel sm:grid-cols-3 плотно | `TelegramSettingsPanel.tsx` | Средняя |
| 3 | Recipients min-w-[7.5rem] toggles | `TelegramRecipientsPanel.tsx` | Средняя |
| 4 | Hero + disable section vertical space | page | Низкая |

## Промпты

### Prompt 1 — Overview cards grid

```
Прочитай reviews/responsive-11-telegram.md.

TelegramOverviewCards.tsx:
grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5
(убедиться что base = 1 col, не 2)
npm run build.
```

### Prompt 2 — Settings panel grids

```
TelegramSettingsPanel.tsx:
все sm:grid-cols-3 → grid-cols-1 sm:grid-cols-2 lg:grid-cols-3
Form rows: flex-col sm:flex-row для label+input пар.
npm run build.
```

### Prompt 3 — Recipients toggles

```
TelegramRecipientsPanel.tsx:
role toggles flex-col sm:flex-row, min-w-[7.5rem] → w-full sm:min-w-[7.5rem] sm:flex-1
npm run build.
```

## Чеклист: 320 / 640 / 1280

## Статус: ⬜ Не начато
