# Node link diagnostics + Push full UX

**Дата:** 2026-09-13  
**Статус:** implemented  
**Ветка:** `feature/client-portal`  
**Подход:** вариант **A** — диагностический слой (health 1.8.0 + meta панели) + единый классификатор ошибок адаптера + UX Push full без смены wipe-логики

## Контекст

Панель связывается с VPN/proxy узлами через `LocalNodeAdapter` (in-process) или `RemoteNodeAdapter` / `ProxyNodeAdapter` (HTTP(S) + `X-Node-Key`). Health опрашивает `node_health_worker`; HA sync primary→replica идёт через Push full (wipe-and-replace).

Известные боли:

1. Ошибки агента (401/403, SSL `WRONG_VERSION_NUMBER`) местами выглядят как «сессия панели» или сырой traceback.  
2. Карточка узла мало говорит о **связи**: ключ, TLS ожидание vs факт, последний успешный health, последняя ошибка.  
3. Push full — высокий blast radius; админу сложно понять **на каком шаге/реплике** упало и что чинить.

Подписка/портал **не** зависят от новых API агента и вне скоупа этого spec.

## Решения brainstorm

| Тема | Выбор |
|------|--------|
| Приоритеты | Надёжность связи + HA Push full UX + диагностика |
| Горизонт | P0 + UX Push full (не deep HA redesign) |
| Агент | Панель + лёгкие поля `/health` → **1.8.0** |
| Подход | **A** — diagnostic layer |

## §1. Архитектура

```text
Nodes UI ──► RemoteAdapter ──X-Node-Key──► GET /health (agent 1.8.0)
     ▲              │
     │              ▼
node_health_worker  classify errors → last_link_error / last_health_ok_at
Push full task ──► same adapter + progress phases + replica summary
```

- **Источник правды о связи:** ответ `/health` + результат последнего опроса (meta на панели).  
- **Агент 1.8.0** расширяет payload, **без** нового route.  
- **Адаптер** классифицирует ошибки в стабильные коды → UI и Push full показывают одно и то же.  
- **Push full:** логика wipe/restore **без изменений**; только префлайт, прогресс, итог, post-success health refresh.

## §2. Диагностика (health + карточка)

### Agent `NODE_AGENT_VERSION = 1.8.0`

Расширить `build_health_payload` в `backend/app/services/node_health.py` (используется vpn `node_agent`):

| Поле | Тип | Смысл |
|------|-----|--------|
| `agent_version` | str | как сейчас |
| `started_at` | str ISO UTC | старт процесса агента |
| `uptime_sec` | int | секунды с старта |
| `listen_tls` | bool | агент реально слушает TLS |

Proxy agent: зеркально, если есть сопоставимый health payload; иначе только vpn в P0 с note в CHANGELOG.

### Panel meta (пишет health-worker / manual check)

| Поле | Смысл |
|------|--------|
| `last_health_ok_at` | ISO UTC последнего успешного health |
| `last_link_error` | `{ code, message, at }` или null после успеха |
| `expected_tls` | bool из настроек узла (`mtls_enabled` / URL scheme) |
| `tls_mismatch` | true если health ok и `expected_tls != listen_tls` |

### UI

Блок **«Связь»** на карточке/деталях узла: online, версия, TLS (ожидание vs факт), uptime, «здоров X назад», при ошибке — код + короткое действие.

Кнопка **«Проверить связь»** — синхронный health сейчас, без ожидания воркера.

Старые агенты (&lt;1.8): отсутствующие поля → «—» / подсказка обновить агент; online/version как сейчас.

## §3. Auth / классификатор ошибок

Единый helper (vpn + proxy remote):

| Код | Когда | HTTP к UI | Смысл для админа |
|-----|--------|-----------|------------------|
| `node_auth` | агент 401/403 | **502** | Неверный API-ключ или IP allowlist |
| `node_tls_mismatch` | SSL wrong version / scheme | 502 | HTTP↔HTTPS / mTLS рассинхрон |
| `node_unreachable` | connect refused / DNS | 502 | Узел недоступен |
| `node_timeout` | timeout | 504 | Таймаут связи |
| `node_error` | прочее | 502 | Ошибка агента + короткий detail |

- Все remote-вызовы через один map — нельзя забыть call site.  
- FE: распознавать `code` / стабильный префикс; **не** logout на `node_auth`.  
- Health-worker: при ошибке пишет `last_link_error`; offline как сейчас для unreachable/auth, но код разный.  
- Без сложного debounce ложного offline в P0 — опираемся на `last_health_ok_at`.

## §4. Push full UX

**Не меняем:** wipe-and-replace, порядок шагов, continue-on-error.

**Меняем:**

1. **Префлайт** — health primary + replicas; `node_auth` / `node_tls_mismatch` → жёсткий блок; unreachable → warning с confirm (или блок — выбрать **блок для auth/tls, warning+confirm для unreachable**).  
2. **Прогресс** `node_sync_push_full` — фазы: `backup_primary` → `restore_replica` → `hosts` → `profiles` → `prune` → `restart_apply` → `verify`; в detail: replica id/name + шаг.  
3. **Итог** — сводка по репликам `ok`/`failed` + шаг + hint из классификатора.  
4. **После успеха** — force health-poll затронутых узлов (анти false drift).

## §5. Тесты и критерии готовности

**Backend:** health fields; classifier mapping; worker meta; Push full preflight/progress/summary/refresh (mocks).  
**Frontend:** блок «Связь»; `node_auth` не logout; Push full фазы/сводка по fixture.  

**Готово когда:** агент 1.8.0 в README/CHANGELOG; graceful degrade на старых агентах; существующие `test_node_sync_push_full*` без регрессии wipe-логики.

## Вне скоупа

- Redesign wipe semantics / auto Push full on heal  
- Отдельный `GET /diagnostics`  
- Subscription/portal  
- Широкий UI version-gating агента (позже)

## Файлы (ориентир)

| Область | Файлы |
|---------|--------|
| Agent health | `backend/app/services/node_health.py`, `backend/node_agent/main.py`, proxy health если есть |
| Classifier | новый helper рядом с adapter или в `node_adapter.py` / `proxy_node_adapter.py` |
| Health worker | worker, обновляющий `node_metadata` |
| Push full | `backend/app/services/node_sync/push_full.py`, background task progress |
| FE | Nodes card/details, `nodeHelpers.ts`, auth failure detection |
| Docs | CHANGELOG, README badges |
