# Multi-remote hosts (OpenVPN) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-node ordered OpenVPN remote host list in the panel DB; patch `.ovpn` only on delivery so clients get multiple `remote` lines without editing AZ templates on disk.

**Architecture:** Store JSON list on `nodes.openvpn_remote_hosts`. Pure `apply_openvpn_remote_hosts` expands existing `(port, proto)` pairs across hosts. Admin GET/PUT `/nodes/{id}/remote-hosts`. All user-facing profile reads go through `read_profile_file_for_delivery`. UI list with ↑↓ in AntiZapret «Адреса подключения».

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, React (`AntizapretConfigTab`), pytest (unit + MagicMock; no TestClient).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-multi-remote-hosts-design.md`
- Product plan (reference): `docs/plans/multi-remote-hosts/` (01–05 only; **not** 06/07)
- OpenVPN only; never patch WireGuard / AmneziaWG
- Patch only on delivery paths; never HA disk copy / cert-expiry / backup reads
- Max 8 hosts; duplicates rejected; Russian error messages
- Non-empty PUT → best-effort `OPENVPN_HOST = hosts[0]`; empty PUT → **do not** change `OPENVPN_HOST`
- Panel never installs/runs `proxy.sh`
- Do not change traffic collector code
- User-facing docs in Russian; update `docs/PROJECT_MAP.md` for new API/UI
- Commit after each task (SDD); message focuses on why

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/openvpn_remote_hosts.py` | validate / normalize / apply / JSON load-save helpers |
| `backend/tests/test_openvpn_remote_hosts.py` | Unit tests for patch + validation |
| `backend/app/models.py` | `Node.openvpn_remote_hosts` column |
| `backend/app/database.py` | SQLite migrate `nodes.openvpn_remote_hosts` |
| `backend/app/schemas.py` | `NodeRemoteHostsBody` / response |
| `backend/app/routers/nodes.py` | GET/PUT `/nodes/{node_id}/remote-hosts` |
| `backend/tests/test_nodes_remote_hosts_api.py` | Handler/service tests with mocks |
| `backend/app/services/profile_delivery.py` | `read_profile_file_for_delivery` + load hosts by node_id |
| `backend/app/routers/configs.py` | download + QR use delivery wrapper |
| `backend/app/routers/public_download.py` | redeem uses delivery + active-node hosts |
| `backend/app/services/telegram_config_send.py` | Telegram/Mini App send uses delivery |
| `backend/tests/test_profile_delivery.py` | Delivery wrapper + call-site smoke with mocks |
| `frontend/src/api/client.ts` | `getNodeRemoteHosts` / `putNodeRemoteHosts` |
| `frontend/src/types.ts` | Types if needed |
| `frontend/src/components/routing/AntizapretConfigTab.tsx` | UI list ↑↓ + hints |
| `docs/antizapret-config.md`, `docs/PROJECT_MAP.md`, `CHANGELOG.md`, plan README | Docs + status |

---

### Task 1: Patch service + unit tests

**Files:**
- Create: `backend/app/services/openvpn_remote_hosts.py`
- Create: `backend/tests/test_openvpn_remote_hosts.py`

**Interfaces:**
- Produces:
  - `MAX_OPENVPN_REMOTE_HOSTS = 8`
  - `class RemoteHostsError(ValueError)` with Russian `args[0]`
  - `validate_host(host: str) -> str`
  - `normalize_hosts(hosts: list[str] | None) -> list[str]`
  - `parse_hosts_json(raw: str | None) -> list[str]`  # empty/invalid → `[]`
  - `hosts_to_json(hosts: list[str]) -> str`  # `json.dumps` list
  - `apply_openvpn_remote_hosts(content: str, hosts: list[str]) -> str`
- Consumes: stdlib only (`re`, `json`, `ipaddress`)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_openvpn_remote_hosts.py
import pytest

from app.services.openvpn_remote_hosts import (
    RemoteHostsError,
    apply_openvpn_remote_hosts,
    normalize_hosts,
    validate_host,
)

SAMPLE = """client
dev tun
remote 10.0.0.1 1194 udp
remote 10.0.0.1 443 tcp
<ca>
-----BEGIN CERTIFICATE-----
ABC
-----END CERTIFICATE-----
</ca>
setenv FRIENDLY_NAME test
"""


