# Node SSH Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `transport=ssh` so the panel opens an in-process SSH local forward and talks HTTP to node/proxy agents through `127.0.0.1`, with encrypted SSH keys and a feature toggle default off.

**Architecture:** Extend the transport registry with a real `SshTransport`; `SshTunnelPool` (asyncssh + sync bridge) owns sessions/forwards; adapters/health resolve base URL via the pool when transport is ssh; UI shows SSH form when the toggle is on.

**Tech Stack:** FastAPI, SQLAlchemy, asyncssh, cryptography (existing encrypt_secret), React/TS, pytest

**Spec:** [docs/superpowers/specs/2026-09-13-node-ssh-transport-design.md](../specs/2026-09-13-node-ssh-transport-design.md)

## Global Constraints

- Panel → SSH → node (local forward); **not** reverse tunnel
- Auth: encrypted private key (+ optional passphrase) in panel DB
- Inside tunnel: **HTTP only** (`is_tls=False`, no mTLS inside SSH)
- Library: **asyncssh** + sync bridge for current sync adapters
- VPN **and** proxy
- Feature toggle key `node_ssh_transport` / env `FEATURE_NODE_SSH_TRANSPORT_ENABLED` — **default off**
- Never return private key material in API/logs/audit details
- Do not bump node/proxy agent versions
- Idle tunnel timeout default **600s**

## File map

| File | Responsibility |
|------|----------------|
| `backend/requirements.txt` | add `asyncssh` |
| `backend/app/models.py` | SSH columns on `Node` |
| `backend/app/database.py` | `_migrate_nodes_ssh_fields` |
| `backend/app/services/feature_toggles.py` | toggle definition default off |
| `backend/app/services/node_transport.py` | `SshTransport` real; `list_transports` respects toggle; allow apply `ssh` when enabled |
| `backend/app/services/ssh_tunnel_pool.py` | pool ensure/drop/idle/reconnect |
| `backend/app/services/node_link_errors.py` | `node_ssh_auth` / `node_ssh_unreachable` / `node_ssh_tunnel` |
| `backend/app/services/node_manager.py` | adapter construction uses tunnel local URL when ssh |
| `backend/app/routers/nodes.py` + schemas | PATCH body for ssh fields; DTO without secrets |
| `frontend/...` | toggle-aware picker + SSH form fields |
| `CHANGELOG.md` | Unreleased |

---

### Task 1: Dependency + model + migration + feature toggle

**Files:**
- Modify: `backend/requirements.txt` — add pinned `asyncssh` (check latest compatible; e.g. `asyncssh==2.21.0` or current stable at implement time)
- Modify: `backend/app/models.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/services/feature_toggles.py`
- Test: `backend/tests/test_feature_toggles.py` or new `test_node_ssh_toggle.py` asserting default off

**Interfaces:**
- Produces: columns `ssh_host`, `ssh_port`, `ssh_username`, `ssh_private_key_encrypted`, `ssh_passphrase_encrypted`, `ssh_remote_agent_host`, `ssh_remote_agent_port`
- Produces: `is_node_ssh_transport_enabled(db) -> bool` helper (or use `get_feature_service().is_enabled("node_ssh_transport")`)

- [ ] **Step 1: Add columns to `Node`**

```python
ssh_host: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
ssh_port: Mapped[int] = mapped_column(Integer, default=22)
ssh_username: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
ssh_private_key_encrypted: Mapped[str] = mapped_column(Text, default="")
ssh_passphrase_encrypted: Mapped[str] = mapped_column(Text, default="")
ssh_remote_agent_host: Mapped[str] = mapped_column(String(255), default="127.0.0.1")
ssh_remote_agent_port: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
```

- [ ] **Step 2: Migration `_migrate_nodes_ssh_fields`** — ADD COLUMN if missing; wire after `_migrate_nodes_transport`

- [ ] **Step 3: Feature toggle** next to `nodes` in `FEATURE_TOGGLES`:

