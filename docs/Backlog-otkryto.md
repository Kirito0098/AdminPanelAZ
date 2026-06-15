# Открытый backlog (◐ частично · ⬜ не начато)

> Задачи roadmap, которые ещё не закрыты полностью.  
> **Полный план:** [Idei.md](Idei.md) · **Промпты:** [Etapy-prompty.md](Etapy-prompty.md) · **Актуализация:** 2026-06-16

| Метка | Значение |
|-------|----------|
| ◐ | База в коде есть; не весь DoD или нужна ручная настройка |
| ⬜ | В коде нет (или только задел) |

---

## Сводка

| ID | Задача | Этап | P | Статус |
|----|--------|------|---|--------|
| 3.4 | Политики per-node (лимиты EU vs RU) | 3 | P2 | ◐ |
| 5.6 | HA в Dashboard и **NOC** | 5 | P2 | ◐ |
| 7.1 | Локальная GeoIP БД | 7 | P1 | ◐ |
| 7.3 | Правила алертов | 7 | P2 | ⬜ |
| 7.4 | Отчёты PDF (weekly) | 7 | P2 | ⬜ |
| 9.1 | CSP hardening (без `unsafe-inline` в styles) | 9 | P2 | ◐ |
| 9.4 | Secrets rotation UI | 9 | P3 | ⬜ |
| 10.1 | PostgreSQL вместо SQLite | 10 | P3 | ⬜ |
| 10.2 | Полноценный i18n (RU + EN) | 10 | P3 | ◐ |
| 10.3 | Plugin / hook architecture | 10 | P3 | ⬜ |
| 10.4 | Inline-режим Telegram-бота | 10 | P3 | ⬜ |

**Этапы с открытыми пунктами:** 5 ◐ · 7 ◐ · 9 ◐ · 10 ⬜

---

## Рекомендуемый порядок

1. **7.3** — правила алертов (P2, высокая ops-ценность, опора на Prometheus + AdminNotify)
2. **5.6** — NOC: агрегация online по HA sync group
3. **7.1** — onboarding MMDB + статус в UI (закрыть DoD «NOC без ip-api»)
4. **9.1** — убрать `style-src 'unsafe-inline'` где возможно
5. **9.4** — wizard rotation секретов (перед публичным prod)
6. **10.1** — PostgreSQL (когда появится «database is locked»)
7. Остальное по боли: **10.2** i18n · **7.4** PDF · **3.4** wizard лимитов · **10.3** / **10.4**

---

## ◐ Частично реализовано

### 3.4 — Политики per-node (EU vs RU) · P2

| | |
|---|---|
| **Этап** | 3 Multi-node |
| **Уже есть** | `OpenVpnAccessPolicy` / `WgAccessPolicy` scoped by `node_id`; сводка [`NodePolicySummarySection`](../frontend/src/components/nodes/NodePolicySummarySection.tsx) на странице узлов |
| **Не хватает** | UI wizard: задать **разные дефолтные лимиты/маршруты** per-node (не только просмотр агрегата) |
| **DoD** | Админ задаёт политику «EU node» vs «RU node» без правки БД вручную |

---

### 5.6 — HA в Dashboard и NOC · P2

