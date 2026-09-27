# Portal VPN visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public client portal list and download only profile files allowed by the owner's (or global default) `visible_vpn_profiles` policy — same semantics as panel / Mini App / Telegram.

**Architecture:** Filter inside `client_portal._list_files_for_configs` using existing `profile_file_allowed` / `resolve_effective_visible_vpn_profiles`. Download already uses that list as an allowlist, so one choke point covers status UI and `/download`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, existing `vpn_profile_visibility.py`.

**Spec:** `docs/superpowers/specs/2026-09-22-portal-vpn-visibility-design.md`

## Global Constraints

- User-facing copy in Russian
- TDD: failing test first, then minimal production code
- Work on branch `release/2.26.0` (never feature→main)
- Reuse existing visibility policy (no new settings UI)
- Public portal visitor is unauthenticated: never grant “admin sees everything” for the *visitor*; if the **owner** is an admin, `resolve_visible_vpn_profiles` already returns full catalog for that owner — that is OK
- Orphan configs (`owner_id` null / non-int): use global default + feature intersect (not admin full catalog)
- Coerce `owner_id` with `isinstance(..., int)` so MagicMock configs in tests do not invent fake owners
- CHANGELOG `[Unreleased]` note in Russian when done
- Commit when executing via Subagent-Driven Development (each task Step 5)

---

## File map

| File | Responsibility |
|------|----------------|
| Modify: `backend/app/services/client_portal.py` | Resolve owner/default policy; filter files in `_list_files_for_configs` |
| Modify: `backend/tests/test_client_portal.py` | Visibility filter + download allowlist tests; fix MagicMock `owner_id` on existing list test |
| Modify: `docs/podpiska.md` | Portal respects visibility |
| Modify: `CHANGELOG.md` | `[Unreleased]` Changed |

---

### Task 1: Filter portal files by visibility policy

**Files:**
- Modify: `backend/app/services/client_portal.py` (`_list_files_for_configs` ~611–645; add small helpers near it)
- Modify: `backend/tests/test_client_portal.py` (new tests + harden `test_list_files_hides_wireguard_when_feature_disabled`)

**Interfaces:**
- Consumes:
  - `resolve_effective_visible_vpn_profiles(db, user) -> dict[str, list[str]]`
  - `get_default_visible_vpn_profiles(db) -> dict[str, list[str]]`
  - `intersect_policy_with_features(policy, *, openvpn_enabled, wireguard_enabled, amneziawg_enabled, amneziawg2_enabled) -> dict`
  - `feature_flags_from_service() -> dict[str, bool]`
  - `profile_file_allowed(policy, *, protocol, variant, path) -> bool`
  - `User` model via `db.get(User, owner_id)` (or equivalent query)
- Produces: `_list_files_for_configs` returns only visibility-allowed files; download allowlist inherits this

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_client_portal.py`:

```python
def test_list_files_hides_vpn_route_when_owner_visibility_az_only():
    from app.models import User, UserRole
    from app.services.vpn_profile_visibility import policy_to_json

    db = MagicMock()
    owner = User(
        id=5,
        username="novikov",
        password_hash="x",
        role=UserRole.user,
        is_active=True,
        visible_vpn_profiles=policy_to_json(
            {
                "routes": ["az"],
                "protocols": ["openvpn", "wireguard", "amneziawg", "amneziawg2"],
                "openvpn_groups": ["udp_tcp", "udp", "tcp"],
            }
        ),
    )
    cfg = MagicMock()
    cfg.id = 7
    cfg.node_id = 3
    cfg.client_name = "TopTinker"
    cfg.vpn_type = VpnType.openvpn
    cfg.owner_id = 5
    adapter = MagicMock()
    adapter.get_profile_files.return_value = [
        {
            "protocol": "openvpn",
            "variant": "antizapret",
            "path": "/client/openvpn/antizapret/AZ-TopTinker.ovpn",
            "filename": "AZ-TopTinker.ovpn",
        },
        {
            "protocol": "openvpn",
            "variant": "vpn",
            "path": "/client/openvpn/vpn/VPN-TopTinker.ovpn",
            "filename": "VPN-TopTinker.ovpn",
        },
    ]
    node = MagicMock()

    def query_side_effect(model):
        q = MagicMock()
        if model is type(node) or getattr(model, "__name__", "") == "Node":
            q.filter.return_value.first.return_value = node
            return q
        # db.get preferred in implementation; if query(User) used:
        q.filter.return_value.first.return_value = owner
        return q

    db.query.side_effect = query_side_effect
    db.get.side_effect = lambda model, pk: owner if pk == 5 else None

    with (
        patch("app.services.client_portal.get_adapter_for_node", return_value=adapter),
        patch("app.services.feature_guards.get_feature_service") as feats,
    ):
        feats.return_value.is_enabled.return_value = True
        files = portal._list_files_for_configs(db, [cfg])

    paths = [f["path"] for f in files]
    assert "/client/openvpn/antizapret/AZ-TopTinker.ovpn" in paths
    assert "/client/openvpn/vpn/VPN-TopTinker.ovpn" not in paths


