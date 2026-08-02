# Proxy Nodes Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Feature toggle `proxy_nodes` (default off), `Node.node_kind` vpn|proxy, separate `proxy_agent` (:9101) with health/status/destination/mappings, panel adapter + UI for edit/monitor — never install `proxy.sh`.

**Architecture:** Toggle + model guards; `backend/proxy_agent/` FastAPI service; `ProxyNodeAdapter` HTTP clone of RemoteNodeAdapter pattern; Nodes UI badge/CRUD when enabled. NOC join is out of scope (wave 2).

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, existing feature_toggles, React NodesPage, pytest + MagicMock, systemd unit scripts.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-proxy-nodes-wave1-design.md`
- Never install/run `proxy.sh` from panel
- Toggle default **false**; when off, proxy UI hidden and proxy create/proxy-only APIs blocked (handler-level — `/api/nodes` is ALWAYS_ALLOWED)
- Only `node_kind=vpn` can be active / used for VPN configs
- Destination edit = iptables DNAT/SNAT rewrite, not re-run proxy.sh
- Port default 9101 for proxy; Auth X-Node-Key + optional mTLS
- No NOC display_address joining in this plan
- Commit after each task

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/feature_toggles.py` | `proxy_nodes` toggle |
| `backend/app/models.py`, `database.py` | `node_kind`, `destination_ip`, `linked_vpn_node_id` |
| `backend/app/schemas.py`, `routers/nodes.py`, `node_manager.py` | CRUD/activate guards |
| `backend/proxy_agent/` | Agent app: health, status, destination, mappings |
| `systemd/` + `scripts/` | proxy_agent unit/install (mirror node) |
| `backend/app/services/proxy_node_adapter.py` | HTTP client |
| `backend/app/routers/nodes.py` or `proxy_nodes.py` | proxy status/destination/mappings routes |
| `frontend` NodesPage + types + client + modules UI | toggle-aware UI |
| `docs/uzly.md`, PROJECT_MAP, CHANGELOG, install doc | docs |

---

### Task 1: Feature toggle + Node model + activate/create guards

**Files:**
- Modify: `backend/app/services/feature_toggles.py`
- Modify: `backend/app/models.py`, `backend/app/database.py`
- Modify: `backend/app/schemas.py`, `backend/app/routers/nodes.py`, `backend/app/services/node_manager.py`
- Create: `backend/tests/test_proxy_nodes_model.py`

**Interfaces:**
- Toggle key `proxy_nodes`, env `FEATURE_PROXY_NODES_ENABLED`, default False
- `Node.node_kind: str` default `"vpn"`; `destination_ip` optional str; `linked_vpn_node_id` optional int FK
- `is_proxy_nodes_enabled(db) -> bool` helper
- `create_node`: if kind=proxy require toggle; default port 9101; is_local False
- `activate_node` / `get_active_node`: reject or skip `node_kind=proxy`

- [ ] **Step 1: Add toggle** (copy `telegram` style default=False; `api_paths` for future proxy routes under nodes — also document handler guards)

- [ ] **Step 2: Model + migration** TEXT/VARCHAR `node_kind` DEFAULT 'vpn'; nullable destination_ip; linked_vpn_node_id INTEGER NULL

- [ ] **Step 3: Schemas + router** expose kind; create validates; activate returns 400 «Прокси-узел нельзя сделать активным для VPN»

- [ ] **Step 4: Tests** toggle off create proxy blocked; activate proxy rejected; vpn activate ok

- [ ] **Step 5: Commit** `feat: proxy_nodes toggle and node_kind model`

---

### Task 2: proxy_agent service (health, status, destination, mappings)

**Files:**
- Create: `backend/proxy_agent/main.py` (+ small modules for iptables/conntrack if needed)
- Create: `backend/tests/test_proxy_agent_destination.py` (unit, no live net)
- Create: `systemd/adminpanelaz-proxy.service`, `scripts/install-proxy-systemd.sh`, `scripts/systemd-exec-proxy.sh`, `backend/proxy_agent.env.example`

**Interfaces:**
- `GET /health` → `{ "ok": true, "version": "..." }`
- `GET /proxy/status` → `{ "installed": bool, "destination_ip": str|null, "detail": str|null }`
- `PUT /proxy/destination` → `{ "destination_ip": "x.x.x.x" }` → rewrite iptables; 400 bad IP
- `GET /proxy/mappings` → `{ "mappings": [ { "client_ip", ... } ] }` best-effort
- Auth: `X-Node-Key` vs env `PROXY_AGENT_API_KEY` (name clearly); optional mTLS env vars

Destination logic (testable pure functions preferred):
- `detect_proxy_destination(rules_text) -> str|None`
- `rewrite_destination(rules_or_cmd_plan, old_ip, new_ip) -> ...` apply via `iptables` subprocess only in agent runtime; unit-test parsers with fixtures

Detect installed: presence of DNAT rules matching known AZ proxy port set OR SNAT to destination — document heuristic in code comments.

- [ ] **Step 1: Failing unit tests for detect/rewrite**
- [ ] **Step 2: Implement agent + auth**
- [ ] **Step 3: systemd scripts mirroring node_agent**
- [ ] **Step 4: Commit** `feat: add proxy_agent with destination and mappings API`

---

### Task 3: ProxyNodeAdapter + panel proxy API

**Files:**
- Create: `backend/app/services/proxy_node_adapter.py`
- Modify: `node_manager.get_adapter_for_node` — if proxy return ProxyNodeAdapter (or separate `get_proxy_adapter`)
- Modify: `nodes.py` — routes `GET/PUT .../proxy/status`, `PUT .../proxy/destination`, `GET .../proxy/mappings`
- Create: `backend/tests/test_proxy_node_adapter.py`

**Interfaces:**
- `ProxyNodeAdapter.health()`, `.proxy_status()`, `.set_destination(ip)`, `.mappings()`
- Routes require admin + toggle + node_kind=proxy
- Sync `node.destination_ip` on successful PUT destination

- [ ] **Steps:** implement adapter (clone RemoteNodeAdapter HTTP helpers), routes, MagicMock tests, commit `feat: panel ProxyNodeAdapter and proxy node APIs`

---

### Task 4: Frontend UI + types

**Files:**
- Modify: `frontend/src/types.ts`, `api/client.ts`
- Modify: `NodesPage.tsx` (and feature modules UI if toggles listed from API)
- Ensure feature toggle appears in Modules with warning text

**Behavior:**
- When `proxy_nodes` disabled: no add-proxy, no proxy badge affordances
- When enabled: create dialog kind vpn|proxy; proxy default port 9101; badge; detail panel health/status/destination; no Activate for proxy
- Link to AZ proxy.sh docs when `installed=false`
- Never show install-proxy.sh button

- [ ] **Steps:** API client helpers, UI, `npm run build`, commit `feat: UI for proxy nodes behind feature toggle`

---

### Task 5: Docs + CHANGELOG + acceptance notes

**Files:** `docs/uzly.md`, `docs/PROJECT_MAP.md`, `CHANGELOG.md`, short `docs/` install note for proxy_agent, design status → implemented

- [ ] Document toggle, node kinds, agent install, DESTINATION=iptables, no proxy.sh from panel, wave 2 NOC later
- [ ] Run focused pytest
- [ ] Commit `docs: proxy nodes wave1`

---

## Self-review

| Spec | Task |
|------|------|
| Toggle default off | 1 |
| node_kind + activate guard | 1 |
| proxy_agent APIs | 2 |
| Adapter + panel API | 3 |
| UI | 4 |
| Docs | 5 |
| No NOC join / no proxy.sh install | Global Constraints |
