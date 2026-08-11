# AZ-AWG2 — playbook запуска срезов

Как запускать каждый этап в Cursor: **промпт для чата**, **Superpowers-скиллы**, **MCP**, **команды проверки**.

Эпик: [`specs/2026-08-10-az-awg2-epic.md`](specs/2026-08-10-az-awg2-epic.md)  
Upstream: https://github.com/blindtechnique/az-awg2

---

## 0. Общие правила

1. Идти строго **1a → 1b → 1c → 2a → 2b → 2c → 3a → 3b → 3c → 4a → 4b**. Не прыгать вперёд.  
   Spec 4a/4b: [`specs/2026-08-11-az-awg2-noc-traffic-design.md`](specs/2026-08-11-az-awg2-noc-traffic-design.md).  
2. Один чат / одна сессия = **один срез** (или Subagent-Driven по задачам плана).  
3. Перед кодом агент должен открыть **спек + план** среза.  
4. Коммиты — только если явно попросишь.  
5. UI-имя всегда **AZ-AWG2**, не AZ-WARP.

### Режим выполнения (выбери один в промпте)

| Режим | Когда | Что писать в конце промпта |
|-------|--------|----------------------------|
| **Subagent-Driven** | Рекомендуется для 1b, 2a | `Выполняй через superpowers:subagent-driven-development — отдельный субагент на задачу плана, ревью между задачами.` |
| **Inline** | Мелкие срезы (1a, 1c, 2c) | `Выполняй через superpowers:executing-plans в этой сессии, с чекпоинтами после каждой задачи.` |

### Карта MCP (на весь эпик)

| MCP | Когда звать | Типичные tools |
|-----|-------------|----------------|
| **codebase-memory** | Старт каждого среза | `search_graph`, `search_code`, `get_architecture`, `get_code_snippet` |
| **github** | Upstream CLI/пути | `get_file_contents` owner=`blindtechnique` repo=`az-awg2` |
| **lazyweb** | Срезы с заметным UI (1a shell, 1c Dashboard, 2b/2c вкладки, 3a backup UI) | `lazyweb_search` → потом report только если просишь дизайн-отчёт |
| **context7** | Редко (SSE, FastAPI StreamingResponse, React) | `resolve-library-id`, `query-docs` |
| **cursor-ide-browser** | После `npm run build` / ручной проверки UI | navigate, snapshot, screenshot |
| **siteaudit** | Не нужен для AZ-AWG2 | — |

### Superpowers-скиллы (не MCP)

| Скилл | Когда |
|-------|--------|
| `writing-plans` | Уже сделано для 1–2; для 3a/3b/3c — **до** кода написать plan |
| `subagent-driven-development` | Выполнение плана по задачам |
| `executing-plans` | Выполнение плана в одном чате |
| `test-driven-development` | Если субагент/план требует RED-GREEN |
| `verification-before-completion` | Перед «срез готов» |
| `requesting-code-review` | После толстого среза (1b, 2a) |
| `brainstorming` | Только если меняешь scope спека |

### Команды проверки (шаблон)

```bash
# Backend (из корня репо или backend/)
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_awg2_*.py -q

# Frontend
cd /opt/AdminPanelAZ/frontend && npm run build

# На VPN-узле (ручная проверка слоя, не панели)
awg-client list antizapret
awg show
```

Конкретные pytest-файлы — в таблице среза ниже.

---

## Шаблон промпта (копируй и подставляй)

```text
Реализуй срез AZ-AWG2 {SLICE} строго по спеку и плану.

Спек: docs/superpowers/specs/{SPEC}
План: docs/superpowers/plans/{PLAN}

Правила:
- Не выходить за scope среза (см. «Не цели» в спеке).
- AZ-AWG2 ≠ AZ-WARP; не трогать стоковый AmneziaWG без нужды.
- Сначала прочитай спек + план целиком.
- MCP: в начале — codebase-memory (паттерн Warper/configs) и github (az-awg2 CLI при необходимости).
- UI: если трогаешь страницу/вкладки — lazyweb_search по паттерну «admin VPN settings» / «obfuscation settings» (desktop).
- TDD по шагам плана; в конце — verification-before-completion.
- Коммиты не делать, пока я не попрошу.

{MODE_LINE}

По завершении: кратко что сделано, какие тесты зелёные, что осталось на следующий срез.
```

