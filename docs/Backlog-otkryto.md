# Открытый backlog (◐ частично · ⬜ не начато)

> Задачи roadmap, которые ещё не закрыты полностью.  
> **Полный план:** [Idei.md](Idei.md) · **Промпты:** [Etapy-prompty.md](Etapy-prompty.md) · **Актуализация:** 2026-06-16

| Метка | Значение |
|-------|----------|
| ◐ | База в коде есть; не весь DoD или нужна ручная настройка |
| ⬜ | В коде нет (или только задел) |

---

## Сводка

| ID | Задача | Этап | P | Шаг | Статус |
|----|--------|------|---|-----|--------|
| 10.1 | PostgreSQL вместо SQLite | 10 | P3 | 6 | ⬜ |
| 10.2 | Полноценный i18n (RU + EN) | 10 | P3 | 7a | ◐ |

**Этапы с открытыми пунктами:** 10 ◐

---

## Порядок наилучшего выполнения

**Принципы:** ops-ценность → закрытие частичных DoD → security перед prod → масштаб по боли.

**Перед любым промптом** добавь суффикс Agent из [Etapy-prompty.md § Режимы](Etapy-prompty.md#режимы-cursor).

| Шаг | ID | Режим | Зависимости | Почему сейчас |
|-----|-----|-------|-------------|-------------|
| 1 | **10.1** | Plan → Agent | при «database is locked» | Не делать преждевременно; SQLite ок для single-instance |
| 2 | **10.2** | Plan → Agent | — | i18n бота ◐; веб — отдельный большой PR |

**Треки:** SQLite bottleneck → **10.1** · EN locale для web → **10.2** (по страницам, один PR за экран).

### Быстрые промпты (копировать в Agent)

| ID | Промпт |
|----|--------|
| **10.1** | `Спланируй миграцию AdminPanelAZ SQLite → PostgreSQL: database_url, cidr_database отдельно?, sqlalchemy migrations, dual-support или one-way, docs, CI job. Верни план без кода.` → затем Agent по плану |
| **10.2** | `Полноценный i18n RU+EN: react-i18next (или аналог) для веб-панели; переключатель locale; согласовать с telegram_bot_i18n.py. EN для Settings/Dashboard/TG. Одна подзадача за PR.` |

---

## ◐ Частично реализовано

### 10.2 — Полноценный i18n (RU + EN) · P3

| | |
|---|---|
| **Этап** | 10 Масштаб |
| **Уже есть** | [`telegram_bot_i18n.py`](../backend/app/services/telegram_bot_i18n.py) — строки бота |
| **Не хватает** | `react-i18next` (или аналог) для веб-панели; переключатель locale; EN для Settings/Dashboard/TG согласованно |
| **DoD** | EN locale для **web + bot** — см. [Idei.md §10](Idei.md#этап-10--масштаб-и-экосистема) |
| **Режим** | Plan → Agent |
| **Промпт (Plan)** | `Спланируй i18n AdminPanelAZ: react-i18next структура ключей, locale switcher, согласование с telegram_bot_i18n.py. Порядок: Settings → Dashboard → остальное. Без кода.` |
| **Промпт (Agent)** | `Полноценный i18n RU+EN: react-i18next для веб-панели; переключатель locale; согласовать с telegram_bot_i18n.py. EN для Settings/Dashboard/TG. Одна страница за PR.` |
| **Проверка** | `npm run build` · toggle locale в UI · bot EN strings |

---

## ⬜ Не начато

### 10.1 — PostgreSQL вместо SQLite · P3

**Когда:** «database is locked», несколько инстансов панели, высокая write-нагрузка samples.

**Нужно:** Plan → `DATABASE_URL`, миграции, dual-support или one-way, docs, CI job.

**Режим:** Plan → Agent (не делать преждевременно)

**Промпт (Plan):** `Спланируй миграцию AdminPanelAZ SQLite → PostgreSQL: database_url, cidr_database отдельно?, sqlalchemy migrations, dual-support или one-way, docs, CI job. Backward compat dev on sqlite. Без кода.`

**Промпт (Agent):** `Реализуй PostgreSQL support (Idei.md 10.1) по плану: config DATABASE_URL, миграции, keep sqlite default dev, docs, CI job. Одна подзадача за PR.`

**Промпт:** [Etapy-prompty.md § 10 Plan](Etapy-prompty.md#подготовка-plan)

**Проверка:** `DATABASE_URL=postgresql://... pytest` · docker-compose optional

---

## Закрыто (2026-06-16)

| ID | Задача | Этап |
|----|--------|------|
| 3.4 | Политики per-node (лимиты EU vs RU) | 3 |
| 5.6 | HA в Dashboard и **NOC** | 5 |
| 7.1 | Локальная GeoIP БД (onboarding) | 7 |
| 7.3 | Правила алертов | 7 |
| 7.4 | Отчёты PDF (weekly) | 7 |
| 9.1 | CSP hardening (без `unsafe-inline` в styles) | 9 |
| 9.4 | Secrets rotation UI | 9 |
| 10.3 | Plugin / hook architecture | 10 |
| 10.4 | Inline-режим Telegram-бота | 10 |

---

## Открытые DoD (частичные этапы)

### Этап 10
- [ ] SQLite → PostgreSQL документирован и работает
- [~] EN locale web + bot — словарь бота ✅; веб-панель без react-i18next

---

## Как обновлять

1. После закрытия задачи — убери строку из этого файла (или пометь ✅ с датой).
2. Синхронизируй [Idei.md](Idei.md) (таблица этапов, матрица, каталог §1–§11).
3. Обнови [Etapy-prompty.md](Etapy-prompty.md) § «Статус реализации».
4. Если задача полностью закрыла этап — отметь этап ✅ в Idei.md.
5. При добавлении новой задачи — укажи **Шаг**, **Режим**, **Промпт (Agent)** и **Проверка** по шаблону выше.

---

*Связано: [Idei.md](Idei.md) · [Etapy-prompty.md](Etapy-prompty.md) · [NodeSync.md](NodeSync.md) · [PROJECT_MAP.md](PROJECT_MAP.md)*
