# AZ-AWG2 — UX/UI выравнивание с AZ-WARP + denser clients

**Дата:** 2026-08-12  
**Статус:** approved  
**Эпик:** [`2026-08-10-az-awg2-epic.md`](2026-08-10-az-awg2-epic.md)  
**Образец UI:** AZ-WARP (`WarperPage`, `WarperHero`, `OverviewCards`) + denser cards как Dashboard `ConfigCard`  
**Исследование:** Lazyweb improve report — [Improve AZ-AWG2 UX quality](https://www.lazyweb.com/report/lazyweb/1dfb8386-7584-40ef-b6f3-deda5565a68f/?source=create)  
**Выбор владельца:** вариант **C** (WARP-shell + denser clients), реализация **вариант 1** (не reuse `ConfigCard` as-is, не full master-detail)

## Цель

Поднять UX/UI вкладки `/awg2` до уровня соседнего модуля AZ-WARP: явная иерархия статуса, overview-метрики, компактный ops chrome, мобильные tabs, менее шумный список клиентов — **без новых backend-возможностей**.

## Решения

| Тема | Выбор |
|------|--------|
| Направление | C: WARP-shell + denser clients |
| Реализация shell | Вынести `Awg2Hero` + `Awg2OverviewCards` по образцу warper |
| Layer info | Убрать толстый блок «Слой на узле»; заменить dashed strip (как fake-subnet у WARP) |
| Клиенты | Оставить card grid + `Awg2ClientStatsSheet`; уплотнить layout, убрать дублирующий page-level header вкладки |
| Master-detail Lazyweb | **Не** в этой итерации (YAGNI; другой паттерн vs WARP/Dashboard) |
| `ConfigCard` Dashboard | **Не** подключать as-is (лишние протоколы/фильтры); копировать только denser visual rhythm |
| API / фичи | Без новых эндпоинтов; только существующие `health` / `status` / configs |

## Не цели

- Split-view «Инспектор клиента» (Lazyweb hypothesis #1)
- Ops rail справа (Lazyweb #2)
- Редизайн Obfuscation / Monitoring / Backup / Help по сути
- Изменения Dashboard / AZ-WARP / Telegram Mini
- Новые API, поля health/status, feature flags
- Фильтры/поиск клиентов уровня Dashboard (можно позже)

## Текущие проблемы (as-is)

1. Hero и status уже есть, но **inline** в `Awg2Page` — нет parity с `WarperHero`.
2. Нет **OverviewCards** — нет быстрых кликов в вкладки / метрик наверху.
3. Блок «Слой на узле» дублирует то, что лучше смотрится как strip + overview.
4. Вкладка Clients повторяет крупный заголовок модуля и раздувает карточки (много вертикального воздуха, действия растянуты).
5. `TabsList` без scroll/snap как у WARP — хуже на узких экранах.

## Архитектура UI

```
Awg2Page
├── Awg2Hero (status, node, refresh, update-layer)
├── loadError alert (или тонкий Awg2Alerts)
├── Awg2InstallPrompt          // если !installed
└── ready:
    ├── Awg2OverviewCards      // 4 cards → navigate tabs + dashed layer strip внутри (как WARP)
    └── Tabs (clients | obfuscation | monitoring | backup | help)
        └── ClientsTab (toolbar + form + denser cards)
```

Файлы (ожидаемые):

| Файл | Роль |
|------|------|
| `frontend/src/pages/Awg2Page.tsx` | Сборка shell как `WarperPage` |
| `frontend/src/components/awg2/Awg2Hero.tsx` | **new** — hero |
| `frontend/src/components/awg2/Awg2OverviewCards.tsx` | **new** — 4 metric cards + dashed layer strip (как `OverviewCards` + fake-subnet у WARP) |
| `frontend/src/components/awg2/ClientsTab.tsx` | denser chrome + cards |
| `frontend/src/components/awg2/utils.ts` | при необходимости helpers для labels |

Опционально: `Awg2Alerts.tsx` если error/conflict разрастётся; иначе оставить inline alert как сейчас.

## Секция 1 — Shell

### Awg2Hero

Зеркало `WarperHero` с отличиями AWG2:

- Иконка `Shield`, заголовок **AZ-AWG2**
- Badge статуса: Нет данных / Не установлен / Установлен (как текущий `statusMeta`)
- Подпись узла через `formatAwg2NodeLabel`
- Кнопки: **Обновить** + при `installed` — `Awg2InstallDialog` mode=`update` («Обновить слой»)
- Без power-toggle (у AWG2 нет `postWarperToggle`-аналога в UI)

### Awg2OverviewCards

Сетка `1 → 2 → 4` колонок (`sm`/`xl`), `border-l-4`, click → `setTab`:

| Card | Value | Navigate |
|------|-------|----------|
| Состояние | Установлен / Не установлен | `monitoring` или остаётся на текущей (предпочтительно `help` не трогать; → `monitoring`) |
| Клиенты | `status.client_counts.vpn` (fallback: `antizapret`, иначе «—» до загрузки списка) | `clients` |
| AntiZapret | `AZ_IFACE` · `AZ_PORT` (mono, короткий) | `obfuscation` или `monitoring` — **решение: `monitoring`** |
| VPN | `VPN_IFACE` · `VPN_PORT` | `clients` |

Данные только из уже загружаемых `health` + `status` на странице. Не делать отдельный fetch ради карточек.

Loading: 4 skeleton-карточки как у WARP.

### Layer strip (внутри `Awg2OverviewCards`)

Dashed `Card` под сеткой метрик (тот же приём, что fake-subnet в `warper/OverviewCards`):

- Показать доступные из `services_env`: `AZ_SUBNET`, `VPN_SUBNET`; если subnet нет — iface/port одной строкой
- Одна короткая hint-строка: клиенты / обфускация / backup во вкладках; install-base — SSH
- **Не** дублировать кнопку «Обновить слой» (она только в Hero)
- Отдельный файл `Awg2LayerStrip.tsx` **не** создавать

Удалить текущий толстый блок «Слой на узле» из `Awg2Page`.

### Tabs

Скопировать классы scroll/snap с `WarperPage` `TabsList` / `TabsTrigger` (короткие label на `sm:hidden` где нужно: Монит. / Справка можно оставить полными если влезает).

Порядок вкладок **без изменений**: clients → obfuscation → monitoring → backup → help.

## Секция 2 — Clients denser

### Toolbar

- Убрать крупный блок с иконкой Shield + H2 «Клиенты AZ-AWG2» + длинным описанием
- Заменить на компактную полосу: заголовок `Клиенты` + badge count | справа: grid-cols dropdown + Обновить
- Опционально одна строка `text-xs text-muted-foreground` вместо абзаца

### Create form

- Сохранить поля и валидацию
- Чуть плотнее padding (`p-3` вместо `p-4` где уместно), без смены API

### Client cards

Сохранить grid + `gridCols` localStorage key `awg2-clients:gridCols`.

Уплотнить карточку:

1. Header: имя + badges (AWG2 / VPN / AZ / block state) + delete — в одну линию
2. Meta: описание / создан / cert days — компактный `text-xs` block (меньше gap)
3. Primary actions: VPN + AntiZapret download — footer buttons
4. Secondary: Статистика + block/unblock — в одну строку или `DropdownMenu` «Ещё», чтобы не раздувать высоту
5. Сохранить confirm dialogs и `Awg2ClientStatsSheet`

Не менять бизнес-логику create/delete/block/download.

## Визуальный язык

- Существующий shadcn + tailwind панели (dark ops, primary teal)
- Не вводить marketing hero, purple gradients, новые шрифты
- Motion только существующие (`animate-spin` на refresh) — без новых анимаций ради эффекта

## Критерии готовности

1. `/awg2` при установленном слое визуально рифмуется с `/warper`: Hero → Overview → strip → Tabs.
2. Толстый «Слой на узле» отсутствует; параметры доступны в overview/strip.
3. Overview cards кликабельны и ведут на вкладки из таблицы выше.
4. Clients: нет дублирующего module-header; карточки заметно ниже по высоте при тех же действиях.
5. Tabs горизонтально скроллятся на узкой ширине без поломки layout.
6. Install-prompt путь (`!installed`) не регрессирует.
7. Нет новых API; существующие тесты backend не требуют правок из-за этого UI-среза (frontend visual — ручная проверка / при наличии — существующие unit на utils).

## Риски и смягчение

| Риск | Смягчение |
|------|-----------|
| `client_counts` пустой на части узлов | Показывать «—»; после load ClientsTab count не обязан синхронизировать overview в v1 (допустимо; опционально прокинуть count вверх позже) |
| Перегрузка Hero кнопками | Только refresh + update-layer |
| Слишком агрессивный densify ломает touch targets | Минимальная высота кнопок как у shadcn `size="sm"`; не уходить в icon-only без title |

## План после утверждения файла

1. Spec self-review (этот файл).  
2. Ревью владельцем.  
3. `writing-plans` → `docs/superpowers/plans/2026-08-12-az-awg2-ux-ui.md`.  
4. Реализация по плану.