---

## Срез 1a — shell модуля

| | |
|--|--|
| **Спек** | `docs/superpowers/specs/2026-08-10-az-awg2-wave1a-design.md` |
| **План** | `docs/superpowers/plans/2026-08-10-az-awg2-wave1a.md` |
| **Сниппеты** | `docs/superpowers/plans/2026-08-10-az-awg2.md` (Tasks detect/toggle/shell) |
| **Режим** | Inline OK |

### Промпт

```text
Реализуй срез AZ-AWG2 1a строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave1a-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave1a.md

Правила:
- Только toggle, health/status API, страница /awg2 + install-prompt. Без VpnType/CRUD клиентов.
- Имя UI: AZ-AWG2. Паттерн — WarperInstallPrompt.
- MCP: codebase-memory — как устроены warper toggle/router/Layout; github — README az-awg2 (install command).
- UI shell: lazyweb_search «VPN admin empty state» platform desktop (быстрые референсы).
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:executing-plans в этой сессии, с чекпоинтами после каждой задачи.
```

### MCP / скиллы

- **codebase-memory:** `warper`, `FEATURE_WARPER`, `Layout.tsx` nav  
- **github:** `blindtechnique/az-awg2` `README.md`  
- **lazyweb:** optional search empty/install state  
- Skills: `executing-plans`, TDD по плану

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_awg2_service.py tests/test_awg2_feature_toggle.py tests/test_awg2_api.py -q
cd /opt/AdminPanelAZ/frontend && npm run build
# В UI: FEATURE_AWG2_ENABLED=1 → пункт AZ-AWG2, install-prompt
```

---

## Срез 1b — клиенты + VpnConfig

| | |
|--|--|
| **Спек** | `…-wave1b-design.md` |
| **План** | `…-wave1b.md` |
| **Режим** | **Subagent-Driven** |

### Промпт

```text
Реализуй срез AZ-AWG2 1b строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave1b-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave1b.md
Сниппеты: docs/superpowers/plans/2026-08-10-az-awg2.md (Tasks add/del, configs, HA skip, import)

Правила:
- VpnType.amneziawg2, awg-client add/del оба туннеля + rollback, Clients tab.
- HA replicate для amneziawg2 ЗАПРЕЩЁН (skip + тесты).
- Не делать Dashboard tab (это 1c).
- MCP: codebase-memory — configs.py create/delete, config_import, Warper adapter parity; github — overlay/bin/client-awg.sh.
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:subagent-driven-development — субагент на задачу плана, ревью между задачами.
В конце — superpowers:verification-before-completion.
```

### MCP / скиллы

- **codebase-memory:** `create_config`, `import_clients_from_disk`, `maybe_replicate_create`  
- **github:** `client-awg.sh`, пути clients  
- Skills: `subagent-driven-development`, `test-driven-development`, `verification-before-completion`, optional `requesting-code-review`

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest \
  tests/test_awg2_service.py tests/test_awg2_api.py \
  tests/test_vpn_profile_visibility.py tests/test_awg2_config_import.py -q
# На узле со слоем: создать клиента из /awg2, проверить файлы в /opt/antizapret-awg/clients
```

---

## Срез 1c — Dashboard + docs

| | |
|--|--|
| **Спек** | `…-wave1c-design.md` |
| **План** | `…-wave1c.md` |
| **Режим** | Inline |

### Промпт

```text
Реализуй срез AZ-AWG2 1c строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave1c-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave1c.md

Правила:
- Dashboard: тип AmneziaWG 2.0 отдельно от стокового AmneziaWG; только если toggle + installed.
- docs/awg2.md + ссылки + CHANGELOG. Help: HA будет в 2a.
- MCP: codebase-memory — ConfigCardsSection / ProtocolTab; lazyweb_search «VPN config dashboard tabs» desktop.
- browser — после build проверить create dialog (если стенд доступен).
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:executing-plans.
```

