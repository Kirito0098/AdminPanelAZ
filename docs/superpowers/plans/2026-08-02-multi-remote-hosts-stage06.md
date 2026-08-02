# Multi-remote Stage 06 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After profile recreate, patch `.ovpn` on disk; patch WG/Amnezia `Endpoint` on delivery to `hosts[0]`; admin button adds first remote host to `allow-ips.txt`.

**Architecture:** Extend MVP helpers — `patch_openvpn_profiles_on_node` after recreate call sites; `apply_wireguard_endpoint_host` inside `read_profile_file_for_delivery`; `POST …/remote-hosts/allow-first` + UI button.

**Tech Stack:** FastAPI, existing Node adapters, React `AntizapretConfigTab`, pytest + MagicMock.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-multi-remote-hosts-stage06-design.md`
- Depends on MVP multi-remote already on branch
- 06a only after successful `recreate_profiles` — never on PUT remote-hosts; never on HA paths that skip `client.sh 7`
- 06b delivery-only for WG/AWG; do not write WG to disk
- 06c only `hosts[0]`; apply via `write_config_file` + `apply_config_changes` (doall.sh) — no `parse.sh ip` in this codebase
- Never install/run `proxy.sh`
- Commit after each task

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/services/openvpn_remote_hosts.py` | optional: keep OVPN helpers; WG helper may live here or sibling |
| `backend/app/services/wireguard_endpoint.py` | `apply_wireguard_endpoint_host` |
| `backend/app/services/profile_delivery.py` | WG branch in delivery; disk patch helper |
| `backend/app/services/openvpn_profile_repair.py` | recreate + optional hosts patch funnel |
| Call sites: `settings.py`, `background_tasks.py`, `cidr/.../orchestrator.py`, `node_sync/shared_domain.py`, configs/csv/templates callers of repair | post-recreate patch |
| `backend/app/routers/nodes.py` | POST allow-first |
| `frontend/src/api/client.ts` + `AntizapretConfigTab.tsx` | button |
| Tests + docs | coverage + user docs |

---

### Task 1: WG Endpoint helper + delivery (06b)

**Files:**
- Create: `backend/app/services/wireguard_endpoint.py`
- Modify: `backend/app/services/profile_delivery.py`
- Create/Modify: `backend/tests/test_wireguard_endpoint.py`, `backend/tests/test_profile_delivery.py`

**Interfaces:**
- Produces: `apply_wireguard_endpoint_host(content: str, host: str) -> str`
- Consumes: `protocol_key_from_file` from `vpn_profile_visibility` (optional; path heuristics OK)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_wireguard_endpoint.py
from app.services.wireguard_endpoint import apply_wireguard_endpoint_host

SAMPLE = """[Interface]
PrivateKey=abc
[Peer]
Endpoint = 10.0.0.1:51820
AllowedIPs = 0.0.0.0/0
"""


def test_replaces_endpoint_keeps_port():
    out = apply_wireguard_endpoint_host(SAMPLE, "1.2.3.4")
    assert "Endpoint = 1.2.3.4:51820" in out
    assert "10.0.0.1" not in out


def test_empty_host_unchanged():
    assert apply_wireguard_endpoint_host(SAMPLE, "") == SAMPLE


def test_no_endpoint_unchanged():
    body = "[Interface]\nPrivateKey=x\n"
    assert apply_wireguard_endpoint_host(body, "1.1.1.1") == body
```

Also extend `test_profile_delivery.py`:

```python
def test_delivery_patches_wg_endpoint():
    adapter = MagicMock()
    adapter.read_profile_file.return_value = SAMPLE
    out = read_profile_file_for_delivery(
        adapter, "/client/wireguard/vpn/client-wg.conf", ["9.9.9.9", "8.8.8.8"]
    )
    assert "Endpoint = 9.9.9.9:51820" in out
```

- [ ] **Step 2: Implement**

```python
# backend/app/services/wireguard_endpoint.py
import re

_ENDPOINT_RE = re.compile(
    r"^(?P<prefix>\s*Endpoint\s*=\s*)(?P<value>\S+)(?P<suffix>\s*)$",
    re.IGNORECASE | re.MULTILINE,
)