def test_read_client_portal_profile_rejects_hidden_vpn_path():
    from fastapi import HTTPException

    db = MagicMock()
    with (
        patch(
            "app.services.client_portal._list_files_for_configs",
            return_value=[
                {"path": "/client/openvpn/antizapret/AZ-TopTinker.ovpn"},
            ],
        ),
        patch("app.services.client_portal._adapter_for_node_id"),
    ):
        try:
            portal._read_client_portal_profile(
                db,
                node_id=1,
                client_name="TopTinker",
                path="/client/openvpn/vpn/VPN-TopTinker.ovpn",
            )
            raised = None
        except HTTPException as exc:
            raised = exc
    assert raised is not None
    assert raised.status_code == 404
```

Also set `cfg.owner_id = None` in existing `test_list_files_hides_wireguard_when_feature_disabled` and patch default policy to full (or leave default FULL via `get_default_visible_vpn_profiles` — if MagicMock `db` breaks default lookup, patch):

```python
cfg.owner_id = None
# inside with-block, also:
patch(
    "app.services.client_portal.get_default_visible_vpn_profiles",
    return_value={
        "routes": ["az", "vpn"],
        "protocols": ["openvpn", "wireguard", "amneziawg", "amneziawg2"],
        "openvpn_groups": ["udp_tcp", "udp", "tcp"],
    },
),
# OR patch whatever helper Task 1 introduces for orphan policy
```

Adjust imports/patches to match the helper name chosen in Step 3 (`_portal_visibility_policy_for_owner` recommended).

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_client_portal.py::test_list_files_hides_vpn_route_when_owner_visibility_az_only \
  tests/test_client_portal.py::test_read_client_portal_profile_rejects_hidden_vpn_path -v
```

Expected: FAIL — VPN file still listed / download not filtered by visibility (or AttributeError if owner resolution incomplete — fix test harness first, then confirm behavioral fail).

- [ ] **Step 3: Minimal implementation**

In `backend/app/services/client_portal.py`, add imports from `app.services.vpn_profile_visibility` and helpers:

```python
def _portal_visibility_policy(db: Session, owner: User | None) -> dict:
    from app.services.vpn_profile_visibility import (
        feature_flags_from_service,
        get_default_visible_vpn_profiles,
        intersect_policy_with_features,
        resolve_effective_visible_vpn_profiles,
    )

    if owner is not None:
        return resolve_effective_visible_vpn_profiles(db, owner)
    flags = feature_flags_from_service()
    return intersect_policy_with_features(
        get_default_visible_vpn_profiles(db),
        openvpn_enabled=flags.get("openvpn", True),
        wireguard_enabled=flags.get("wireguard", True),
        amneziawg_enabled=flags.get("amneziawg", True),
        amneziawg2_enabled=flags.get("awg2", True),
    )


def _owner_for_config(db: Session, config: VpnConfig) -> User | None:
    owner_id = getattr(config, "owner_id", None)
    if not isinstance(owner_id, int):
        return None
    return db.get(User, owner_id)
```

