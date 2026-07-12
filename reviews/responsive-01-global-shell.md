# План 01: глобальная оболочка (Layout + UI primitives)

> **Маршрут:** все страницы под `Layout`  
> **Приоритет:** P0  
> **Файлы:** `frontend/src/components/Layout.tsx`, `frontend/src/components/ui/button.tsx`, `frontend/src/components/ui/tabs.tsx`, `frontend/src/lib/configCardViewPrefs.ts`, `frontend/src/components/NodeSelector.tsx`

## Текущее состояние

- Сайдбар скрыт ниже `lg` (1024px), мобильное меню через `Sheet`.
- `NodeSelector` в шапке скрыт ниже `sm` (640px) — на телефоне нельзя сменить узел без обходных путей.
- `Button` и `TabsTrigger` глобально с `whitespace-nowrap` — длинные русские подписи не переносятся.
- `gridColsClass` в настройках карточек: режимы 2/3/4 колонки без mobile override.

## Проблемы (по приоритету)

| # | Проблема | Файл | Серьёзность |
|---|----------|------|-------------|
| 1 | NodeSelector недоступен на `<640px` | `Layout.tsx` | Высокая |
| 2 | `whitespace-nowrap` на всех кнопках | `button.tsx` | Высокая |
| 3 | `grid-cols-2/3/4` без `grid-cols-1` base | `configCardViewPrefs.ts` | Высокая |
| 4 | Нет единого компонента `PageToolbar` | — | Средняя |
| 5 | `TabsTrigger` nowrap | `tabs.tsx` | Средняя |
| 6 | Нет `SheetDescription` на части sheet-диалогов | разные | Низкая |

## Критерии приёмки

- [ ] На 375px в шапке доступен выбор узла (компактный селектор или кнопка в меню).
- [ ] Кнопки с длинным текстом на `<sm` показывают иконку + короткий label (или только иконку с `aria-label`).
- [ ] `gridColsClass('2'|'3'|'4')` даёт `grid-cols-1 sm:grid-cols-2 ...` а не фиксированные колонки на mobile.
- [ ] `npm run build` проходит без ошибок.
- [ ] Десктоп (≥1280px) визуально не деградировал.

## Порядок работ

### Фаза 1 — NodeSelector на mobile
Добавить компактный `NodeSelector` в header для `<sm` или в мобильный Sheet над навигацией.

### Фаза 2 — gridColsClass
Исправить `gridColsClass` в `configCardViewPrefs.ts`.

### Фаза 3 — Кнопки (опционально, осторожно)
Не снимать `whitespace-nowrap` глобально — добавить variant `wrap` или responsive helper `ToolbarButton`.

---

## Промпты

### Prompt 1 — NodeSelector на мобильных

```
Прочитай reviews/responsive-01-global-shell.md (Фаза 1).

Задача: на экранах <640px пользователь должен иметь возможность сменить активный узел.

Файлы: frontend/src/components/Layout.tsx, frontend/src/components/NodeSelector.tsx

Требования:
- Не ломать десктопный header (sm:flex и выше — как сейчас).
- На mobile (<sm): показать компактный NodeSelector в header ИЛИ вверху мобильного Sheet-меню.
- Минимальный diff, следовать стилю проекта (Tailwind, shadcn).
- Не менять API и бизнес-логику NodeContext.

Проверка: 375px — узел виден и переключается; 1280px — без изменений.
npm run build в frontend.
```

### Prompt 2 — gridColsClass mobile-first

```
Прочитай reviews/responsive-01-global-shell.md (Фаза 2).

Исправь frontend/src/lib/configCardViewPrefs.ts — функцию gridColsClass.

Сейчас case '2'|'3'|'4' возвращают grid-cols-N без mobile base.
Нужно:
- '1' → grid-cols-1
- '2' → grid-cols-1 sm:grid-cols-2
- '3' → grid-cols-1 sm:grid-cols-2 lg:grid-cols-3
- '4' → grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2k:grid-cols-4
- default (auto) — оставить как есть или уточнить аналогично

Минимальный diff. npm run build.
```

### Prompt 3 — ToolbarButton helper (опционально)

```
Прочитай reviews/responsive-01-global-shell.md (Фаза 3).

Создай переиспользуемый компонент frontend/src/components/shared/ToolbarButton.tsx:
- props: icon, label, shortLabel?, onClick, disabled?, variant?
- на <sm показывать shortLabel или только icon с aria-label=label
- на sm+ — полный label

Не меняй глобально button.tsx. Используй в DashboardPage hero toolbar как пилот.

npm run build.
```

---

## Чеклист тестирования

| Ширина | Что проверить |
|--------|---------------|
| 375px | Бургер-меню, NodeSelector, настройки в сайдбаре |
| 640px | NodeSelector в header появился |
| 1024px | Десктопный сайдбар, flyout настроек |
| 1280px | Без регрессий |

## Статус

| Фаза | Статус |
|------|--------|
| Фаза 1 NodeSelector | ⬜ |
| Фаза 2 gridColsClass | ⬜ |
| Фаза 3 ToolbarButton | ⬜ |