```python
FeatureToggleDefinition(
    key="node_ssh_transport",
    env_key="FEATURE_NODE_SSH_TRANSPORT_ENABLED",
    label="SSH transport узлов",
    description="Способ связи SSH (local forward) на странице «Узлы». Требует модуль «Узлы».",
    icon="🔐",
    disable_hint="SSH в picker станет недоступен; http/mtls без изменений.",
    resource_impact_level="low",
    default=False,
    group="app_module",
)
```

- [ ] **Step 4: `pip install` / lock if project uses lockfile; pytest toggle default false; commit**

```bash
git commit -m "Add SSH node columns and feature toggle (default off)."
```

---

### Task 2: SshTunnelPool + error codes + SshTransport

**Files:**
- Create: `backend/app/services/ssh_tunnel_pool.py`
- Create: `backend/tests/test_ssh_tunnel_pool.py`
- Modify: `backend/app/services/node_link_errors.py` (+ tests)
- Modify: `backend/app/services/node_transport.py`

**Interfaces:**
- Produces:
  - `class SshTunnelPool:` `ensure(node) -> int` (local port), `drop(node_id: int) -> None`, `drop_all() -> None`
  - `get_ssh_tunnel_pool() -> SshTunnelPool` singleton
  - `SshTransport` with `is_tls=False`; `local_base_url(node) -> str` via pool
  - `apply_transport_value` allows `ssh` only when caller already validated feature+creds (or raise)
  - `get_transport` returns `SshTransport` for `transport=ssh` (no longer fail closed on ssh)
  - Link codes: `node_ssh_auth`, `node_ssh_unreachable`, `node_ssh_tunnel`

- [ ] **Step 1: Failing tests for pool** (mock asyncssh)

```python
def test_ensure_returns_stable_local_port(monkeypatch):
    # mock connect + forward; second ensure same port
    ...

def test_drop_closes_session():
    ...
```

- [ ] **Step 2: Implement pool**

Sketch:

```python
# ssh_tunnel_pool.py
class SshTunnelPool:
    def ensure(self, node) -> int:
        # decrypt key; asyncssh.connect(ssh_host, port, username, client_keys=[key])
        # forward_local((127.0.0.1, 0), (remote_agent_host, remote_agent_port))
        # store session by node.id; update last_used
        # map asyncssh errors → ValueError with code prefix or custom SshTunnelError(code, message)

    def drop(self, node_id: int) -> None: ...
```

Sync bridge: run coroutine on a dedicated background event loop thread owned by the pool (preferred over nested `asyncio.run` per call).

- [ ] **Step 3: Wire `get_transport` for ssh**; `list_transports()` sets ssh `available` from feature toggle (needs db/settings — pass `available: bool` from router, or read env/service without db if toggle is env-backed)

- [ ] **Step 4: Classifier helpers** for ssh errors used by manager/adapters

- [ ] **Step 5: pytest pass; commit**

```bash
git commit -m "Add SSH tunnel pool and SshTransport registry entry."
```

---

### Task 3: Adapters / node_manager use tunnel URL

**Files:**
- Modify: `backend/app/services/node_manager.py` (`get_adapter_for_node`, `get_proxy_adapter`, `check_node_health`)
- Modify: `RemoteNodeAdapter` / `ProxyNodeAdapter` **or** manager-only override:
  - Prefer manager constructs adapter with `host="127.0.0.1"`, `port=local_port`, `mtls_enabled=False` when transport is ssh
- Test: unit with mocked pool ensuring adapter base_url is localhost

- [ ] **Step 1: Helper**

```python
def _remote_http_endpoint(node: Node) -> tuple[str, int, bool]:
    from app.services.node_transport import get_transport, TRANSPORT_SSH, resolve_transport_id
    if resolve_transport_id(node) == TRANSPORT_SSH:
        port = get_ssh_tunnel_pool().ensure(node)
        return "127.0.0.1", port, False
    tr = get_transport(node)
    return node.host, node.port, tr.is_tls
```

- [ ] **Step 2: Use in adapter factories + health**; map `SshTunnelError` → health `link_error` with `node_ssh_*`