(Import `User` from `app.models` if not already imported.)

Update `_list_files_for_configs`:

```python
def _list_files_for_configs(db: Session, configs: list[VpnConfig]) -> list[dict]:
    if not configs:
        return []
    adapter = _adapter_for_node_id(db, configs[0].node_id)
    out: list[dict] = []
    policy_cache: dict[int | None, dict] = {}
    for config in configs:
        owner = _owner_for_config(db, config)
        cache_key = owner.id if owner is not None else None
        if cache_key not in policy_cache:
            policy_cache[cache_key] = _portal_visibility_policy(db, owner)
        policy = policy_cache[cache_key]
        files = adapter.get_profile_files(config.client_name, config.vpn_type)
        files = enrich_profile_files(config.client_name, files)
        for f in files:
            path = f.get("path") or ""
            if not path:
                continue
            protocol = _portal_protocol_for_file(f, config)
            if not _protocol_feature_enabled(protocol):
                continue
            if not profile_file_allowed(
                policy,
                protocol=protocol,
                variant=f.get("variant", ""),
                path=path,
            ):
                continue
            filename = (
                f.get("download_filename")
                or build_profile_download_filename(
                    config.client_name,
                    protocol=protocol,
                    variant=f.get("variant", ""),
                    path=path,
                )
            )
            label = f.get("name") or filename
            out.append(
                {
                    "path": path,
                    "label": label,
                    "filename": filename,
                    "vpn_type": protocol,
                    "config_id": config.id,
                }
            )
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /opt/AdminPanelAZ/backend && .venv/bin/python -m pytest \
  tests/test_client_portal.py::test_list_files_hides_vpn_route_when_owner_visibility_az_only \
  tests/test_client_portal.py::test_read_client_portal_profile_rejects_hidden_vpn_path \
  tests/test_client_portal.py::test_list_files_hides_wireguard_when_feature_disabled -v
```

Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/client_portal.py backend/tests/test_client_portal.py
git commit -m "$(cat <<'EOF'
feat(portal): honor VPN profile visibility on downloads

EOF
)"
```

---

### Task 2: Docs + CHANGELOG

**Files:**
- Modify: `docs/podpiska.md` (section «Клиентский портал», after the `c_` / `u_` paragraphs ~77–81)
- Modify: `CHANGELOG.md` (`## [Unreleased]` → `### 🔄 Changed`)

**Interfaces:** none

- [ ] **Step 1: Update podpiska.md**

After the paragraph about `c_` / `u_` links (around lines 77–81), add:

```markdown
Список файлов на портале (скачивание и «Импорт в OpenVPN») учитывает **Видимость VPN-профилей** владельца: маршруты AZ/VPN, протоколы и группы OpenVPN — те же настройки, что в **Настройки → Пользователи** (или глобальный default). Скрытый профиль не показывается и не отдаётся по прямой ссылке download (`404`). У конфига без владельца применяется глобальный default видимости.
```

- [ ] **Step 2: CHANGELOG entry**

Under `### 🔄 Changed`:

```markdown
- **Клиентский портал** — список и download конфигов учитывают **Видимость VPN-профилей** владельца (как панель / Mini App / Telegram); скрытый маршрут (например только AZ без VPN) больше не скачивается с портала.
```

- [ ] **Step 3: Commit**

```bash
git add docs/podpiska.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: portal respects VPN profile visibility

EOF
)"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
|---|---|
| Reuse existing visibility (A/1) | Task 1 |
| Filter list + download | Task 1 (`_list_files_for_configs` + existing allowlist) |
| Owner policy for `c_` / owned configs | Task 1 `_owner_for_config` |
| Orphan → global default | Task 1 `_portal_visibility_policy(None)` |
| No visitor-admin bypass | Task 1 (never uses current session user) |
| Tests AZ-only owner | Task 1 |
| Docs + CHANGELOG | Task 2 |
| No new UI | (explicitly skipped) |

No placeholders. Helper names consistent across tasks.