### MCP / скиллы

- **lazyweb:** search dashboard/VPN configs  
- **cursor-ide-browser:** smoke UI  
- Skills: `executing-plans`

### Проверка

```bash
cd /opt/AdminPanelAZ/frontend && npm run build
# Ручной: user с visibility amneziawg2 видит/скачивает конфиг
ls docs/awg2.md
```

---

## Срез 2a — HA crypto-sync

| | |
|--|--|
| **Спек** | `…-wave2a-design.md` |
| **План** | `…-wave2a.md` |
| **Сниппеты** | `…-wave2.md` Tasks 1–3 |
| **Режим** | **Subagent-Driven** |

### Промпт

```text
Реализуй срез AZ-AWG2 2a строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave2a-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave2a.md
Сниппеты: docs/superpowers/plans/2026-08-10-az-awg2-wave2.md (Tasks 1–3)

Правила:
- Archive amneziawg+clients, exclude stats.db; apply_runtime; sync_amneziawg2_state_from_primary.
- Снять HA skip волны 1; инвертировать тесты.
- Replica без слоя → ошибка с install_command.
- MCP: codebase-memory — vpn_state_sync, replicate_client_create, WG archive; github — структура /etc/amnezia/amneziawg.
- Без obfuscation/monitoring UI (2b/2c).
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:subagent-driven-development.
В конце — verification-before-completion и краткий code review запрос.
```

### MCP / скиллы

- **codebase-memory:** `sync_wireguard_state_from_primary`, `export_wireguard_client_profiles_archive`  
- **github:** services.env / overlay paths  
- Skills: `subagent-driven-development`, `verification-before-completion`, `requesting-code-review`

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_awg2_ha_sync.py tests/test_awg2_api.py -q
# HA стенд: create amneziawg2 на primary → файлы на replica
```

---

## Срез 2b — обфускация

| | |
|--|--|
| **Спек** | `…-wave2b-design.md` |
| **План** | `…-wave2b.md` |
| **Режим** | Inline или Subagent |

### Промпт

```text
Реализуй срез AZ-AWG2 2b строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave2b-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave2b.md
Сниппеты: docs/superpowers/plans/2026-08-10-az-awg2-wave2.md (Task 4 + ObfuscationTab)

Правила:
- show / regenerate / apply + regen-all; warning re-import; HA sync best-effort после apply.
- MCP: github — awg-obfuscation.sh флаги; codebase-memory — warper settings tab; lazyweb_search «VPN obfuscation settings» desktop.
- context7 только если нужны детали FastAPI validation.
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:executing-plans (или subagent-driven, если задачи расползутся).
```

### MCP / скиллы

- **github:** `overlay/bin/awg-obfuscation.sh`  
- **lazyweb:** obfuscation/settings UI refs  
- Skills: `executing-plans`

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_awg2_obfuscation.py -q
cd /opt/AdminPanelAZ/frontend && npm run build
```

---

## Срез 2c — мониторинг

| | |
|--|--|
| **Спек** | `…-wave2c-design.md` |
| **План** | `…-wave2c.md` |
| **Режим** | Inline |

### Промпт

```text
Реализуй срез AZ-AWG2 2c строго по спеку и плану.

Спек: docs/superpowers/specs/2026-08-10-az-awg2-wave2c-design.md
План: docs/superpowers/plans/2026-08-10-az-awg2-wave2c.md
Сниппеты: docs/superpowers/plans/2026-08-10-az-awg2-wave2.md (Tasks 5–7)

Правила:
- GET /monitoring: overview или fallback awg show dump; без deep client/geo (3c).
- MCP: github — awg_stats.py overview; codebase-memory — Warper MonitoringTab; lazyweb_search «VPN peer monitoring table» desktop.
- browser — smoke вкладки после build.
- Коммиты не делать, пока не попрошу.

Выполняй через superpowers:executing-plans + verification-before-completion.
```