def test_validate_host_ok():
    assert validate_host(" 1.2.3.4 ") == "1.2.3.4"
    assert validate_host("vpn.example.com") == "vpn.example.com"


def test_validate_host_rejects_bad():
    with pytest.raises(RemoteHostsError):
        validate_host("")
    with pytest.raises(RemoteHostsError):
        validate_host("bad host")
    with pytest.raises(RemoteHostsError):
        validate_host("http://evil")


def test_normalize_max_and_dup():
    assert normalize_hosts(None) == []
    assert normalize_hosts([]) == []
    with pytest.raises(RemoteHostsError):
        normalize_hosts(["a.com", "a.com"])
    with pytest.raises(RemoteHostsError):
        normalize_hosts([f"h{i}.com" for i in range(9)])


def test_apply_expands_hosts_times_ports():
    out = apply_openvpn_remote_hosts(SAMPLE, ["1.1.1.1", "2.2.2.2", "3.3.3.3"])
    remotes = [ln for ln in out.splitlines() if ln.startswith("remote ")]
    assert remotes == [
        "remote 1.1.1.1 1194 udp",
        "remote 1.1.1.1 443 tcp",
        "remote 2.2.2.2 1194 udp",
        "remote 2.2.2.2 443 tcp",
        "remote 3.3.3.3 1194 udp",
        "remote 3.3.3.3 443 tcp",
    ]
    assert "FRIENDLY_NAME" in out
    assert "BEGIN CERTIFICATE" in out


def test_apply_empty_hosts_unchanged():
    assert apply_openvpn_remote_hosts(SAMPLE, []) == SAMPLE


def test_apply_no_remote_unchanged():
    body = "client\ndev tun\n"
    assert apply_openvpn_remote_hosts(body, ["1.1.1.1"]) == body


def test_apply_idempotent():
    once = apply_openvpn_remote_hosts(SAMPLE, ["a.com", "b.com"])
    twice = apply_openvpn_remote_hosts(once, ["a.com", "b.com"])
    assert once == twice
```

- [ ] **Step 2: Run tests — expect FAIL (module missing)**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_openvpn_remote_hosts.py -v`
Expected: FAIL import / not found

- [ ] **Step 3: Implement module**

```python
# backend/app/services/openvpn_remote_hosts.py
from __future__ import annotations

import ipaddress
import json
import re

MAX_OPENVPN_REMOTE_HOSTS = 8

_REMOTE_RE = re.compile(
    r"^(?P<prefix>\s*)remote\s+(?P<host>\S+)\s+(?P<port>\d+)(?:\s+(?P<proto>\S+))?\s*$"
)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class RemoteHostsError(ValueError):
    """Validation error with a Russian message in args[0]."""


def validate_host(host: str) -> str:
    value = (host or "").strip()
    if not value:
        raise RemoteHostsError("Адрес не может быть пустым")
    if any(ch.isspace() for ch in value):
        raise RemoteHostsError("Адрес не должен содержать пробелы")
    if value.lower().startswith(("http://", "https://", "ftp://", "file://")):
        raise RemoteHostsError("Укажите IP или домен без схемы URL")
    if "/" in value or "\\" in value or "@" in value:
        raise RemoteHostsError("Недопустимые символы в адресе")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(value):
        raise RemoteHostsError(f"Некорректный адрес: {value}")
    return value


def normalize_hosts(hosts: list[str] | None) -> list[str]:
    if not hosts:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in hosts:
        if raw is None or str(raw).strip() == "":
            continue
        h = validate_host(str(raw))
        key = h.lower()
        if key in seen:
            raise RemoteHostsError(f"Дубликат адреса: {h}")
        seen.add(key)
        out.append(h)
    if len(out) > MAX_OPENVPN_REMOTE_HOSTS:
        raise RemoteHostsError(f"Не больше {MAX_OPENVPN_REMOTE_HOSTS} адресов")
    return out


def parse_hosts_json(raw: str | None) -> list[str]:
    if raw is None or str(raw).strip() == "":
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    try:
        return normalize_hosts([str(x) for x in data])
    except RemoteHostsError:
        return []


def hosts_to_json(hosts: list[str]) -> str:
    return json.dumps(list(hosts), ensure_ascii=False)


def apply_openvpn_remote_hosts(content: str, hosts: list[str]) -> str:
    if not hosts:
        return content
    lines = content.splitlines(keepends=True)
    pairs: list[tuple[str, str | None]] = []
    seen_pairs: set[tuple[str, str | None]] = set()
    remote_idxs: list[int] = []
    for i, line in enumerate(lines):
        bare = line[:-1] if line.endswith("\n") else line
        if bare.endswith("\r"):
            bare = bare[:-1]
        m = _REMOTE_RE.match(bare)
        if not m:
            continue
        remote_idxs.append(i)
        pair = (m.group("port"), m.group("proto"))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            pairs.append(pair)
    if not remote_idxs or not pairs:
        return content
    new_remotes: list[str] = []
    for host in hosts:
        for port, proto in pairs:
            if proto:
                new_remotes.append(f"remote {host} {port} {proto}\n")
            else:
                new_remotes.append(f"remote {host} {port}\n")
    # Drop CRLF handling: emit \n; if original used \r\n, normalize block to \n (acceptable).
    first = remote_idxs[0]
    keep = [ln for i, ln in enumerate(lines) if i not in set(remote_idxs)]
    # Insert at original first remote position among remaining lines:
    # Rebuild: take lines before first remote, then new remotes, then lines after last remote
    # with all remotes removed.
    before = []
    after = []
    for i, ln in enumerate(lines):
        if i < first:
            before.append(ln)
        elif i in set(remote_idxs):
            continue
        else:
            after.append(ln)
    return "".join(before + new_remotes + after)
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_openvpn_remote_hosts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/openvpn_remote_hosts.py backend/tests/test_openvpn_remote_hosts.py
git commit -m "$(cat <<'EOF'
feat: add OpenVPN multi-remote patch helpers

EOF
)"
```

