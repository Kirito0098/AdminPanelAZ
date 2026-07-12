# План 04: Журналы (`/logs`)

> **Маршрут:** `/logs`  
> **Приоритет:** P0  
> **Файл:** `frontend/src/pages/LogsPage.tsx`

## Текущее состояние

- **Хорошо:** OpenVPN/WireGuard connections и action logs — `md:block` table / `md:hidden` cards.
- **Плохо:** QR downloads и OVPN sockets — table only.
- Log viewer toolbar плотный (№, Хвост, Копировать, Скачать).
- Много вкладок в TabsList с flex-wrap.

## Проблемы

| # | Проблема | Серьёзность |
|---|----------|-------------|
| 1 | QR downloads table без cards | Высокая |
| 2 | OVPN sockets table без cards | Высокая |
| 3 | Breakpoint md vs lg inconsistency | Средняя |
| 4 | Log viewer toolbar dense | Средняя |
| 5 | Action log whitespace-nowrap timestamps | Низкая |
| 6 | Много tab triggers — 3+ ряда | Низкая |

## Критерии приёмки

- [ ] QR и Sockets: card view `<lg`.
- [ ] Унифицировать порог table/cards на `lg` (опционально миграция с md).
- [ ] Log viewer toolbar: `flex-wrap` + full-width search на mobile.

## Промпты

### Prompt 1 — QR downloads mobile cards

```
Прочитай reviews/responsive-04-logs.md.

В LogsPage.tsx вкладка QR downloads:
добавь lg:hidden card list (имя, дата, ссылка/действия)
hidden lg:block — существующая table
Паттерн как ActionLogCard в том же файле.
npm run build.
```

### Prompt 2 — OVPN sockets mobile cards

```
LogsPage.tsx вкладка OVPN sockets:
аналогично Prompt 1 — SocketCard компонент
поля: адрес, клиент, байты, время
npm run build.
```

### Prompt 3 — Unify breakpoint to lg (опционально)

```
LogsPage.tsx: connections и action logs — сменить md на lg для table/cards
если согласовано с Traffic/Monitoring. Обновить оба блока одновременно.
npm run build.
```

### Prompt 4 — Log viewer toolbar

```
Log viewer toolbar в LogsPage:
flex-col sm:flex-row, search w-full, кнопки flex-wrap gap-2
<sm: icon buttons для Копировать/Скачать с aria-label
```

## Чеклист: 375 / 768 / 1024

## Статус: ⬜ Не начато