### MCP / скиллы

- **github:** `overlay/bin/awg_stats.py`  
- **lazyweb** + **browser**  
- Skills: `executing-plans`, `verification-before-completion`

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest tests/test_awg2_monitoring.py -q
cd /opt/AdminPanelAZ/frontend && npm run build
```

---

## Срез 3a — install SSE, TTL, узкий backup

| | |
|--|--|
| **Спек** | `…-wave3a-design.md` |
| **План** | сначала написать: `docs/superpowers/plans/2026-08-10-az-awg2-wave3a.md` |
| **Режим** | Сначала brainstorming/writing-plans, потом Subagent |

### Промпт A — план

```text
По спеку docs/superpowers/specs/2026-08-10-az-awg2-wave3a-design.md
напиши implementation plan через superpowers:writing-plans в
docs/superpowers/plans/2026-08-10-az-awg2-wave3a.md.
Образец стрима — Warper /warper/updates/stream.
Не пиши код.
```

### Промпт B — код

```text
Реализуй срез AZ-AWG2 3a по
docs/superpowers/specs/2026-08-10-az-awg2-wave3a-design.md
и docs/superpowers/plans/2026-08-10-az-awg2-wave3a.md.

Правила:
- SSE install/update; без --install-base/reboot orchestration.
- TTL + expires_at; узкий backup (не полный awg-backup).
- MCP: codebase-memory — warper updates stream; github — install.sh flags, expiry.tsv, awg-backup.sh (что НЕ копировать); lazyweb — backup/settings admin UI.
- Subagent-driven-development.
```

### Проверка (ориентир)

```bash
# pytest по новым test_awg2_install / ttl / backup когда появятся
cd /opt/AdminPanelAZ/frontend && npm run build
```

---

## Срез 3b — Telegram + Mini App

| | |
|--|--|
| **Спек** | `…-wave3b-design.md` |
| **План** | написать `…-wave3b.md` перед кодом |

### Промпт A — план

```text
По docs/superpowers/specs/2026-08-10-az-awg2-wave3b-design.md
напиши plan через writing-plans → docs/superpowers/plans/2026-08-10-az-awg2-wave3b.md.
Образец: telegram warper_status + tg-mini Warper page. Не пиши код.
```

### Промпт B — код

```text
Реализуй 3b по спеку и плану wave3b.
MCP: codebase-memory — warper_status, tg-mini Warper/Configs; без lazyweb-отчёта обязательно (можно search).
Не дублировать install/обфускацию в боте.
```

---

## Срез 3c — block + deep stats

| | |
|--|--|
| **Спек** | `…-wave3c-design.md` |
| **План** | написать `…-wave3c.md` перед кодом |

### Промпт A — план

```text
По docs/superpowers/specs/2026-08-10-az-awg2-wave3c-design.md
напиши plan через writing-plans → docs/superpowers/plans/2026-08-10-az-awg2-wave3c.md.
Образец: wg_runtime + client-access wireguard + geoip_local. Не пиши код.
```

### Промпт B — код

```text
Реализуй 3c по спеку и плану.
MCP: codebase-memory — wg_runtime, access_policy, lookup_geo_local; github — awg set / conf peers.
Отдельная policy от стокового WG. Subagent-driven.
```

---

## Срез 4a — NOC + connection-history + TG

| | |
|--|--|
| **Спек** | `docs/superpowers/specs/2026-08-11-az-awg2-noc-traffic-design.md` §4a |
| **План** | `docs/superpowers/plans/2026-08-11-az-awg2-wave4a.md` |
| **Режим** | **Subagent-Driven** |
| **Next** | 4b — traffic collector + limits (реализован) |

### Промпт

```text
Реализуй срез AZ-AWG2 4a строго по спеку §4a и плану.

Спек: docs/superpowers/specs/2026-08-11-az-awg2-noc-traffic-design.md
План: docs/superpowers/plans/2026-08-11-az-awg2-wave4a.md