---

### Task 2: Model, migration, remote-hosts API

**Files:**
- Modify: `backend/app/models.py` (`Node`)
- Modify: `backend/app/database.py` (`run_db_migrations` nodes columns)
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/nodes.py`
- Create: `backend/tests/test_nodes_remote_hosts_api.py`

**Interfaces:**
- Consumes: `normalize_hosts`, `parse_hosts_json`, `hosts_to_json`, `RemoteHostsError` from Task 1
- Produces:
  - `Node.openvpn_remote_hosts: Mapped[str | None]` (Text, nullable, default `None`)
  - `GET/PUT /api/nodes/{node_id}/remote-hosts` → `{ "hosts": [...], "warnings": [] }`
  - On non-empty PUT: `get_adapter_for_node(node).update_antizapret_settings({"openvpn_host": hosts[0]})` best-effort
  - On empty PUT: do **not** call update for openvpn_host

- [ ] **Step 1: Add model column**

In `Node` after `node_metadata`:

```python
openvpn_remote_hosts: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
```

- [ ] **Step 2: Migration**

In `run_db_migrations` migrations dict, add table entry (or dedicated helper like mtls):

```python
"nodes": [
    ("openvpn_remote_hosts", "TEXT"),
],
```

If `"nodes"` key already appears elsewhere, merge into one list — do not duplicate the table key. Prefer adding to the generic migrations dict; if `nodes` is only handled in `_migrate_nodes_mtls_enabled`, either extend that helper or add:

```python
def _migrate_nodes_openvpn_remote_hosts() -> None:
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    if "openvpn_remote_hosts" in cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE nodes ADD COLUMN openvpn_remote_hosts TEXT"))
        logger.info("DB migration: added nodes.openvpn_remote_hosts")
```

Call it from `run_db_migrations` next to `_migrate_nodes_mtls_enabled()`.

- [ ] **Step 3: Schemas**

```python
class NodeRemoteHostsBody(BaseModel):
    hosts: list[str] = Field(default_factory=list)


class NodeRemoteHostsResponse(BaseModel):
    hosts: list[str]
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Router endpoints** (place near other `/{node_id}/…` admin routes; after static paths like `/mtls/status`)

