# Node SSH transport (local forward)

**Дата:** 2026-09-13  
**Статус:** implemented  
**Ветка:** `feature/client-portal`  
**Подход:** вариант **A** — in-process SSH (asyncssh/paramiko) + tunnel pool; HTTP к agent через local forward  
**Базовый spec:** [2026-09-13-node-transport-framework-design.md](./2026-09-13-node-transport-framework-design.md)

## Контекст

P0 transport framework дал `nodes.transport` (`http` | `mtls` | `ssh`) и picker; `ssh` был stub (`transport_not_implemented`, без записи в БД).

Нужен рабочий SSH-канал: панель открывает SSH к узлу, поднимает local forward и ходит к существующему agent API (`node_agent` / `proxy_agent`) по **HTTP** через `127.0.0.1`. Протокол агента не меняется.

## Решения brainstorm

| Тема | Выбор |
|------|--------|
| Направление | Панель → SSH → узел (не reverse) |
| Auth | Приватный ключ encrypted в панели (+ optional passphrase) |
| Внутри туннеля | Только HTTP (без mTLS внутри SSH в MVP) |
| Реализация туннеля | **A** — in-process SSH + pool |
| Scope | VPN и proxy |
| Feature flag | `FEATURE_NODE_SSH_TRANSPORT` (или аналог в `FEATURE_TOGGLES`) — **default off** |

## §1. Цель и границы

**In scope (MVP):**

- Разрешить `transport=ssh` (писать в БД) при валидных SSH-полях.
- Хранение SSH credentials (encrypt как API keys).
- `SshTunnelPool`: сессия + local forward per node; reconnect; idle teardown.
- Adapters/health через forward → `http://127.0.0.1:<ephemeral>`.
- UI: picker SSH + форма ssh_host/port/user/key/passphrase; badge `SSH`.
- Коды ошибок `node_ssh_*`; link diagnostics совместимы.
- Feature toggle default **off**.
- Тесты + CHANGELOG.

**Out of scope:**

- Reverse SSH / node-initiated tunnel.
- ProxyJump / bastion UI (можно позже через OpenSSH-совместимые поля).
- Password-only SSH (без ключа).
- mTLS внутри туннеля.
- Смена wire protocol агента.
- Автогенерация ключей на узле (админ кладёт pubkey на сервер сам).

## §2. Data model

Колонки на `nodes` (или эквивалент в encrypted settings — предпочтение **колонки на Node**):

| Поле | Тип | Смысл |
|------|-----|--------|
| `transport` | str | `ssh` |
| `ssh_host` | str | SSH endpoint |
| `ssh_port` | int | default `22` |
| `ssh_username` | str | SSH user |
| `ssh_private_key_encrypted` | str | PEM, encrypt_secret |
| `ssh_passphrase_encrypted` | str \| null | optional |
| `ssh_remote_agent_host` | str | default `127.0.0.1` |
| `ssh_remote_agent_port` | int \| null | default = `node.port` (9100/9101) |

Семантика существующих полей в режиме SSH:

- `node.host` / `node.port` — **agent за туннелем** (remote bind host/port на стороне узла), не обязан совпадать с публичным SSH host.  
  Альтернатива (lock): держать agent bind только в `ssh_remote_agent_*`, а `node.host`/`port` оставить как SSH host/port для UX-совместимости со старыми экранами.

**Lock для MVP:**  
- `ssh_host` / `ssh_port` / `ssh_username` — SSH.  
- `node.port` (+ `ssh_remote_agent_host`, default `127.0.0.1`) — куда forwardить agent API.  
- `node.host` может дублировать `ssh_host` для отображения «где узел», но adapters в SSH-режиме **не** коннектятся на `node.host` напрямую.

`mtls_enabled` при `transport=ssh` → **false** (derived).

Миграция: add columns; ssh остаётся недоступным пока toggle off.

## §3. Архитектура

```text
Nodes UI ──► PATCH /nodes/{id}/transport {ssh + credentials}
                    │
                    ▼
              nodes.transport=ssh + ssh_*
                    │
Health / Adapters ──► get_transport(node) ──► SshTransport
                                              │
                                              ▼
                                         SshTunnelPool.ensure(node_id)
                                              │ asyncssh connect + local forward
                                              ▼
                                    http://127.0.0.1:LPORT
                                              │ X-Node-Key
                                              ▼
                         remote 127.0.0.1:9100|9101 (agent HTTP)
```

### Модули

| Символ | Роль |
|--------|------|
| `SshTransport` | `id=ssh`, `is_tls=False`, `base_scheme=http`, client base URL = local forward |
| `SshTunnelPool` | `ensure(node) -> local_port`, `drop(node_id)`, idle GC, reconnect |
| `ssh_credentials` helpers | encrypt/decrypt key+passphrase; never log PEM |
| Feature guard | PATCH/UI/list `available` зависят от toggle |

