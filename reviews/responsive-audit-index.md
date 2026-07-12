# Аудит адаптивной вёрстки — индекс планов

> Планы для поэтапного исправления mobile / tablet / Mac layout в основной панели AntiZapret.
> Каждый файл содержит: проблемы, критерии приёмки, порядок работ и **готовые промпты** для Cursor Agent.
>
> **Нумерация файлов = рекомендуемый порядок выполнения** (01 → 15).
>
> Контекст: Tailwind CSS уже используется; проблема в **desktop-first вёрстке** и несогласованных брейкпоинтах.

## Единые правила проекта (для всех страниц)

| Правило | Значение |
|---------|----------|
| Mobile base | Всегда `grid-cols-1` / `flex-col` по умолчанию |
| Tablet | `sm:` 640px, `md:` 768px |
| Desktop sidebar | `lg:` 1024px |
| Wide desktop | `xl:` 1280px, `2k:` 2400px (кастом) |
| Таблица ↔ карточки | Единый порог **`lg` (1024px)** для data tables |
| Кнопки на `<sm` | Иконка + короткий label или tooltip |
| Тестовые ширины | 320, 375, 390, 640, 768, 1024, 1280, 1440 px |

## Рекомендуемый порядок выполнения

| Шаг | P | Область | Файл |
|-----|---|---------|------|
| **01** | P0 | Глобальная оболочка | [responsive-01-global-shell.md](./responsive-01-global-shell.md) |
| **02** | P0 | NOC Мониторинг | [responsive-02-monitoring.md](./responsive-02-monitoring.md) |
| **03** | P0 | Мониторинг трафика | [responsive-03-traffic.md](./responsive-03-traffic.md) |
| **04** | P0 | Журналы | [responsive-04-logs.md](./responsive-04-logs.md) |
| **05** | — | Общие компоненты (опц.) | [responsive-05-shared-components.md](./responsive-05-shared-components.md) |
| **06** | P1 | Конфигурации (Dashboard) | [responsive-06-dashboard.md](./responsive-06-dashboard.md) |
| **07** | P1 | Узлы | [responsive-07-nodes.md](./responsive-07-nodes.md) |
| **08** | P1 | Настройки (12 разделов) | [responsive-08-settings.md](./responsive-08-settings.md) |
| **09** | P2 | Маршрутизация / CIDR | [responsive-09-routing.md](./responsive-09-routing.md) |
| **10** | P2 | AZ-WARP | [responsive-10-warper.md](./responsive-10-warper.md) |
| **11** | P2 | Telegram | [responsive-11-telegram.md](./responsive-11-telegram.md) |
| **12** | P3 | Конфиг AntiZapret | [responsive-12-antizapret.md](./responsive-12-antizapret.md) |
| **13** | P3 | Редактор файлов | [responsive-13-edit-files.md](./responsive-13-edit-files.md) |
| **14** | P3 | Сервер | [responsive-14-server-monitor.md](./responsive-14-server-monitor.md) |
| **15** | P3 | Login | [responsive-15-login.md](./responsive-15-login.md) |

## Планы по страницам (полная таблица)

| # | Маршрут | Файл плана | Основной файл |
|---|---------|------------|---------------|
| 01 | Layout (все) | [responsive-01-global-shell.md](./responsive-01-global-shell.md) | `Layout.tsx`, `button.tsx`, `tabs.tsx` |
| 02 | `/monitoring` | [responsive-02-monitoring.md](./responsive-02-monitoring.md) | `MonitoringPage.tsx` |
| 03 | `/traffic` | [responsive-03-traffic.md](./responsive-03-traffic.md) | `TrafficPage.tsx` |
| 04 | `/logs` | [responsive-04-logs.md](./responsive-04-logs.md) | `LogsPage.tsx` |
| 05 | Shared | [responsive-05-shared-components.md](./responsive-05-shared-components.md) | `ResponsiveDataView`, `ToolbarButton` |
| 06 | `/` | [responsive-06-dashboard.md](./responsive-06-dashboard.md) | `DashboardPage.tsx` |
| 07 | `/nodes` | [responsive-07-nodes.md](./responsive-07-nodes.md) | `NodesPage.tsx` |
| 08 | `/settings/:section` | [responsive-08-settings.md](./responsive-08-settings.md) | `SettingsPage.tsx` + 12 табов |
| 09 | `/routing` | [responsive-09-routing.md](./responsive-09-routing.md) | `RoutingPage.tsx` + tabs |
| 10 | `/warper` | [responsive-10-warper.md](./responsive-10-warper.md) | `WarperPage.tsx` |
| 11 | `/telegram` | [responsive-11-telegram.md](./responsive-11-telegram.md) | `TelegramPage.tsx` |
| 12 | `/antizapret` | [responsive-12-antizapret.md](./responsive-12-antizapret.md) | `AntizapretConfigPage.tsx` |
| 13 | `/edit-files` | [responsive-13-edit-files.md](./responsive-13-edit-files.md) | `EditFilesPage.tsx` |
| 14 | `/server-monitor` | [responsive-14-server-monitor.md](./responsive-14-server-monitor.md) | `ServerMonitorPage.tsx` |
| 15 | `/login` | [responsive-15-login.md](./responsive-15-login.md) | `LoginPage.tsx` |

## Telegram Mini App

Отдельный продукт: см. [tg-miniapp-review.md](./tg-miniapp-review.md) (функциональный аудит).

## Как использовать промпты

1. Выполняйте планы **по номеру** (01 → 15), если не оговорено иное.
2. Откройте файл плана, скопируйте **Prompt 1** из раздела «Промпты».
3. Запустите Agent mode — один промпт = один логический PR.
4. Пройдите чеклист тестирования из того же файла.
5. Отметьте статус в таблице ниже: ⬜ → 🟡 → ✅

## Мастер-промпт

```
Прочитай reviews/responsive-audit-index.md и единые правила проекта.
Исправь адаптивную вёрстку по плану reviews/responsive-NN-<name>.md (номер из рекомендуемого порядка).
Следуй mobile-first: grid-cols-1 по умолчанию, таблицы → карточки на lg:hidden.
Не меняй бизнес-логику и API. Минимальный diff. После правок: npm run build в frontend.
Пройди чеклист тестирования из плана.
```

## Статус выполнения

| # | Файл | Статус |
|---|------|--------|
| 01 | responsive-01-global-shell | ⬜ Не начато |
| 02 | responsive-02-monitoring | ⬜ Не начато |
| 03 | responsive-03-traffic | ⬜ Не начато |
| 04 | responsive-04-logs | ⬜ Не начато |
| 05 | responsive-05-shared-components | ⬜ Не начато |
| 06 | responsive-06-dashboard | ⬜ Не начато |
| 07 | responsive-07-nodes | ⬜ Не начато |
| 08 | responsive-08-settings | ⬜ Не начато |
| 09 | responsive-09-routing | ⬜ Не начато |
| 10 | responsive-10-warper | ⬜ Не начато |
| 11 | responsive-11-telegram | ⬜ Не начато |
| 12 | responsive-12-antizapret | ⬜ Не начато |
| 13 | responsive-13-edit-files | ⬜ Не начато |
| 14 | responsive-14-server-monitor | ⬜ Не начато |
| 15 | responsive-15-login | ⬜ Не начато |

_Обновляйте статус по мере выполнения._