```python
@router.get("/{node_id}/remote-hosts", response_model=NodeRemoteHostsResponse)
def get_remote_hosts(node_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    return NodeRemoteHostsResponse(hosts=parse_hosts_json(node.openvpn_remote_hosts))


@router.put("/{node_id}/remote-hosts", response_model=NodeRemoteHostsResponse)
def put_remote_hosts(
    node_id: int,
    payload: NodeRemoteHostsBody,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Узел не найден")
    try:
        hosts = normalize_hosts(payload.hosts)
    except RemoteHostsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    node.openvpn_remote_hosts = hosts_to_json(hosts) if hosts else None
    node.updated_at = datetime.utcnow()
    db.add(node)
    db.commit()
    db.refresh(node)
    warnings: list[str] = []
    if hosts:
        try:
            get_adapter_for_node(node).update_antizapret_settings({"openvpn_host": hosts[0]})
        except Exception as exc:  # noqa: BLE001 — best-effort; list already saved
            warnings.append(f"Не удалось обновить OPENVPN_HOST: {exc}")
    if settings.audit_log_enabled:
        log_action(
            db,
            action="node_remote_hosts_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"node_id={node_id} hosts={hosts}",
        )
    return NodeRemoteHostsResponse(hosts=hosts, warnings=warnings)
```

Import needed symbols from `openvpn_remote_hosts`, `get_adapter_for_node`, schemas.

- [ ] **Step 5: Tests (unit, MagicMock — no TestClient)**

```python
# backend/tests/test_nodes_remote_hosts_api.py
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.openvpn_remote_hosts import RemoteHostsError, normalize_hosts, hosts_to_json, parse_hosts_json


def test_parse_roundtrip():
    raw = hosts_to_json(["1.1.1.1", "vpn.example.com"])
    assert parse_hosts_json(raw) == ["1.1.1.1", "vpn.example.com"]
    assert parse_hosts_json(None) == []
    assert parse_hosts_json("not-json") == []


def test_put_logic_empty_skips_setup(monkeypatch):
    """Document expected router behavior via a small extracted helper if added;
    otherwise assert normalize([]) and that empty means openvpn_remote_hosts=None."""
    assert normalize_hosts([]) == []


def test_put_rejects_dup():
    with pytest.raises(RemoteHostsError):
        normalize_hosts(["a.com", "A.com"])
```

Also add a focused test that mocks `get_adapter_for_node` and a fake router-callable if you extract `_save_remote_hosts(db, node, hosts) -> list[str]` warnings into the service layer — preferred:

```python
# in openvpn_remote_hosts.py or a thin nodes helper
def sync_openvpn_host_from_remotes(adapter, hosts: list[str]) -> list[str]:
    if not hosts:
        return []
    try:
        adapter.update_antizapret_settings({"openvpn_host": hosts[0]})
        return []
    except Exception as exc:  # noqa: BLE001
        return [f"Не удалось обновить OPENVPN_HOST: {exc}"]
```

Test:

```python
def test_sync_skips_when_empty():
    adapter = MagicMock()
    assert sync_openvpn_host_from_remotes(adapter, []) == []
    adapter.update_antizapret_settings.assert_not_called()


def test_sync_best_effort_warning():
    adapter = MagicMock()
    adapter.update_antizapret_settings.side_effect = RuntimeError("down")
    warnings = sync_openvpn_host_from_remotes(adapter, ["1.2.3.4"])
    assert warnings and "OPENVPN_HOST" in warnings[0]
```

- [ ] **Step 6: Run tests**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_openvpn_remote_hosts.py tests/test_nodes_remote_hosts_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/database.py backend/app/schemas.py \
  backend/app/routers/nodes.py backend/app/services/openvpn_remote_hosts.py \
  backend/tests/test_nodes_remote_hosts_api.py
git commit -m "$(cat <<'EOF'
feat: store and expose per-node OpenVPN remote hosts