Библиотека: **asyncssh** предпочтительно; если adapters sync — тонкий sync bridge (thread / `asyncio.run` scoped) без блокировки event loop панели надолго. Paramiko допустим как альтернатива в plan, если asyncssh интеграция дороже — **lock: asyncssh + sync bridge**.

### Lifecycle

1. Первый запрос / health при `transport=ssh` → `ensure()`: connect, auth key, forward `local_port → ssh_remote_agent_host:agent_port`.  
2. Повторные запросы переиспользуют сессию.  
3. Ошибка канала → invalidate + one reconnect; затем `node_ssh_*` / offline.  
4. Idle timeout (конфиг, default **10 min**) без запросов → close.  
5. Смена transport с `ssh` → `drop()`; смена ключа/host → `drop()` + re-ensure.  
6. Process shutdown → close all.

## §4. API

### `GET /nodes/transports`

При toggle **off**: ssh `available: false` (как сейчас).  
При toggle **on**: ssh `available: true`.

### `PATCH /nodes/{id}/transport`

Body расширяется (или отдельный `PUT /nodes/{id}/ssh`):

```json
{
  "transport": "ssh",
  "ssh_host": "203.0.113.10",
  "ssh_port": 22,
  "ssh_username": "root",
  "ssh_private_key": "-----BEGIN …-----",
  "ssh_passphrase": null,
  "ssh_remote_agent_host": "127.0.0.1",
  "ssh_remote_agent_port": null
}
```

- Toggle off → 403/404 feature disabled.  
- Валидация: host, user, non-empty key PEM; port ranges.  
- Ключ в response **никогда** не возвращать; только `ssh_key_configured: true`.  
- После save: optional sync probe (health через туннель); при fail — либо rollback transport, либо оставить ssh + `last_link_error` — **lock: оставить ssh + записать link error** (как soft enable), UI показывает ошибку связи.  
- Переход `ssh` → `http`/`mtls`: `drop()` tunnel; для mtls — существующий enable path.

Legacy `enable-mtls` / `disable-mtls` не трогают ssh (400 если сейчас ssh и зовут mtls shorthand — или enable_mtls сначала меняет transport).

### Node DTO

Добавить: `ssh_host`, `ssh_port`, `ssh_username`, `ssh_key_configured`, `ssh_remote_agent_host`, `ssh_remote_agent_port` (без секретов).

## §5. UI

- Picker: SSH доступен только при toggle on.  
- При выборе SSH — поля credentials (textarea key, optional passphrase).  
- Confirm перед сохранением.  
- Badge / TG: `SSH`.  
- Блок «Связь»: expected TLS false; при ssh ошибках — код `node_ssh_*` + hint.

## §6. Ошибки

| Код | Когда |
|-----|--------|
| `node_ssh_auth` | auth failure / bad key |
| `node_ssh_unreachable` | connect/timeout to ssh_host |
| `node_ssh_tunnel` | forward failed / local bind |
| `node_auth` / `node_unreachable` / … | ошибки HTTP к agent **после** успешного туннеля |

HTTP к UI: 502/504 как у прочих node link errors; не logout.

## §7. Security

- Encrypt at rest; redact logs; no key in API responses/audit details.  
- Temp material only in memory (asyncssh from string).  
- Agent ideally listen `127.0.0.1` on node when using SSH-only exposure (docs note; не enforce в MVP).  
- Toggle default off — явный opt-in.

## §8. Тесты и готовность

**Backend:** encrypt roundtrip; pool ensure/reuse/drop (mocks); PATCH ssh validation; health via mocked forward; toggle off rejects; transition ssh→http drops tunnel.  
**Frontend:** form + available flag; badge SSH.  

**Готово когда:** при toggle on можно выбрать SSH, сохранить ключ, получить online health через туннель; при off — ssh unavailable; без регрессии http/mtls.

## Файлы (ориентир)

| Область | Файлы |
|---------|--------|
| Model / migrate | `models.py`, `database.py` |
| Transport / pool | `node_transport.py`, новый `ssh_tunnel_pool.py` |
| Adapters / manager | `node_manager.py`, adapters base URL override |
| API | `routers/nodes.py`, schemas |
| FE | NodeTransportSelect + SSH form |
| Feature toggles | registry + Settings |
| Docs | этот spec, CHANGELOG, короткий ops note |

## Follow-up

- ProxyJump / bastion.  
- Reverse tunnel.  
- Optional mTLS inside SSH.  
- Key rotation UX / generate keypair in panel.
