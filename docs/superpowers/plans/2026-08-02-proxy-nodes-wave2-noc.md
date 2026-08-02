# Proxy Nodes Wave 2 (NOC enrich) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In NOC monitoring overview, resolve home CLIENT_IP via proxy_agent mappings when session `real_address` is a known proxy IP:port; else mark via_proxy and keep proxy IP for geo.

**Architecture:** `proxy_noc_enrich.py` builds proxy IP set + cached mappings; `monitoring_overview` rewrites lookup endpoints before `lookup_ips_geo` and sets `via_proxy` / `proxy_resolved` on enriched clients.

**Tech Stack:** Existing monitoring_overview, ProxyNodeAdapter, feature toggle `proxy_nodes`, pytest MagicMock.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-proxy-nodes-wave2-noc-design.md`
- Only NOC overview (OpenVPN + WG); not traffic sessions / Telegram
- Match: proxy IP + port == `proxy_sport` → `client_ip`
- Cache TTL 45s in-process
- Toggle off → no enrich / no agent calls
- Never crash overview on agent errors
- Never install proxy.sh
- Commit after each task

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/proxy_noc_enrich.py` | cache, match, resolve endpoint → client_ip |
| `backend/app/services/monitoring_overview.py` | wire enrich before geo |
| `backend/app/schemas.py` | optional via_proxy / proxy_resolved on client models |
| Frontend NOC component | subtle via_proxy indicator |
| Tests + docs | coverage + user docs |

---

### Task 1: proxy_noc_enrich helpers + unit tests

**Files:**
- Create: `backend/app/services/proxy_noc_enrich.py`
- Create: `backend/tests/test_proxy_noc_enrich.py`

**Interfaces:**
- `PROXY_MAPPINGS_CACHE_TTL_SEC = 45`
- `clear_proxy_mappings_cache()` for tests
- `normalize_proxy_host(host: str) -> str | None`  # IPv4 literal preferred
- `match_client_ip(endpoint: str | None, mappings: list[dict], proxy_ips: set[str]) -> tuple[str | None, bool, bool]`
  - returns `(resolved_ip_or_None, via_proxy, proxy_resolved)`
- `get_mappings_for_proxy(adapter_factory, node_id: int, *, now=None) -> list[dict]` with TTL cache

- [ ] **Step 1: Failing tests**

```python
from app.services.proxy_noc_enrich import match_client_ip, clear_proxy_mappings_cache

def test_match_resolves_by_sport():
    mappings = [{"client_ip": "203.0.113.10", "client_port": 50000, "proxy_sport": 40001}]
    ip, via, resolved = match_client_ip("198.51.100.1:40001", mappings, {"198.51.100.1"})
    assert via and resolved and ip == "203.0.113.10"

def test_match_wrong_port_via_unresolved():
    mappings = [{"client_ip": "203.0.113.10", "proxy_sport": 40001}]
    ip, via, resolved = match_client_ip("198.51.100.1:40002", mappings, {"198.51.100.1"})
    assert via and not resolved and ip is None

def test_non_proxy_ip():
    ip, via, resolved = match_client_ip("8.8.8.8:1194", [], {"198.51.100.1"})
    assert not via and not resolved and ip is None
```

- [ ] **Step 2: Implement match + cache** (use `parse_client_endpoint` for parsing)

- [ ] **Step 3: pytest PASS + commit** `feat: proxy NOC mapping match and cache helpers`

---

### Task 2: Wire monitoring_overview + schema fields

**Files:**
- Modify: `backend/app/services/monitoring_overview.py`
- Modify: `backend/app/schemas.py` (`OpenVpnClient` / `WireGuardPeer` enriched fields)
- Create/Modify: `backend/tests/test_monitoring_overview_proxy.py`

**Behavior:**
1. If not `is_enabled("proxy_nodes")` → existing path.
2. Else load proxy nodes from db; for each, try mappings via `get_proxy_adapter` / existing factory (best-effort).
3. For each client/peer endpoint, `match_client_ip`; choose geo lookup IP = resolved or original lookup_ip.
4. Set `via_proxy`, `proxy_resolved` on enriched models.
5. Collect lookup IPs **after** resolution so geo uses home IP when resolved.

- [ ] **Steps:** implement, tests with mocked adapters/db, commit `feat: enrich NOC overview with proxy-resolved client IPs`

---

### Task 3: Frontend NOC indicator + docs

**Files:**
- NOC UI component(s) that render connected clients — show badge/hint when `via_proxy`
- `docs/noc-monitoring.md`, `docs/uzly.md` or `docs/proxy-agent.md`, `CHANGELOG.md`, design status `implemented`

- [ ] **Steps:** minimal UI mark; docs; focused pytest; commit `docs: proxy NOC IP resolution`

---

## Self-review

| Spec | Task |
|------|------|
| Match + cache | 1 |
| Overview wire + fields | 2 |
| UI + docs | 3 |
| Not traffic/Telegram | Global Constraints |