| | |
|---|---|
| **Этап** | 5 Node Sync / HA |
| **Уже есть** | HA badge на [`ConfigCard`](../frontend/src/components/dashboard/ConfigCard.tsx); dedup linked configs (`ha_primary_config_id`); auto-sync + reconcile — [`NodeSync.md`](NodeSync.md) |
| **Не хватает** | **NOC / federated monitoring:** одна logical строка на HA-клиента; online «на любом узле группы», не дубли по `node_id` |
| **Промпт** | [Etapy-prompty.md § 5.6](Etapy-prompty.md#этап-5--node-sync--ha--частично) |
| **Файлы для правок** | `monitoring_overview.py`, `build_federated_monitoring_overview`, `MonitoringPage` |

---

### 7.1 — Локальная GeoIP БД · P1

| | |
|---|---|
| **Этап** | 7 Мониторинг |
| **Уже есть** | [`geoip_local.py`](../backend/app/services/geoip_local.py), интеграция в `ip_geo.py`, пути в `config.py` (`data/geoip/GeoLite2-City.mmdb`, ASN) |
| **Не хватает** | Док/onboarding: как скачать MMDB; индикатор в UI «loaded / fallback ip-api»; DoD «NOC без ip-api» только после загрузки файлов |
| **Промпт** | [Etapy-prompty.md § 7.1 MMDB](Etapy-prompty.md#промпт--доработка-71-mmdb-onboarding) |
| **Проверка** | `pytest tests/test_ip_geo.py`; NOC при недоступном ip-api + наличие MMDB |

---

### 9.1 — CSP hardening · P2

| | |
|---|---|
| **Этап** | 9 Security |
| **Уже есть** | Nonce для `script-src` — [`http_security.py`](../backend/app/middleware/http_security.py), [`html_csp.py`](../backend/app/services/html_csp.py), Vite placeholder; тесты `test_http_security.py` |
| **Не хватает** | DoD: **`style-src 'unsafe-inline'`** всё ещё в дефолтном CSP (`config.py`); нужен audit inline styles во frontend |
| **Промпт** | [Etapy-prompty.md § 9.1 CSP styles](Etapy-prompty.md#промпт--доработка-91-csp-styles) |

---

### 10.2 — Полноценный i18n (RU + EN) · P3

| | |
|---|---|
| **Этап** | 10 Масштаб |
| **Уже есть** | [`telegram_bot_i18n.py`](../backend/app/services/telegram_bot_i18n.py) — строки бота |
| **Не хватает** | `react-i18next` (или аналог) для веб-панели; переключатель locale; EN для Settings/Dashboard/TG согласованно |
| **DoD** | EN locale для **web + bot** — см. [Idei.md §10](Idei.md#этап-10--масштаб-и-экосистема) |

---

## ⬜ Не начато

### 7.3 — Правила алертов · P2

**Что нужно:** модель `AlertRule` (порог, метрика/агрегат, cooldown) · worker на Prometheus/DB · AdminNotify · UI Settings → Monitoring.

**Промпт:** [Etapy-prompty.md § 7.3](Etapy-prompty.md#промпт--реализация-73-alert-rules)

**DoD этапа 7:** кастомные пороги типа «>50 OVPN online», «узел offline >5 min».

---

### 7.4 — Отчёты PDF (weekly) · P2

**Что нужно:** генерация PDF/TG weekly: top clients, инциденты, CIDR failures (отдельно от **7.2** TG text summary — [`noc_report.py`](../backend/app/services/noc_report.py) уже есть).

**Примечание:** ежедневная/еженедельная **TG-сводка NOC** — ✅ реализована (7.2).

---

### 9.4 — Secrets rotation UI · P3

**Что нужно:** guided wizard: `SECRET_KEY`, API keys, TG token; предупреждение re-login после смены JWT secret.

**Сейчас:** rotation только вручную через `.env` / SECURITY.md.

---

### 10.1 — PostgreSQL вместо SQLite · P3

**Когда:** «database is locked», несколько инстансов панели, высокая write-нагрузка samples.

**Нужно:** Plan → `DATABASE_URL`, миграции, dual-support или one-way, docs, CI job.

**Промпт:** [Etapy-prompty.md § 10 Plan](Etapy-prompty.md#подготовка-plan)

---

### 10.3 — Plugin / hook architecture · P3

**Что нужно:** минимальный registry расширений (notify backends и т.п.) без over-engineering.

**Сейчас:** нет отдельного plugin layer.

---

### 10.4 — Inline-режим Telegram-бота · P3

**Что нужно:** `@bot query` → отправка ссылки/конфига; TTL-кэш inline results.

**Сейчас:** только command handlers + Mini App.

---

## Открытые DoD (частичные этапы)

### Этап 5
- [~] NOC: federated overview агрегирует online по **NodeSyncGroup**, не по каждому `node_id`

### Этап 7
- [~] NOC стабилен **без ip-api.com** — только при загруженных MMDB
- [ ] Кастомные правила алертов (7.3)
- [ ] PDF weekly reports (7.4)

### Этап 9
- [~] CSP без `'unsafe-inline'` на **основных** страницах (scripts — ok)
- [ ] Secrets rotation UI (9.4)

### Этап 10
- [ ] SQLite → PostgreSQL документирован и работает
- [~] EN locale web + bot
- [ ] Plugin hooks
- [ ] Inline bot

---

## Как обновлять

1. После закрытия задачи — убери строку из этого файла (или пометь ✅ с датой).
2. Синхронизируй [Idei.md](Idei.md) (таблица этапов, матрица, каталог §1–§11).
3. Обнови [Etapy-prompty.md](Etapy-prompty.md) § «Статус реализации».
4. Если задача полностью закрыла этап — отметь этап ✅ в Idei.md.

---

*Связано: [Idei.md](Idei.md) · [Etapy-prompty.md](Etapy-prompty.md) · [NodeSync.md](NodeSync.md) · [PROJECT_MAP.md](PROJECT_MAP.md)*
