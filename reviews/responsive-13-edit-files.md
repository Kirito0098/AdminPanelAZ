# План 13: Редактор файлов (`/edit-files`)

> **Маршрут:** `/edit-files`  
> **Приоритет:** P3  
> **Файл:** `frontend/src/pages/EditFilesPage.tsx`

## Текущее состояние

**Хороший паттерн:** sidebar `hidden lg:block`, mobile file picker через `Select` (`lg:hidden`). Editor full-width ниже `lg`.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | Textarea `min-h-[28rem]` — очень высокий на phone | Средняя |
| 2 | Header actions длинные русские labels | Низкая |
| 3 | Diff panel на mobile — проверить stack | Средняя |
| 4 | Select file picker UX на длинных путях | Низкая |

## Промпты

### Prompt 1 — Editor height mobile

```
Прочитай reviews/responsive-13-edit-files.md.

EditFilesPage.tsx:
- Textarea: min-h-[16rem] sm:min-h-[22rem] lg:min-h-[28rem]
- Header actions: <sm short labels или icon buttons (Копировать, Обновить)
- Убедиться diff/compare: flex-col на <lg если side-by-side

npm run build.
```

### Prompt 2 — File select UX

```
EditFilesPage.tsx mobile Select:
truncate длинных путей в SelectItem, title=full path.
Опционально группировка по директории — только если просто.
```

## Чеклист: 375 / 1024

## Статус: ⬜ Не начато
