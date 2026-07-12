# План 15: Login (`/login`)

> **Маршрут:** `/login`  
> **Приоритет:** P3 (низкий — уже неплохо адаптирован)  
> **Файл:** `frontend/src/pages/LoginPage.tsx`

## Текущее состояние

Страница вне `Layout`, центрированная форма `max-w-md`, `p-4`. Таблиц и сложных сеток нет.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | Строка captcha (img + кнопка) горизонтальная — тесно на 320px | Низкая |
| 2 | Telegram Login Widget без max-width | Низкая |
| 3 | Много алертов подряд — длинный скролл на маленьком экране | Низкая |
| 4 | WebAuthn / 2FA блоки без отдельного mobile spacing | Низкая |

## Критерии приёмки

- [ ] Форма читаема на 320px без горизонтального скролла.
- [ ] Captcha: на `<sm` img и кнопка в колонку.
- [ ] Кнопки входа full-width на mobile.

## Промпты

### Prompt 1 — Captcha и мелкие правки

```
Прочитай reviews/responsive-15-login.md.

Адаптируй frontend/src/pages/LoginPage.tsx для экранов 320–390px:
- блок captcha: flex-col на <sm, flex-row на sm+
- убедись что нет overflow-x на body
- Telegram widget container: max-w-full overflow-hidden

Минимальный diff. Не менять логику авторизации.
npm run build в frontend.
```

### Prompt 2 — WebAuthn / 2FA spacing

```
Прочитай reviews/responsive-15-login.md.

Улучши вертикальные отступы и читаемость блоков WebAuthn и 2FA в LoginPage.tsx на mobile.
Используй space-y-*, text-sm где уместно. Без изменения API.
```

## Чеклист

| 320px | 375px | 768px |
|-------|-------|-------|
| Форма без scroll-x | Captcha в колонку | Центрирование OK |

## Статус: ⬜ Не начато