EOF
)"
```

---

### Task 3: Delivery wrapper on all `.ovpn` paths

**Files:**
- Create: `backend/app/services/profile_delivery.py`
- Create: `backend/tests/test_profile_delivery.py`
- Modify: `backend/app/routers/configs.py` (`download_profile`, `generate_qr`)
- Modify: `backend/app/routers/public_download.py` (`qr_download_get`, `qr_download_post`)
- Modify: `backend/app/services/telegram_config_send.py` (`send_config_files_to_chat`)

**Interfaces:**
- Produces:
  - `load_node_remote_hosts(db: Session, node_id: int | None) -> list[str]`
  - `read_profile_file_for_delivery(adapter, path: str, hosts: list[str]) -> str`
- Consumes: `adapter.read_profile_file`, `apply_openvpn_remote_hosts`, `parse_hosts_json`

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_profile_delivery.py
from unittest.mock import MagicMock

from app.services.profile_delivery import read_profile_file_for_delivery

OVPN = "remote 10.0.0.1 1194 udp\n"
WG = "[Interface]\nPrivateKey=x\n"


def test_delivery_patches_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    out = read_profile_file_for_delivery(adapter, "/x/client.ovpn", ["1.1.1.1", "2.2.2.2"])
    assert "remote 1.1.1.1 1194 udp" in out
    assert "remote 2.2.2.2 1194 udp" in out


def test_delivery_skips_non_ovpn():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = WG
    out = read_profile_file_for_delivery(adapter, "/x/client.conf", ["1.1.1.1"])
    assert out == WG


def test_delivery_empty_hosts_raw():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = OVPN
    assert read_profile_file_for_delivery(adapter, "/x/a.ovpn", []) == OVPN
```

- [ ] **Step 2: Implement**

```python
# backend/app/services/profile_delivery.py
from __future__ import annotations

from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.models import Node
from app.services.openvpn_remote_hosts import apply_openvpn_remote_hosts, parse_hosts_json


def load_node_remote_hosts(db: Session, node_id: int | None) -> list[str]:
    if not node_id:
        return []
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        return []
    return parse_hosts_json(node.openvpn_remote_hosts)


def read_profile_file_for_delivery(adapter, path: str, hosts: list[str]) -> str:
    raw = adapter.read_profile_file(path)
    # Match .ovpn case-insensitively on final suffix
    name = PurePosixPath(path.replace("\\", "/")).name
    if not name.lower().endswith(".ovpn"):
        return raw
    return apply_openvpn_remote_hosts(raw, hosts)
```

- [ ] **Step 3: Wire call sites**

`configs.py` — `download_profile` and `generate_qr`:

```python
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery

# replace adapter.read_profile_file(path) with:
hosts = load_node_remote_hosts(db, config.node_id)
content = read_profile_file_for_delivery(adapter, path, hosts)
```

`telegram_config_send.py` — inside the loop:

```python
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery

hosts = load_node_remote_hosts(db, config.node_id)
# once before loop is fine
...
content = read_profile_file_for_delivery(adapter, selected_path, hosts)
```

`public_download.py` — redeem has no `VpnConfig`; use **active node** hosts (same node the adapter already reads from):

```python
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery

node = get_active_node(db)
hosts = load_node_remote_hosts(db, node.id)
content = read_profile_file_for_delivery(get_active_adapter(db), row.file_path, hosts)
```

Do **not** change cert/PKI/HA/backup readers.

- [ ] **Step 4: Run tests**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_profile_delivery.py tests/test_openvpn_remote_hosts.py tests/test_nodes_remote_hosts_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/profile_delivery.py backend/tests/test_profile_delivery.py \
  backend/app/routers/configs.py backend/app/routers/public_download.py \
  backend/app/services/telegram_config_send.py
git commit -m "$(cat <<'EOF'
feat: patch OpenVPN remotes on all profile delivery paths

EOF
)"
```

---

### Task 4: Frontend UI — «Адреса подключения»

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types.ts` (if needed)
- Modify: `frontend/src/components/routing/AntizapretConfigTab.tsx`

**Interfaces:**
- Consumes: `GET/PUT /nodes/{id}/remote-hosts`
- Produces: list editor with add / remove / ↑ / ↓; save separate from setup dirty keys

- [ ] **Step 1: API client**

```typescript
export async function getNodeRemoteHosts(nodeId: number) {
  return apiFetch<{ hosts: string[]; warnings?: string[] }>(`/nodes/${nodeId}/remote-hosts`)
}

export async function putNodeRemoteHosts(nodeId: number, hosts: string[]) {
  return apiFetch<{ hosts: string[]; warnings: string[] }>(`/nodes/${nodeId}/remote-hosts`, {
    method: 'PUT',
    body: JSON.stringify({ hosts }),
  })
}
```

- [ ] **Step 2: UI behavior in `AntizapretConfigTab`**

