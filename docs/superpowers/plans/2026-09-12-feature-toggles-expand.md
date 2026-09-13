# Expand Feature Toggles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose every safe-to-disable app section and background worker in «Разделы панели» via the existing `FEATURE_TOGGLES` registry, with default-on upgrades and real UI/API/worker gates.

**Architecture:** Add explicit `FeatureToggleDefinition` entries (same env-backed model). Background workers keep runtime re-checks (prefer `get_feature_service().is_enabled` and/or Settings fields already bound to the same env keys). `nodes` stays under `/api/nodes` `ALWAYS_ALLOWED` and uses handler-level guards like `proxy_nodes`. `panel_ops` gates the settings tab + `/api/system/rebuild` only; `/api/system/restart` stays available for the feature-toggles banner.

**Tech Stack:** FastAPI, `FeatureToggleService`, pydantic Settings (`get_settings` + `cache_clear` on toggle writes), React (`Layout`, `SettingsNav`, `FeatureGuardRoute`, `FeatureTogglesTab`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-feature-toggles-expand-design.md`

## Global Constraints

- New toggles **default = on**, except `cloudflare_ips_update` **default = off** (matches existing `Settings.cloudflare_ips_auto_update: bool = False`).
- Always-on (never add as toggles): auth/session, `/` Конфигурации, Settings → personal, Settings → `modules`.
- Do **not** remove `/api/nodes` from `ALWAYS_ALLOWED_PREFIXES`.
- Do **not** gate `/api/system/restart` with `panel_ops` (banner restart must work).
- Prefer reusing existing env keys already read by `Settings` / workers (`NODE_HEALTH_SYNC_ENABLED`, `CERT_SYNC_ENABLED`, …).
- New env keys only where none exist: `FEATURE_NODES_ENABLED`, `FEATURE_PANEL_OPS_ENABLED`, `FEATURE_KEY_ROTATION_ENABLED`, `FEATURE_ACCESS_EXPIRY_ENABLED`, `FEATURE_CONNECTION_HISTORY_ENABLED`.
- Russian labels/descriptions/`disable_hint` matching existing toggle tone.
- Commit after each task; `git add -f` for paths under `docs/superpowers/` (gitignored).
- Do not invent UX presets / first-run wizard (out of scope).

## File map

| File | Role |
|------|------|
| `backend/app/services/feature_toggles.py` | New definitions; `RESOURCE_PROFILES` toggles/env; `is_nodes_enabled` helper |
| `backend/app/services/feature_guards.py` | Optional `require_module`; keep ALWAYS_ALLOWED as-is |
| `backend/app/routers/nodes.py` | Handler gates for admin mutating when `nodes` off |
| `backend/app/routers/system.py` | Gate `/rebuild` with `panel_ops` |
| `backend/app/services/*_worker.py` / schedulers | Runtime gates for new background keys |
| `backend/app/config.py` | Only if a new Settings field is required (prefer feature service for brand-new flags) |
| `backend/tests/test_feature_toggles_expand.py` | Registry + defaults + profile keys |
| `backend/tests/test_nodes_feature_toggle.py` | Mutating blocked / reads allowed |
| `backend/tests/test_panel_ops_feature_toggle.py` | rebuild gated; restart free |
| `frontend/src/components/Layout.tsx` | `featureKey: 'nodes'` |
| `frontend/src/App.tsx` | `FeatureGuardRoute feature="nodes"` on `/nodes` |
| `frontend/src/components/settings/SettingsNav.tsx` | `panel_ops` settingsTab wiring |
| `frontend/src/components/settings/MonitoringTab.tsx` | Hide `AlertRulesCard` when `alert_rules` off |
| `frontend/src/pages/NodesPage.tsx` | No special case beyond route guard (optional copy) |
| `CHANGELOG.md` | Unreleased note |

---

### Task 1: Registry — new `FeatureToggleDefinition`s + registry tests

**Files:**
- Modify: `backend/app/services/feature_toggles.py` (append definitions before `FEATURE_TOGGLE_BY_KEY`)
- Create: `backend/tests/test_feature_toggles_expand.py`

**Interfaces:**
- Produces keys: `nodes`, `panel_ops`, `node_health`, `cert_sync`, `resource_metrics`, `panel_resource_metrics`, `cidr_scheduler`, `node_sync_reconcile`, `retention`, `key_rotation`, `user_reminders`, `alert_rules`, `noc_reports`, `cloudflare_ips_update`, `access_expiry`, `connection_history`
- Produces helpers later tasks use: definitions only in this task; `is_nodes_enabled` in Task 3

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_feature_toggles_expand.py
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.feature_toggles import (
    FEATURE_TOGGLE_BY_ENV,
    FEATURE_TOGGLE_BY_KEY,
    FEATURE_TOGGLES,
    FRONTEND_PATH_TO_MODULE,
    RESOURCE_PROFILES,
    SETTINGS_TAB_TO_MODULE,
    FeatureToggleService,
)

NEW_APP = ("nodes", "panel_ops")
NEW_BG = (
    "node_health",
    "cert_sync",
    "resource_metrics",
    "panel_resource_metrics",
    "cidr_scheduler",
    "node_sync_reconcile",
    "retention",
    "key_rotation",
    "user_reminders",
    "alert_rules",
    "noc_reports",
    "cloudflare_ips_update",
    "access_expiry",
    "connection_history",
)
ALWAYS_ON_FORBIDDEN = {"modules", "personal", "auth", "dashboard", "configurations"}


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text("", encoding="utf-8")
    return path


def test_new_keys_registered_unique_and_defaults():
    keys = [item.key for item in FEATURE_TOGGLES]
    assert len(keys) == len(set(keys))
    env_keys = [item.env_key for item in FEATURE_TOGGLES]
    assert len(env_keys) == len(set(env_keys))
    for key in NEW_APP + NEW_BG:
        assert key in FEATURE_TOGGLE_BY_KEY
        item = FEATURE_TOGGLE_BY_KEY[key]
        if key == "cloudflare_ips_update":
            assert item.default is False
        else:
            assert item.default is True
        assert key not in ALWAYS_ON_FORBIDDEN


def test_nodes_and_panel_ops_bindings():
    assert FRONTEND_PATH_TO_MODULE["/nodes"] == "nodes"
    assert SETTINGS_TAB_TO_MODULE["panel_ops"] == "panel_ops"
    assert FEATURE_TOGGLE_BY_KEY["nodes"].group == "app_module"
    assert FEATURE_TOGGLE_BY_KEY["panel_ops"].group == "app_module"
    assert FEATURE_TOGGLE_BY_KEY["node_health"].group == "background"


def test_missing_env_defaults_on(env_file: Path):
    svc = FeatureToggleService(env_file)
    assert svc.is_enabled("nodes") is True
    assert svc.is_enabled("access_expiry") is True
    assert svc.is_enabled("cloudflare_ips_update") is False


def test_env_keys_match_existing_settings_where_applicable():
    assert FEATURE_TOGGLE_BY_KEY["node_health"].env_key == "NODE_HEALTH_SYNC_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cert_sync"].env_key == "CERT_SYNC_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["resource_metrics"].env_key == "RESOURCE_METRICS_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["panel_resource_metrics"].env_key == "PANEL_RESOURCE_METRICS_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cidr_scheduler"].env_key == "CIDR_DB_REFRESH_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["node_sync_reconcile"].env_key == "NODE_SYNC_RECONCILE_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["retention"].env_key == "RETENTION_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["user_reminders"].env_key == "SELF_SERVICE_REMINDER_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["alert_rules"].env_key == "ALERT_RULES_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["noc_reports"].env_key == "NOC_REPORT_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["cloudflare_ips_update"].env_key == "CLOUDFLARE_IPS_AUTO_UPDATE"
    assert FEATURE_TOGGLE_BY_KEY["key_rotation"].env_key == "FEATURE_KEY_ROTATION_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["access_expiry"].env_key == "FEATURE_ACCESS_EXPIRY_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["connection_history"].env_key == "FEATURE_CONNECTION_HISTORY_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["nodes"].env_key == "FEATURE_NODES_ENABLED"
    assert FEATURE_TOGGLE_BY_KEY["panel_ops"].env_key == "FEATURE_PANEL_OPS_ENABLED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_feature_toggles_expand.py -v`  
Expected: FAIL (keys missing / ImportError)

- [ ] **Step 3: Add definitions**

Append to `FEATURE_TOGGLES` in `backend/app/services/feature_toggles.py` (after existing items, before the closing `)`):

```python
    FeatureToggleDefinition(
        key="nodes",
        env_key="FEATURE_NODES_ENABLED",
        label="Узлы",
        description="Страница «Узлы»: список VPN/прокси-узлов, ключи, mTLS и обновления агента.",
        icon="🖥️",
        disable_hint="Страница «Узлы» и операции создания/изменения узлов станут недоступны. Фоновый опрос и чтение узлов другими разделами сохраняются.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        frontend_paths=("/nodes",),
    ),
    FeatureToggleDefinition(
        key="panel_ops",
        env_key="FEATURE_PANEL_OPS_ENABLED",
        label="Операции панели",
        description="Вкладка «Операции панели»: пересборка фронтенда и связанные действия.",
        icon="🔄",
        disable_hint="Вкладка «Операции панели» и пересборка из неё станут недоступны. Перезапуск панели из баннера модулей останется доступен.",
        resource_impact_level="minimal",
        default=True,
        group="app_module",
        settings_tabs=("panel_ops",),
        api_prefixes=("/api/system/rebuild",),
    ),
    FeatureToggleDefinition(
        key="node_health",
        env_key="NODE_HEALTH_SYNC_ENABLED",
        label="Опрос health узлов",
        description="Фоновый опрос статуса VPN/прокси-узлов.",
        icon="❤️",
        disable_hint="Статусы узлов перестанут обновляться автоматически.",
        resource_impact_level="medium",
        resource_savings="Периодические HTTP-запросы к агентам узлов.",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cert_sync",
        env_key="CERT_SYNC_ENABLED",
        label="Синхронизация сертификатов OpenVPN",
        description="Фоновая подтяжка сроков сертификатов OpenVPN с узлов в БД.",
        icon="📜",
        disable_hint="Сроки сертификатов в БД перестанут синхронизироваться с узлами.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="resource_metrics",
        env_key="RESOURCE_METRICS_ENABLED",
        label="Метрики ресурсов VPN-узлов",
        description="Сбор CPU/RAM и связанных метрик с VPN-узлов.",
        icon="📉",
        disable_hint="Графики и история нагрузки узлов перестанут обновляться.",
        resource_impact_level="medium",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="panel_resource_metrics",
        env_key="PANEL_RESOURCE_METRICS_ENABLED",
        label="Метрики ресурсов панели",
        description="Сбор CPU/RAM процесса панели для карточек профилей и мониторинга.",
        icon="📊",
        disable_hint="Живые замеры RAM панели на профилях перестанут обновляться.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cidr_scheduler",
        env_key="CIDR_DB_REFRESH_ENABLED",
        label="Планировщик CIDR DB",
        description="Ночное/периодическое автообновление CIDR DB.",
        icon="🗓️",
        disable_hint="Автообновление CIDR DB по расписанию будет отключено (ручной pipeline останется при включённой маршрутизации).",
        resource_impact_level="high",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="node_sync_reconcile",
        env_key="NODE_SYNC_RECONCILE_ENABLED",
        label="Сверка Node Sync",
        description="Фоновый reconcile групп синхронизации узлов.",
        icon="🔁",
        disable_hint="Автоматическая сверка Node Sync будет отключена.",
        resource_impact_level="medium",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="retention",
        env_key="RETENTION_ENABLED",
        label="Автоочистка БД (retention)",
        description="Удаление старых сэмплов трафика, логов и метрик по срокам из Обслуживания.",
        icon="🗑️",
        disable_hint="Автоочистка таблиц истории будет остановлена.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="key_rotation",
        env_key="FEATURE_KEY_ROTATION_ENABLED",
        label="Ротация API-ключей узлов",
        description="Фоновая ротация API-ключей узлов по сроку (если задан интервал в настройках).",
        icon="🔑",
        disable_hint="Авторотация API-ключей узлов будет отключена (ручная ротация на странице Узлы — при включённом модуле Узлы).",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="user_reminders",
        env_key="SELF_SERVICE_REMINDER_ENABLED",
        label="Напоминания self-service",
        description="Фоновые напоминания пользователям (сертификаты / трафик) через self-service каналы.",
        icon="🔔",
        disable_hint="Автонапоминания self-service будут отключены.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="alert_rules",
        env_key="ALERT_RULES_ENABLED",
        label="Правила алертов",
        description="Фоновая оценка правил алертов (доставка зависит от Telegram).",
        icon="🚨",
        disable_hint="Правила алертов не будут оцениваться; карточка в мониторинге скроется.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="noc_reports",
        env_key="NOC_REPORT_ENABLED",
        label="NOC-отчёты по расписанию",
        description="Ежедневные/еженедельные NOC-отчёты (обычно в Telegram).",
        icon="📰",
        disable_hint="Планировщик NOC-отчётов будет отключён.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="cloudflare_ips_update",
        env_key="CLOUDFLARE_IPS_AUTO_UPDATE",
        label="Автообновление Cloudflare IP",
        description="Периодическое обновление списков IP Cloudflare для proxy-mode.",
        icon="☁️",
        disable_hint="Списки Cloudflare IP не будут обновляться автоматически.",
        resource_impact_level="low",
        default=False,
        group="background",
    ),
    FeatureToggleDefinition(
        key="access_expiry",
        env_key="FEATURE_ACCESS_EXPIRY_ENABLED",
        label="Автоистечение access-until",
        description="Фоновое применение блокировок по сроку access-until / unlock.",
        icon="⏳",
        disable_hint="Истёкший access-until не будет применяться автоматически.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
    FeatureToggleDefinition(
        key="connection_history",
        env_key="FEATURE_CONNECTION_HISTORY_ENABLED",
        label="История подключений (сэмплы)",
        description="Фоновый сбор счётчиков подключений для NOC-графиков.",
        icon="📈",
        disable_hint="Сэмплы числа подключений перестанут записываться.",
        resource_impact_level="low",
        default=True,
        group="background",
    ),
```

**Do not** set `settings_tabs=("monitoring",)` on `alert_rules` — `SETTINGS_TAB_TO_MODULE` is 1:1 and `monitoring` is already owned by `resource_monitor`. Hide the alert card in UI via `isEnabled('alert_rules')` only (Task 5).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_feature_toggles_expand.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/feature_toggles.py backend/tests/test_feature_toggles_expand.py
git commit -m "$(cat <<'EOF'
Add feature toggle registry entries for nodes, panel ops, and background workers.

EOF
)"
```

---

### Task 2: Resource profiles include new background keys

**Files:**
- Modify: `backend/app/services/feature_toggles.py` (`RESOURCE_PROFILES`)
- Modify: `backend/tests/test_feature_toggles_expand.py` (add profile assertions)

**Interfaces:**
- Consumes: new toggle keys from Task 1
- Produces: `apply_resource_profile` writes env for new keys via existing loop over `toggles` + `env`

- [ ] **Step 1: Extend tests**

```python
def test_resource_profiles_cover_new_background_keys():
    for profile_key, meta in RESOURCE_PROFILES.items():
        toggles = meta["toggles"]
        for key in NEW_BG:
            assert key in toggles, f"{profile_key} missing {key}"
        if profile_key == "minimal":
            assert toggles["node_health"] is False
            assert toggles["cert_sync"] is False
            assert toggles["resource_metrics"] is False
            assert toggles["panel_resource_metrics"] is False
            assert toggles["cidr_scheduler"] is False
            assert toggles["node_sync_reconcile"] is False
            assert toggles["noc_reports"] is False
            assert toggles["alert_rules"] is False
            assert toggles["connection_history"] is False
            # keep safety-ish on
            assert toggles["retention"] is True
            assert toggles["access_expiry"] is True
            assert toggles["key_rotation"] is True
            assert toggles["user_reminders"] is False
            assert toggles["cloudflare_ips_update"] is False
        else:
            assert toggles["node_health"] is True
            assert toggles["resource_metrics"] is True
            assert toggles["cidr_scheduler"] is (profile_key == "full")
```

For `standard`, set `cidr_scheduler=False` (already true via env `CIDR_DB_REFRESH_ENABLED=false`). For `full`, `cidr_scheduler=True`.

- [ ] **Step 2: Run to see fail**

Run: `python -m pytest tests/test_feature_toggles_expand.py::test_resource_profiles_cover_new_background_keys -v`  
Expected: FAIL missing keys

- [ ] **Step 3: Update each profile's `toggles` and `env` dicts**

Example additions for **minimal** `toggles` (merge into existing dict):

```python
"node_health": False,
"cert_sync": False,
"resource_metrics": False,
"panel_resource_metrics": False,
"cidr_scheduler": False,
"node_sync_reconcile": False,
"retention": True,
"key_rotation": True,
"user_reminders": False,
"alert_rules": False,
"noc_reports": False,
"cloudflare_ips_update": False,
"access_expiry": True,
"connection_history": False,
```

Mirror into `env` where Settings already uses the same key (`NODE_HEALTH_SYNC_ENABLED`, etc.). For `FEATURE_*` keys also set `"FEATURE_KEY_ROTATION_ENABLED": "true"` etc. in env maps.

**standard:** background new keys True except `cidr_scheduler=False`, `cloudflare_ips_update=False`, keep existing warper/telegram/proxy off.  
**full:** all new background True except `cloudflare_ips_update=False` (operator must opt in), `cidr_scheduler=True`.

Do **not** put `nodes` / `panel_ops` into profile toggles (profiles stay resource-oriented).

- [ ] **Step 4: Pass tests + commit**

```bash
cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_feature_toggles_expand.py -v
git add backend/app/services/feature_toggles.py backend/tests/test_feature_toggles_expand.py
git commit -m "$(cat <<'EOF'
Extend resource profiles with new background feature toggle keys.

EOF
)"
```

---

### Task 3: `nodes` helper + mutating handler gates

**Files:**
- Modify: `backend/app/services/feature_toggles.py` (add `is_nodes_enabled`)
- Modify: `backend/app/routers/nodes.py`
- Create: `backend/tests/test_nodes_feature_toggle.py`

**Interfaces:**
- Produces: `is_nodes_enabled(db=None) -> bool` (same pattern as `is_proxy_nodes_enabled`)
- Allowed when `nodes=false` (read/ops needed by rest of panel):  
  `GET ""`, `GET /geo-routing-hint`, `GET /active`, `GET /mtls/status`, `GET /{id}`, `POST /{id}/health`, `GET /{id}/proxy/*` (still also needs `proxy_nodes`), `GET /{id}/remote-hosts`, `GET /{id}/openvpn-multihome`, `GET /{id}/resource-history`, `GET /{id}/updates`
- Blocked when `nodes=false`:  
  `POST ""`, `PUT /{id}`, `DELETE /{id}`, `POST /update-roll`, `POST /{id}/enable-mtls`, `POST /{id}/disable-mtls`, `PUT /{id}/remote-hosts`, `POST /{id}/allow-first-remote-host`, `PUT /{id}/openvpn-multihome`, `POST /{id}/rotate-key`, `POST /{id}/activate`, `POST /{id}/update`, `POST /{id}/restart-agent`, and proxy **mutating** already gated by `proxy_nodes` (also require `nodes` for create proxy card)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_nodes_feature_toggle.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.feature_toggles import FeatureToggleService, is_nodes_enabled


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    return p


def test_is_nodes_enabled_defaults_true(env_file: Path, monkeypatch):
    svc = FeatureToggleService(env_file)
    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: svc,
    )
    assert is_nodes_enabled(None) is True
    env_file.write_text("FEATURE_NODES_ENABLED=false\n", encoding="utf-8")
    svc._invalidate_env_map()
    assert is_nodes_enabled(None) is False


def test_create_node_blocked_when_nodes_disabled(monkeypatch):
    from app.routers import nodes as nodes_router

    monkeypatch.setattr(nodes_router, "is_nodes_enabled", lambda _db: False)
    with pytest.raises(HTTPException) as ei:
        # Call the internal guard helper once you extract `_require_nodes_module(db)`
        nodes_router._require_nodes_module(MagicMock())
    assert ei.value.status_code == 403
```

After implementing `_require_nodes_module`, expand with one TestClient create-node test mirroring `test_proxy_nodes_model.py` style if fixtures allow; otherwise unit-test the helper + spot-check 2 endpoints.

- [ ] **Step 2: Implement helper**

```python
# at end of feature_toggles.py next to is_proxy_nodes_enabled

def is_nodes_enabled(db=None) -> bool:
    """Admin Nodes UI/mutations gate. ``/api/nodes`` stays ALWAYS_ALLOWED."""
    from app.services.feature_guards import get_feature_service

    _ = db
    return get_feature_service().is_enabled("nodes")
```

In `nodes.py`:

```python
from app.services.feature_toggles import is_nodes_enabled, is_proxy_nodes_enabled
from app.services.feature_guards import module_disabled_message

def _require_nodes_module(db) -> None:
    if not is_nodes_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=module_disabled_message("nodes"),
        )
```

Call `_require_nodes_module(db)` at the start of each blocked handler listed above. For `create_node`, call it for **all** kinds (vpn and proxy); keep existing `proxy_nodes` check for proxy kind.

- [ ] **Step 3: Pass tests + commit**

```bash
cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_nodes_feature_toggle.py tests/test_proxy_nodes_model.py -v
git add backend/app/services/feature_toggles.py backend/app/routers/nodes.py backend/tests/test_nodes_feature_toggle.py
git commit -m "$(cat <<'EOF'
Gate admin node mutations behind the nodes feature toggle.

EOF
)"
```

---

### Task 4: Background worker runtime gates

**Files (modify each loop’s enable check):**
- `backend/app/services/node_health_worker.py` — already uses `settings.node_health_sync_enabled` (same env as toggle). Verify toggle write clears settings cache (already on PUT toggles). No code change if Settings field is enough; add comment linking to feature key `node_health`.
- `backend/app/services/cert_sync_worker.py` — same via `cert_sync_enabled`
- `backend/app/services/panel_resource_metrics_worker.py` — `panel_resource_metrics_enabled`
- resource metrics worker file (find `run_resource_metrics` / similar) — `resource_metrics_enabled`
- `backend/app/services/cidr/cidr_scheduler.py` — `cidr_db_refresh_enabled`
- `backend/app/services/node_sync/reconcile_worker.py` — `node_sync_reconcile_enabled`
- `backend/app/services/retention_worker.py` — `RETENTION_ENABLED` / settings
- `backend/app/services/user_reminder_worker.py` — `self_service_reminder_enabled`
- `backend/app/services/alert_rule_worker.py` — already `alert_rules_enabled` + telegram
- `backend/app/services/noc_report_scheduler.py` — `noc_report_enabled`
- Cloudflare IPs scheduler — `cloudflare_ips_auto_update`
- `backend/app/services/node_key_rotation.py` — **add** `get_feature_service().is_enabled("key_rotation")`
- `backend/app/services/access_expiry_worker.py` — **add** `is_enabled("access_expiry")`
- `backend/app/services/connection_history_worker.py` — **add** `is_enabled("connection_history")` in addition to existing checks

**Interfaces:**
- Consumes: feature keys from Task 1; Settings fields bound to same env where applicable
- Produces: loops skip work when toggle off without process restart

- [ ] **Step 1: Failing unit tests for the three new FEATURE_* gates**

```python
# add to test_feature_toggles_expand.py or test_background_toggle_gates.py

def test_key_rotation_respects_feature_toggle(env_file: Path, monkeypatch):
    from app.services import node_key_rotation as mod

    env_file.write_text("FEATURE_KEY_ROTATION_ENABLED=false\n", encoding="utf-8")
    svc = FeatureToggleService(env_file)
    monkeypatch.setattr("app.services.feature_guards.get_feature_service", lambda: svc)
    # Expose or test the internal predicate once added, e.g. mod._is_key_rotation_enabled()
    assert mod._is_key_rotation_enabled() is False
```

Mirror for `access_expiry_worker._is_access_expiry_enabled` and `connection_history_worker` predicate.

- [ ] **Step 2: Implement predicates**

`node_key_rotation.py`:

```python
def _is_key_rotation_enabled() -> bool:
    from app.services.feature_guards import get_feature_service
    if not get_feature_service().is_enabled("key_rotation"):
        return False
    return get_settings().node_api_key_rotation_days > 0
```

Use this in `run_node_key_rotation_loop` instead of only checking days.

`access_expiry_worker.py`:

```python
def _is_access_expiry_enabled() -> bool:
    from app.services.feature_guards import get_feature_service
    return get_feature_service().is_enabled("access_expiry")
```

Skip tick body when False.

`connection_history_worker.py`:

```python
def _is_connection_history_enabled() -> bool:
    from app.services.feature_guards import get_feature_service
    return get_feature_service().is_enabled("connection_history")
```

Require `_is_connection_history_enabled()` and existing resource_metrics / resource_monitor checks.

- [ ] **Step 3: Audit remaining workers** — for each Settings-backed env, confirm pydantic field `validation_alias` / env name matches toggle `env_key`. If a worker only checked at process start, switch to per-tick Settings/`is_enabled` like peers.

- [ ] **Step 4: Run targeted tests + commit**

```bash
cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_feature_toggles_expand.py tests/test_background_toggle_gates.py -v
git add backend/app/services/node_key_rotation.py backend/app/services/access_expiry_worker.py backend/app/services/connection_history_worker.py backend/tests/
git commit -m "$(cat <<'EOF'
Wire background workers to new feature toggle runtime gates.

EOF
)"
```

---

### Task 5: `panel_ops` API + frontend settings/nav + nodes UI

**Files:**
- Modify: `backend/app/routers/system.py` (`rebuild_panel`)
- Create: `backend/tests/test_panel_ops_feature_toggle.py`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/settings/SettingsNav.tsx`
- Modify: `frontend/src/components/settings/MonitoringTab.tsx`
- Modify: `frontend/src/components/settings/PanelOpsTab.tsx` (optional note when rebuild-only)

**Interfaces:**
- `panel_ops` settings tab via `SETTINGS_TAB_TO_MODULE["panel_ops"]` (already from definition)
- `SettingsNav`: add `settingsTab: 'panel_ops'` requires extending `SettingsTabKey`

- [ ] **Step 1: Backend failing test**

```python
def test_rebuild_requires_panel_ops(monkeypatch):
    from app.routers import system as system_router
    from app.services.feature_guards import module_disabled_message

    monkeypatch.setattr(
        "app.services.feature_guards.get_feature_service",
        lambda: type("S", (), {"is_enabled": staticmethod(lambda k: k != "panel_ops")})(),
    )
    # Prefer extracting _require_panel_ops() and unit-testing it, or TestClient on /system/rebuild
```

Implement at top of `rebuild_panel`:

```python
from app.services.feature_guards import get_feature_service, module_disabled_message

if not get_feature_service().is_enabled("panel_ops"):
    raise HTTPException(status_code=403, detail=module_disabled_message("panel_ops"))
```

Do **not** add the same check to `restart_panel`.

Because `/api/system/rebuild` is listed as `api_prefixes` on the definition, middleware may already block it once the registry maps `PREFIX_TO_MODULES`. Verify with `check_path_access("/api/system/rebuild", service=svc)` in tests — if middleware covers it, handler check is defense-in-depth (keep both).

Note: `/api/settings` is ALWAYS_ALLOWED but rebuild is under `/api/system` — middleware path mapping applies.

- [ ] **Step 2: Frontend SettingsNav**

```typescript
// SettingsTabKey union — add:
| 'panel_ops'

// nav item:
navItem('panel_ops', RefreshCw, { settingsTab: 'panel_ops' }),
```

`isNavItemVisible` already hides items when `settingsTab` maps to a disabled module via `isTabEnabled`.

- [ ] **Step 3: Layout + App**

```typescript
// Layout.tsx NAV item Узлы:
{ to: '/nodes', label: 'Узлы', icon: Server, end: false, adminOnly: true, featureKey: 'nodes' },

// App.tsx:
<Route path="nodes" element={<LazyPage><FeatureGuardRoute feature="nodes"><NodesPage /></FeatureGuardRoute></LazyPage>} />
```

- [ ] **Step 4: MonitoringTab**

```tsx
import { useFeatureModules } from '@/context/FeatureModulesContext'

const { isEnabled } = useFeatureModules()
// ...
{isEnabled('alert_rules') && <AlertRulesCard />}
```

- [ ] **Step 5: tsc + backend tests + commit**

```bash
cd /opt/AdminPanelAZ/backend && python -m pytest tests/test_panel_ops_feature_toggle.py tests/test_feature_toggles_routing_split.py -v
cd /opt/AdminPanelAZ/frontend && npx tsc --noEmit -p tsconfig.json
git add backend/app/routers/system.py backend/tests/test_panel_ops_feature_toggle.py \
  frontend/src/components/Layout.tsx frontend/src/App.tsx \
  frontend/src/components/settings/SettingsNav.tsx \
  frontend/src/components/settings/MonitoringTab.tsx
git commit -m "$(cat <<'EOF'
Wire nodes and panel_ops toggles into UI routes and rebuild API.

EOF
)"
```

---

### Task 6: Changelog + manual smoke checklist + spec status

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/superpowers/specs/2026-09-12-feature-toggles-expand-design.md` (status → implemented when done)
- Optional: short note in `docs/nastrojki/` only if an existing modules doc exists — otherwise skip (YAGNI)

- [ ] **Step 1: Changelog under Unreleased**

```markdown
### Added
- Расширены «Разделы панели»: тогглы Узлы, Операции панели и фоновых воркеров (health, cert sync, metrics, CIDR scheduler, retention, alerts, NOC reports, access-until expiry, …).
```

- [ ] **Step 2: Manual smoke (document results in commit message or PR notes)**

1. Open Настройки → Разделы панели — new rows visible; search «узлы», «cidr», «алерт».  
2. Disable `nodes` → save → menu Узлы gone; `/nodes` shows «Раздел отключён»; dashboard still loads; create-node API 403.  
3. Disable `panel_ops` → tab hidden; rebuild 403; restart from modules banner still works.  
4. Disable `node_health` → logs show skip debug (or no health stamp updates).  
5. Fresh empty `.env` → `is_enabled` true for new keys except cloudflare.  
6. Apply Minimal profile → heavy background keys false in `.env`.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git add -f docs/superpowers/specs/2026-09-12-feature-toggles-expand-design.md
git commit -m "$(cat <<'EOF'
Document expanded feature toggles in changelog.

EOF
)"
```

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| Expand app_module (`nodes`, `panel_ops`) | 1, 3, 5 |
| Expand background inventory | 1, 4 |
| default on (cloudflare exception) | 1 |
| Always-on not in registry | 1 tests |
| `/api/nodes` ALWAYS_ALLOWED + mutating gates | 3 |
| panel_ops hide tab; restart banner free | 5 |
| Resource profiles updated | 2 |
| AlertRulesCard hide | 5 |
| Tests + tsc | 1–5 |
| Changelog | 6 |
| No presets / no autogen | Global Constraints |

## Placeholder / consistency notes

- Env key names for Settings-backed toggles must match pydantic Settings env exactly (`NODE_HEALTH_SYNC_ENABLED`, not a parallel `FEATURE_NODE_HEALTH_*`).
- Never bind two toggles to the same `settings_tabs` entry (`monitoring` stays `resource_monitor`).
- `awg2_expire` / `backup_scheduler` / traffic collector remain tied to existing modules (no new keys).