def apply_wireguard_endpoint_host(content: str, host: str) -> str:
    host = (host or "").strip()
    if not host:
        return content

    def _sub(m: re.Match[str]) -> str:
        value = m.group("value")
        # host:port — take port after last ':' (IPv4/hostname only in our product)
        if ":" in value:
            port = value.rsplit(":", 1)[-1]
            if port.isdigit():
                return f"{m.group('prefix')}{host}:{port}{m.group('suffix')}"
        return f"{m.group('prefix')}{host}{m.group('suffix')}"

    new, n = _ENDPOINT_RE.subn(_sub, content, count=1)
    return new if n else content
```

In `profile_delivery.py`:

```python
from app.services.vpn_profile_visibility import protocol_key_from_file
from app.services.wireguard_endpoint import apply_wireguard_endpoint_host

def read_profile_file_for_delivery(adapter, path: str, hosts: list[str]) -> str:
    raw = adapter.read_profile_file(path)
    name = PurePosixPath(path.replace("\\", "/")).name
    if name.lower().endswith(".ovpn"):
        return apply_openvpn_remote_hosts(raw, hosts)
    if hosts:
        proto = protocol_key_from_file(protocol="", path=path)
        if proto in ("wireguard", "amneziawg"):
            return apply_wireguard_endpoint_host(raw, hosts[0])
    return raw
```

Check `protocol_key_from_file` signature — pass whatever it requires; if `protocol` unused when path set, use empty string.

- [ ] **Step 3: pytest PASS** then commit

```bash
git add backend/app/services/wireguard_endpoint.py backend/app/services/profile_delivery.py \
  backend/tests/test_wireguard_endpoint.py backend/tests/test_profile_delivery.py
git commit -m "feat: patch WireGuard Endpoint from remote hosts on delivery"
```

---

### Task 2: Disk patch after recreate (06a)

**Files:**
- Modify: `backend/app/services/profile_delivery.py` (add `patch_openvpn_profiles_on_node`)
- Modify: `backend/app/services/openvpn_profile_repair.py`
- Modify recreate call sites listed below
- Create: `backend/tests/test_patch_openvpn_on_disk.py`

**Interfaces:**
- Produces: `patch_openvpn_profiles_on_node(adapter, hosts: list[str]) -> dict` with keys like `patched`, `warnings`
- Consumes: `apply_openvpn_remote_hosts`, `adapter.list_openvpn_clients` / `get_profile_files` / `read_profile_file` / `write_profile_file`

- [ ] **Step 1: Implement disk patch**

```python
def patch_openvpn_profiles_on_node(adapter, hosts: list[str]) -> dict:
    if not hosts:
        return {"patched": 0, "warnings": []}
    from app.models import VpnType  # or existing enum import path
    patched = 0
    warnings: list[str] = []
    try:
        names = adapter.list_openvpn_clients()
    except Exception as exc:  # noqa: BLE001
        return {"patched": 0, "warnings": [str(exc)]}
    seen_paths: set[str] = set()
    for name in names:
        try:
            files = adapter.get_profile_files(name, VpnType.openvpn)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{name}: {exc}")
            continue
        for item in files:
            path = item.get("path") or ""
            if not path or not path.lower().endswith(".ovpn") or path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                raw = adapter.read_profile_file(path)
                new = apply_openvpn_remote_hosts(raw, hosts)
                if new != raw:
                    adapter.write_profile_file(path, new)
                    patched += 1
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{path}: {exc}")
    return {"patched": patched, "warnings": warnings}
```

Verify `list_openvpn_clients` exists on Local/Remote adapters; if not, use another listing API already on adapter (explore and use the real method name).

- [ ] **Step 2: Funnel helper**

Prefer extending `recreate_openvpn_profiles` in `openvpn_profile_repair.py`:

```python
def recreate_openvpn_profiles(adapter, hosts: list[str] | None = None) -> str:
    output = adapter.recreate_profiles()
    if hosts:
        patch_openvpn_profiles_on_node(adapter, hosts)
    return output