1. Read active node id from existing context/hook used by the tab (same source as other node-scoped actions). If none — hide list or show disabled hint.
2. On load (with settings): also `getNodeRemoteHosts(activeNodeId)` → local state `remoteHosts: string[]`.
3. In section «Адреса подключения»:
   - Render editable list (inputs) with buttons ↑ ↓ × and «Добавить адрес» (disable add when length ≥ 8).
   - Keep WireGuard field from setup as today; add short note under it: «Несколько адресов пока только для OpenVPN».
   - For OpenVPN host setup field: when `remoteHosts.length > 0`, show read-only/synced display of `remoteHosts[0]` **or** disable the setup `openvpn_host` input and explain that the first list entry is written to `OPENVPN_HOST` on save of the list. Saving the list uses `putNodeRemoteHosts`, not `updateAntizapretSettings`.
4. Separate «Сохранить адреса» (or include in section save) calling `putNodeRemoteHosts`; toast errors from API `detail`; show `warnings` if present.
5. Hints (Russian, plain language) — match design/spec bullet list (order, max 8, proxy.sh self-install link, allow-ips, traffic on foreign VPN, list survives AZ update).

Match existing tab styling (no new design system); reuse buttons/inputs already used in the tab.

- [ ] **Step 3: Manual smoke (or build check)**

Run: `cd /opt/AdminPanelAZ/frontend && npm run build` (or project’s usual lint/typecheck)
Expected: success

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/types.ts \
  frontend/src/components/routing/AntizapretConfigTab.tsx
git commit -m "$(cat <<'EOF'
feat: UI for per-node OpenVPN remote host list

EOF
)"
```

---

### Task 5: Docs, CHANGELOG, plan status

**Files:**
- Modify: `docs/antizapret-config.md`
- Modify: `docs/PROJECT_MAP.md` (API + UI section)
- Optionally 1–2 sentences: `docs/traffic-monitoring.md`, `docs/NodeSync.md`
- Modify: `CHANGELOG.md` (Unreleased / next version section per repo style)
- Modify: `docs/plans/multi-remote-hosts/README.md` — status «реализовано (MVP)» when done
- Modify: `docs/superpowers/specs/2026-08-02-multi-remote-hosts-design.md` — status `implemented` when done

- [ ] **Step 1: User docs**

Add section **«Несколько адресов подключения»** to `docs/antizapret-config.md`:

- where in UI; per-node order; example RUS → server1 → server2 vs reverse on second node
- link to [Настроить прокси-сервер](https://github.com/GubernievS/AntiZapret-VPN#настроить-прокси-сервер)
- panel does not install proxy.sh; one proxy → one DESTINATION_IP
- allow-ips reminder
- list in panel survives `setup.sh`; do not rely on editing templates on disk
- traffic: counted on foreign VPN session node; without HA counters separate; with HA Sync Group — existing monitoring sum

- [ ] **Step 2: PROJECT_MAP + CHANGELOG**

Document `GET/PUT /nodes/{id}/remote-hosts` and UI section. CHANGELOG entry under features.

- [ ] **Step 3: Acceptance checklist (comment in plan README)**

```markdown
- [ ] One node, 1–3 remotes → download order matches
- [ ] Clear list → stock .ovpn; OPENVPN_HOST unchanged by panel
- [ ] Two nodes without HA, different orders
- [ ] HA Sync Group if stand available
- [ ] proxy + s1 + s2 scenario
```

- [ ] **Step 4: Run full related pytest once**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_openvpn_remote_hosts.py tests/test_nodes_remote_hosts_api.py tests/test_profile_delivery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/antizapret-config.md docs/PROJECT_MAP.md docs/plans/multi-remote-hosts/README.md \
  docs/superpowers/specs/2026-08-02-multi-remote-hosts-design.md CHANGELOG.md \
  docs/traffic-monitoring.md docs/NodeSync.md 2>/dev/null || true
git commit -m "$(cat <<'EOF'
docs: multi-remote OpenVPN hosts for admins

EOF
)"
```

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| `apply` / validate / normalize | Task 1 |
| Column + GET/PUT + OPENVPN_HOST sync / empty leave alone | Task 2 |
| Delivery all channels; skip HA/cert/WG | Task 3 |
| UI ↑↓ + hints | Task 4 |
| Docs + acceptance | Task 5 |
| No proxy.sh install / no traffic code / no stage 07 | Global Constraints |

No TBD placeholders. Types: `hosts: list[str]`, response includes `warnings`. Public redeem uses active-node hosts (documented; matches existing adapter scope).