- [ ] **Step 3: On transport change away from ssh / node delete** — `drop(node_id)` (hook in disable path / DELETE node / PATCH)

- [ ] **Step 4: pytest; commit**

```bash
git commit -m "Route node adapters through SSH local forward when transport=ssh."
```

---

### Task 4: API — PATCH ssh credentials + DTO + list available

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/nodes.py`
- Modify: `backend/tests/test_node_transport_api.py` (extend) or `test_node_ssh_api.py`

**Interfaces:**
- `NodeTransportUpdate` gains optional ssh fields (`ssh_private_key` plaintext write-only)
- Response: `ssh_key_configured: bool`, ssh host/user/ports — **no** key material
- PATCH `ssh` when toggle off → 403 with module/feature message
- PATCH `ssh` without key when not configured → 400
- PATCH `ssh` with key → encrypt via `encrypt_secret`, set `transport=ssh`, `mtls_enabled=False`, `drop` old tunnel

- [x] **Step 1: Failing API tests**

```python
def test_patch_ssh_rejected_when_toggle_off(...): ...
def test_patch_ssh_stores_encrypted_key_not_in_response(...): ...
def test_list_transports_ssh_available_follows_toggle(...): ...
```

- [x] **Step 2: Implement router validation + encrypt**; reuse `store`-style helpers from `node_manager.store_api_key` pattern with `get_settings().secret_key` / existing crypto key

- [x] **Step 3: Update `_to_response` / `_node_transport_value`** — ssh is first-class; `mtls_enabled` false when ssh

- [x] **Step 4: pytest; commit**

```bash
git commit -m "Expose SSH transport PATCH API with encrypted key storage."
```

---

### Task 5: Frontend SSH form + badge + toggle awareness

**Files:**
- Modify: `frontend/src/types.ts`, `api/nodes.ts`
- Modify: `NodeTransportSelect.tsx` — respect `available`
- Create or extend: SSH fields dialog/section on transport change to ssh (NodesPage confirm or dedicated dialog)
- Modify: `NodeTransportBadge.tsx`, tg-mini badge (already has SSH label path)
- Feature toggles UI will pick up new key from API registry automatically if definitions are listed — verify Settings «Разделы»

- [ ] **Step 1: Types + `patchNodeTransport` body includes ssh fields**

- [ ] **Step 2: When user selects SSH** — open form (host/port/user/key/passphrase); submit PATCH; handle 403 if toggle off (hide option when `available: false`)

- [ ] **Step 3: Badge shows SSH**

- [ ] **Step 4: Manual/ vitest smoke; commit**

```bash
git commit -m "Add SSH transport form to node connection picker."
```

---

### Task 6: Docs + spec status

**Files:**
- `CHANGELOG.md` Unreleased Added
- Spec status → `implemented`
- Short ops note in `docs/proxy-agent.md` or `docs/nodes.md` if exists: agent on `127.0.0.1`, install panel pubkey on node

- [ ] **Step 1: Document**

```markdown
- **SSH transport узлов** (opt-in `node_ssh_transport`) — панель поднимает SSH local forward и ходит к agent по HTTP через localhost.
```

- [ ] **Step 2: commit**

```bash
git commit -m "Document SSH node transport and mark design implemented."
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Columns + migrate | 1 |
| Feature toggle default off | 1 |
| Tunnel pool + asyncssh | 2 |
| Error codes | 2 |
| Adapters via forward | 3 |
| PATCH/DTO/list available | 4 |
| UI form + badge | 5 |
| CHANGELOG / ops note | 6 |
| No reverse / no mTLS-inside | Global |

## Self-review notes

- `get_transport("ssh")` must stop raising after Task 2 (breaks old stub tests — update `test_get_transport_ssh_in_db_fails` to expect `SshTransport` or skip when key missing).
- Old test `PATCH ssh → 400` becomes toggle-dependent: off → 403/unavailable; on → success path.
- Keep http/mtls paths unchanged when toggle off.
