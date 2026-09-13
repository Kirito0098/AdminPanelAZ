# Node Transport Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-node `transport` (`http` | `mtls`) with a registry for future SSH; VPN and proxy share one picker; SSH stub returns `transport_not_implemented` without writing DB.

**Architecture:** Add `nodes.transport`, keep `mtls_enabled` synced as derived; `get_transport(node)` feeds adapters/health `expected_tls`; PATCH `/nodes/{id}/transport` plus existing enable/disable-mtls as shorthands.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, React/TS, pytest, vitest

**Spec:** [docs/superpowers/specs/2026-09-13-node-transport-framework-design.md](../specs/2026-09-13-node-transport-framework-design.md)

## Global Constraints

- Scope: VPN **and** proxy — one `transport` field
- P0 writable values: only `http`, `mtls`; PATCH `ssh` → **400** `transport_not_implemented`, **no DB write**
- API `mtls_enabled` always derived: `transport == "mtls"` (local → false as today)
- On transport change, sync DB `mtls_enabled` with derived value
- Do not bump node/proxy agent versions for this feature
- Keep `POST …/enable-mtls` and `…/disable-mtls` as shorthands
- Unknown `transport` in DB → fail closed (do not silently treat as http)

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/node_transport.py` | Protocol, Http/Mtls/Ssh stub, registry, `get_transport`, `list_transports`, `set_node_transport` helpers |
| `backend/app/models.py` | `Node.transport` column |
| `backend/app/database.py` | `_migrate_nodes_transport` add column + backfill from `mtls_enabled` |
| `backend/app/schemas.py` | `transport` on `NodeResponse`; request/response for PATCH; transports list |
| `backend/app/routers/nodes.py` | `GET /transports`, `PATCH /{id}/transport`; DTO mapping |
| `backend/app/services/node_mtls_provision.py` | Set `transport` alongside `mtls_enabled` |
| `backend/app/services/node_manager.py` | Adapter construction + `expected_tls` via transport |
| `backend/app/services/node_adapter.py` / `proxy_node_adapter.py` | Prefer transport `is_tls` / scheme / ssl (thin: still accept `mtls_enabled=` kwarg mapped from transport) |
| `frontend/src/types.ts`, `api/nodes.ts` | Types + API |
| `frontend/src/components/nodes/*` | Picker + badge |
| `frontend/src/tg-mini/pages/Nodes.tsx` | Badge by transport |
| `CHANGELOG.md` | Unreleased |

---

### Task 1: Transport module + DB column + migration

**Files:**
- Create: `backend/app/services/node_transport.py`
- Create: `backend/tests/test_node_transport.py`
- Modify: `backend/app/models.py` (`Node.transport`)
- Modify: `backend/app/database.py` (call `_migrate_nodes_transport` near `_migrate_nodes_mtls_enabled`)

**Interfaces:**
- Produces:
  - `TRANSPORT_HTTP = "http"`, `TRANSPORT_MTLS = "mtls"`, `TRANSPORT_SSH = "ssh"`
  - `class NodeTransport(Protocol)` with `id: str`, `display_name: str`, `is_tls: bool`, `base_scheme() -> str`, `ssl_context() -> ssl.SSLContext | bool | None`
  - `def list_transports() -> list[dict]` → `[{id, label, available}, ...]` (ssh `available=False`)
  - `def get_transport(node: Node) -> NodeTransport` — fail closed on unknown / ssh-in-DB
  - `def sync_mtls_flag(node: Node) -> None` — `node.mtls_enabled = (node.transport == "mtls")`
  - `def apply_transport_value(node: Node, transport: str) -> None` — sets `transport` + sync flag; raises `ValueError` for unsupported

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_node_transport.py
from app.services import node_transport as nt

def test_list_transports_marks_ssh_unavailable():
    items = {i["id"]: i for i in nt.list_transports()}
    assert items["http"]["available"] is True
    assert items["mtls"]["available"] is True
    assert items["ssh"]["available"] is False

def test_get_transport_http_and_mtls(monkeypatch):
    class N:
        transport = "http"
        mtls_enabled = False
        is_local = False
    assert nt.get_transport(N()).id == "http"
    N.transport = "mtls"
    assert nt.get_transport(N()).is_tls is True

def test_get_transport_unknown_fails():
    class N:
        transport = "wire"
        is_local = False
    try:
        nt.get_transport(N())
        assert False, "expected error"
    except ValueError as e:
        assert "transport" in str(e).lower() or "wire" in str(e)

def test_apply_transport_rejects_ssh():
    class N:
        transport = "http"
        mtls_enabled = False
    try:
        nt.apply_transport_value(N(), "ssh")
        assert False
    except ValueError as e:
        assert "not_implemented" in str(e) or "ssh" in str(e).lower()
```

- [ ] **Step 2: Run tests — expect FAIL** (module missing)

Run: `cd backend && python -m pytest tests/test_node_transport.py -v`

- [ ] **Step 3: Implement `node_transport.py`**

```python
# Key shapes (full file in implementation)
TRANSPORT_HTTP, TRANSPORT_MTLS, TRANSPORT_SSH = "http", "mtls", "ssh"
SUPPORTED_WRITABLE = frozenset({TRANSPORT_HTTP, TRANSPORT_MTLS})

@dataclass(frozen=True)
class HttpTransport:
    id: str = TRANSPORT_HTTP
    display_name: str = "HTTP"
    is_tls: bool = False
    def base_scheme(self) -> str: return "http"
    def ssl_context(self): return None

@dataclass(frozen=True)
class MtlsTransport:
    id: str = TRANSPORT_MTLS
    display_name: str = "HTTPS + mTLS"
    is_tls: bool = True
    def base_scheme(self) -> str:
        from app.services.node_mtls import node_agent_base_scheme
        return node_agent_base_scheme(mtls_enabled=True)
    def ssl_context(self):
        from app.services.node_mtls import build_node_agent_ssl_context
        return build_node_agent_ssl_context(mtls_enabled=True)

def get_transport(node) -> NodeTransport:
    raw = (getattr(node, "transport", None) or TRANSPORT_HTTP).strip().lower()
    if raw == TRANSPORT_HTTP: return HttpTransport()
    if raw == TRANSPORT_MTLS: return MtlsTransport()
    raise ValueError(f"unsupported node transport: {raw}")

def apply_transport_value(node, transport: str) -> None:
    t = (transport or "").strip().lower()
    if t == TRANSPORT_SSH:
        raise ValueError("transport_not_implemented")
    if t not in SUPPORTED_WRITABLE:
        raise ValueError(f"unsupported transport: {t}")
    node.transport = t
    sync_mtls_flag(node)
```

- [ ] **Step 4: Model + migration**

In `Node` after `mtls_enabled`:

```python
transport: Mapped[str] = mapped_column(String(16), default="http")
```

In `database.py`:

```python
def _migrate_nodes_transport() -> None:
    inspector = inspect(engine)
    if "nodes" not in inspector.get_table_names():
        return
    cols = {col["name"] for col in inspector.get_columns("nodes")}
    with engine.begin() as conn:
        if "transport" not in cols:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN transport VARCHAR(16) DEFAULT 'http'"))
            logger.info("DB migration: added nodes.transport")
        # Backfill every boot is idempotent: mtls_enabled → mtls, else http
        conn.execute(text(
            "UPDATE nodes SET transport = 'mtls' WHERE mtls_enabled = 1 AND (transport IS NULL OR transport = '' OR transport = 'http')"
        ))
        conn.execute(text(
            "UPDATE nodes SET transport = 'http' WHERE (mtls_enabled = 0 OR mtls_enabled IS NULL) AND transport = 'mtls'"
        ))
        # Prefer one-shot backfill only when column just added; if re-run safe:
        # On first add, set from mtls_enabled unconditionally:
        # UPDATE nodes SET transport = CASE WHEN mtls_enabled = 1 THEN 'mtls' ELSE 'http' END
```

**Backfill rule (lock this in):** when column is **first added**, run:

```sql
UPDATE nodes SET transport = CASE WHEN mtls_enabled = 1 THEN 'mtls' ELSE 'http' END
```

Do **not** continuously overwrite user transport on every boot after that (column presence check is enough).

Wire `_migrate_nodes_transport()` next to `_migrate_nodes_mtls_enabled()` in the migrate runner.

- [ ] **Step 5: pytest pass; commit**

```bash
cd backend && python -m pytest tests/test_node_transport.py -v
git add -f backend/app/services/node_transport.py backend/tests/test_node_transport.py \
  backend/app/models.py backend/app/database.py
git commit -m "Add node transport registry and DB column."
```

---

### Task 2: Provision + API (PATCH transport, list, DTO)

**Files:**
- Modify: `backend/app/services/node_mtls_provision.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/nodes.py`
- Modify: `backend/app/routers/tg_mini/helpers.py` (include `transport` in node payload)
- Create/Modify: `backend/tests/test_node_transport_api.py` (or extend existing nodes router tests)

**Interfaces:**
- Consumes: `apply_transport_value`, `list_transports`, `enable_mtls` / `disable_mtls`
- Produces: DTO field `transport`; routes below

- [ ] **Step 1: Failing API tests**

```python
def test_patch_transport_ssh_returns_400(client, admin_headers, remote_node):
    r = client.patch(f"/api/nodes/{remote_node.id}/transport",
                     json={"transport": "ssh"}, headers=admin_headers)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail == "transport_not_implemented" or detail.get("code") == "transport_not_implemented"
    # reload node — still previous transport

def test_patch_transport_http_to_mtls_proxy_flag_only(client, ...):
    # proxy node: transport becomes mtls, mtls_enabled True
    ...

def test_get_transports(client, admin_headers):
    r = client.get("/api/nodes/transports", headers=admin_headers)
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()["items"]]
    assert ids == ["http", "mtls", "ssh"]
```

Match existing test client fixtures (`conftest` / nodes tests). Prefer `detail: {"code": "transport_not_implemented", "message": "..."}` for consistency with link errors; if project uses plain string details elsewhere for 400, use:

```python
raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "transport_not_implemented", "message": "SSH transport ещё не реализован"})
```

- [ ] **Step 2: Provision sync**

In `enable_mtls` / `_enable_proxy_mtls_flag` / `disable_mtls` wherever `node.mtls_enabled = True/False`:

```python
node.transport = "mtls"  # or "http"
node.mtls_enabled = True  # keep both in sync
# or: apply_transport_value(node, "mtls") then continue provision
```

Prefer calling `apply_transport_value` **before** cert work for enable, and at start of disable — but enable already raises if `mtls_enabled`; update those guards to check `transport == "mtls"` **or** keep checking `mtls_enabled` after sync.

- [ ] **Step 3: Schemas + router**

```python
# schemas
class NodeTransportItem(BaseModel):
    id: str
    label: str
    available: bool

class NodeTransportsResponse(BaseModel):
    items: list[NodeTransportItem]

class NodeTransportUpdate(BaseModel):
    transport: str

# NodeResponse
transport: str = "http"
mtls_enabled: bool = False  # derived when building response
```

DTO builder (wherever `NodeResponse` is built — `nodes.py` ~line 158):

```python
transport = "http" if node.is_local else (getattr(node, "transport", None) or ("mtls" if node.mtls_enabled else "http"))
mtls_enabled = False if node.is_local else (transport == "mtls")
```

Routes (register **before** `/{node_id}` catch-alls if needed):

```python
@router.get("/transports", response_model=NodeTransportsResponse)
def list_node_transports(_: User = Depends(require_admin)):
    return NodeTransportsResponse(items=[... from list_transports() ...])

@router.patch("/{node_id}/transport", response_model=NodeResponse)
def patch_node_transport(node_id: int, body: NodeTransportUpdate, ...):
    # local → 400
    # ssh → 400 transport_not_implemented
    # http → disable_mtls(db, node) if currently mtls else apply http
    # mtls → enable_mtls(db, node, admin) if not already
```

**Important:** For `http`↔`mtls`, reuse `enable_mtls` / `disable_mtls` so VPN cert provision and proxy flag-only behavior stay identical. Do not reimplement provision in the PATCH handler.

- [ ] **Step 4: pytest; commit**

```bash
git commit -m "Expose node transport PATCH API and sync provision flags."
```

---

### Task 3: Adapters + health `expected_tls`

**Files:**
- Modify: `backend/app/services/node_manager.py` (adapter factory + `expected_tls`)
- Modify: `backend/app/services/node_adapter.py` / `proxy_node_adapter.py` if they take raw bool — pass `get_transport(node).is_tls` as today's `mtls_enabled=`
- Modify: any create-node defaults to set `transport="http"`
- Test: extend `test_node_transport.py` or health meta test asserting `expected_tls` follows transport

- [ ] **Step 1: Failing test** — node with `transport=mtls` yields `expected_tls=True` in health meta path (unit with fake node).

- [ ] **Step 2: Wire `get_transport`**

In `node_manager` where adapters are constructed (~253, 278, 411):

```python
from app.services.node_transport import get_transport
tr = get_transport(node)
RemoteNodeAdapter(..., mtls_enabled=tr.is_tls)
```

```python
expected_tls = (not node.is_local) and get_transport(node).is_tls
```

If `get_transport` raises (corrupt DB), treat as link error / offline with clear message — do not crash the whole health worker loop (catch per node).

- [ ] **Step 3: pytest relevant suites; commit**

```bash
git commit -m "Route node adapters and expected_tls through transport registry."
```

---

### Task 4: Frontend picker + badge + TG

**Files:**
- Modify: `frontend/src/types.ts` — `transport: 'http' | 'mtls' | 'ssh'` on Node
- Modify: `frontend/src/api/nodes.ts` — `listNodeTransports()`, `patchNodeTransport(id, transport)`
- Modify: `frontend/src/components/nodes/NodeTransportBadge.tsx`
- Modify: `frontend/src/components/nodes/NodeActions.tsx` (or parent that owns enable/disable) — select primary
- Modify: `frontend/src/pages/NodesPage.tsx` / bulk filters using `mtls_enabled` — keep working via derived field **or** switch to `transport === 'mtls'`
- Modify: `frontend/src/tg-mini/pages/Nodes.tsx`
- Test: small vitest for badge label mapping if pattern exists; else manual check list in CHANGELOG

- [ ] **Step 1: API + types**

```ts
export type NodeTransportId = 'http' | 'mtls' | 'ssh'

export function listNodeTransports() {
  return apiFetch<{ items: { id: NodeTransportId; label: string; available: boolean }[] }>(
    '/nodes/transports',
  )
}

export function patchNodeTransport(nodeId: number, transport: NodeTransportId) {
  return apiFetch<Node>(`/nodes/${nodeId}/transport`, {
    method: 'PATCH',
    body: JSON.stringify({ transport }),
  })
}
```

- [ ] **Step 2: Badge**

```tsx
const label = node.is_local ? null : ({ http: 'HTTP', mtls: 'mTLS', ssh: 'SSH' }[node.transport] ?? node.transport)
```

- [ ] **Step 3: Picker UI**

Replace or sit above enable/disable mTLS buttons:

- Load transports once (page mount or actions open).
- `<Select>` value=`node.transport`, onChange → `patchNodeTransport`; disable options with `available: false` + title «Скоро».
- On success toast; invalidate nodes query.
- Keep enable/disable as optional thin shortcuts **or** remove if select covers — **prefer remove duplicate buttons** to avoid two UIs (spec allowed optional; plan locks **select only**).

- [ ] **Step 4: Fix bulk “nodes without mtls”** filters to `transport !== 'mtls'` (or keep `!mtls_enabled` since derived).

- [ ] **Step 5: Commit**

```bash
git commit -m "Add node transport picker for VPN and proxy nodes."
```

---

### Task 5: Docs + spec status

**Files:**
- Modify: `CHANGELOG.md` (Unreleased Changed)
- Modify: `docs/superpowers/specs/2026-09-13-node-transport-framework-design.md` — status `implemented` when done

- [ ] **Step 1: CHANGELOG bullet**

```markdown
- Выбор способа связи узла (`transport`: HTTP / mTLS) для VPN и proxy; каркас registry под SSH (stub).
```

- [ ] **Step 2: Commit**

```bash
git add -f CHANGELOG.md docs/superpowers/specs/2026-09-13-node-transport-framework-design.md
git commit -m "Document node transport picker in changelog."
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Column + migration | 1 |
| Registry Http/Mtls/Ssh stub | 1 |
| VPN+proxy same field | 2–4 |
| PATCH + GET transports | 2 |
| SSH no DB write | 2 |
| enable/disable shorthand | 2 |
| Adapters / expected_tls | 3 |
| UI picker + badge + TG | 4 |
| CHANGELOG | 5 |
| No agent version bump | Global |

## Self-review notes

- No real SSH implementation in any task.
- Provision path reused — avoids cert logic drift.
- UI: select-only (no dual enable/disable buttons) locked in Task 4.