Правила:
- Только NOC overview, connection-history, TG NOC text/PNG. Без traffic collector/limits (это 4b).
- Третий протокол amneziawg2 — не вливать в wireguard_peers / protocol_type=wireguard.
- Toggle FEATURE_AWG2_ENABLED; not installed / adapter error → пустые peers, без 500.
- MCP: codebase-memory — monitoring_overview, connection_history, noc_report; github при необходимости.
- Коммиты — по SDD / явной просьбе.

Выполняй через superpowers:subagent-driven-development — субагент на задачу плана, ревью между задачами.
```

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest \
  tests/test_awg2_noc.py tests/test_noc_report_awg2.py \
  tests/test_connection_history*.py -q -k awg2
cd /opt/AdminPanelAZ/frontend && npm run build
# UI: awg2 on → фильтр/KPI/серия AWG 2.0; awg2 off → как pre-4a
```

---

## Срез 4b — Traffic monitoring + limits

| | |
|--|--|
| **Спек** | `docs/superpowers/specs/2026-08-11-az-awg2-noc-traffic-design.md` §4b |
| **План** | `docs/superpowers/plans/2026-08-11-az-awg2-wave4b.md` |
| **Режим** | **Subagent-Driven** |
| **Next** | — (эпик 1a–4b закрыт по критериям) |

### Промпт

```text
Реализуй срез AZ-AWG2 4b строго по спеку §4b и плану.

Спек: docs/superpowers/specs/2026-08-11-az-awg2-noc-traffic-design.md
План: docs/superpowers/plans/2026-08-11-az-awg2-wave4b.md

Правила:
- Только traffic collector/chart/reset/HA aggregate + limits/auto-block + UI TrafficPage/ClientActionsDialog.
- protocol_type=amneziawg2; никогда не писать AWG2 как wireguard.
- Gates: FEATURE_AWG2_ENABLED + traffic monitoring; off → нет новых samples / нет UI третьего протокола.
- MCP: codebase-memory — traffic collector, access_policy, client_access; github при необходимости.
- Коммиты — по SDD / явной просьбе.

Выполняй через superpowers:subagent-driven-development — субагент на задачу плана, ревью между задачами.
```

### Проверка

```bash
cd /opt/AdminPanelAZ/backend && PYTHONPATH=. .venv/bin/pytest \
  tests/test_traffic_awg2_collector.py tests/test_traffic_awg2_scopes.py \
  tests/test_awg2_traffic_limit.py tests/test_awg2_traffic_limit_api.py -q
cd /opt/AdminPanelAZ/frontend && npm run build
# UI: awg2+traffic on → бейдж/сброс/серия AWG 2.0 + set/clear limit; off → как pre-4b
```

---

## Чеклист «срез закрыт»

- [ ] Все tasks плана `[x]` или явно отложены  
- [ ] Pytest среза зелёный  
- [ ] `npm run build` OK если трогали frontend  
- [ ] Scope не расползся на следующий срез  
- [ ] (Опционально) commit + push по твоей просьбе  

---

## Быстрый указатель файлов

```
docs/superpowers/
├── AZ-AWG2-EXECUTION-PLAYBOOK.md    ← этот файл
├── specs/
│   ├── 2026-08-10-az-awg2-epic.md
│   ├── 2026-08-10-az-awg2-wave1a-design.md … wave3c-design.md
│   ├── 2026-08-11-az-awg2-noc-traffic-design.md  (4a/4b)
│   └── …
└── plans/
    ├── 2026-08-10-az-awg2-wave1a.md … wave3c.md
    ├── 2026-08-11-az-awg2-wave4a.md
    ├── 2026-08-11-az-awg2-wave4b.md
    ├── 2026-08-10-az-awg2.md          (сниппеты волны 1)
    └── 2026-08-10-az-awg2-wave2.md    (сниппеты волны 2)
```

## Старт прямо сейчас

Срезы **1a–4b** закрыты по планам. Для регрессий / hotfix копируй промпт нужного среза в новый Agent-чат (режим Agent, не Ask).