```

Update callers that already have `db`/`node_id` to pass `load_node_remote_hosts(db, node_id)`.

Direct sites still calling `adapter.recreate_profiles()`:
- `settings.recreate_profiles` — after success, load active node hosts + patch
- `background_tasks.task_run_doall` — when recreate runs, need `hosts` or `node_id` param (extend signature from callers that have db)
- `cidr` `_deploy_single_node` — after recreate flag, patch with `parse_hosts_json(node.openvpn_remote_hosts)`
- `shared_domain.apply_shared_domain_to_members` — primary: recreate → patch → then OVPN copy to replicas; replica: after copy → patch with **that replica's** hosts (or primary's list if product wants identical remotes — **use each node's own `openvpn_remote_hosts`**)

**Do not** patch when recreate is skipped (HA replica wipe/restore).

- [ ] **Step 3: Tests**

```python
def test_patch_writes_when_hosts():
    adapter = MagicMock()
    adapter.list_openvpn_clients.return_value = ["alice"]
    adapter.get_profile_files.return_value = [{"path": "/x/alice.ovpn"}]
    adapter.read_profile_file.return_value = "remote 10.0.0.1 1194 udp\n"
    result = patch_openvpn_profiles_on_node(adapter, ["1.1.1.1", "2.2.2.2"])
    assert result["patched"] == 1
    adapter.write_profile_file.assert_called()
    written = adapter.write_profile_file.call_args[0][1]
    assert "remote 1.1.1.1 1194 udp" in written


def test_patch_noop_empty_hosts():
    adapter = MagicMock()
    assert patch_openvpn_profiles_on_node(adapter, [])["patched"] == 0
    adapter.list_openvpn_clients.assert_not_called()
```

- [ ] **Step 4: pytest + commit**

```bash
git commit -m "feat: patch OpenVPN remotes on disk after profile recreate"
```

---

### Task 3: allow-first API + UI (06c)

**Files:**
- Modify: `backend/app/routers/nodes.py`, schemas if needed
- Create: `backend/tests/test_remote_hosts_allow_first.py` (MagicMock)
- Modify: `frontend/src/api/client.ts`, `AntizapretConfigTab.tsx`

**Interfaces:**
- `POST /nodes/{node_id}/remote-hosts/allow-first` → `{ added: bool, host: str, detail?: str }`

- [ ] **Step 1: Service logic (can live in openvpn_remote_hosts or small helper)**

```python
def append_host_to_allow_ips(content: str, host: str) -> tuple[str, bool]:
    lines = content.splitlines()
    existing = {ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")}
    if host in existing:
        return content, False
    body = content.rstrip("\n")
    new = (body + "\n" + host + "\n") if body else (host + "\n")
    return new, True
```

Router:

```python
@router.post("/{node_id}/remote-hosts/allow-first")
def allow_first_remote_host(...):
    # load hosts; 400 if empty
    # adapter.read_config_file("allow-ips.txt")
    # append; write; apply_config_changes() best-effort with warnings
    # action_log
```

- [ ] **Step 2: Tests** — empty→400; add→write+apply; duplicate→added False no write (or write skipped)

- [ ] **Step 3: Frontend**

```typescript
export async function allowFirstRemoteHost(nodeId: number) {
  return apiFetch<{ added: boolean; host: string; detail?: string }>(
    `/nodes/${nodeId}/remote-hosts/allow-first`,
    { method: 'POST' },
  )
}
```

In `ConnectionAddressesCard`: button enabled when `savedRemoteHosts.length > 0`; on click call API; toast success/warning.

- [ ] **Step 4: build + commit**

```bash
git commit -m "feat: add first remote host to allow-ips with one click"
```

---

### Task 4: Docs + CHANGELOG

**Files:** `docs/antizapret-config.md`, `docs/PROJECT_MAP.md`, `CHANGELOG.md`, design status → `implemented`

- [ ] Document 06a/b/c behaviors and `setup.sh` caveat
- [ ] Run focused pytest suite for stage 06 + MVP remote-hosts tests
- [ ] Commit `docs: multi-remote stage 06 disk WG allow-ips`

---

## Self-review

| Spec | Task |
|------|------|
| 06b delivery Endpoint | Task 1 |
| 06a disk after recreate | Task 2 |
| 06c allow-first | Task 3 |
| Docs | Task 4 |
| No proxy install / no 07 | Global Constraints |
