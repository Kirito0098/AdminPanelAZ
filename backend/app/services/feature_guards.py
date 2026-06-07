"""Route guards for disabled application modules (AdminAntizapret 1.9.0 parity)."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.services.feature_toggles import (
    FEATURE_TOGGLE_BY_KEY,
    FEATURE_TOGGLES,
    FeatureToggleService,
)

ALWAYS_ALLOWED_PREFIXES = (
    "/api/health",
    "/api/feature-modules",
    "/api/feature-toggles",
    "/api/auth/login",
    "/api/auth/login/json",
    "/api/auth/captcha",
    "/api/auth/me",
    "/api/auth/change-password",
    "/api/ip-blocked",
    "/api/public/",
    "/api/settings",
    "/api/users",
    "/api/nodes",
    "/api/configs",
    "/api/monitoring/summary",
    "/api/system/viewer-access",
)

PATH_TO_MODULES: dict[str, tuple[str, ...]] = {}
PREFIX_TO_MODULES: dict[str, tuple[str, ...]] = {}
SHARED_PREFIX_TO_MODULES: dict[str, tuple[str, ...]] = {
    "/api/routing/cidr-db/tasks/": ("routing", "diagnostics_tests"),
}

for _item in FEATURE_TOGGLES:
    for _path in _item.api_paths:
        existing = PATH_TO_MODULES.get(_path, ())
        if _item.key not in existing:
            PATH_TO_MODULES[_path] = existing + (_item.key,)
    for _prefix in _item.api_prefixes:
        existing = PREFIX_TO_MODULES.get(_prefix, ())
        if _item.key not in existing:
            PREFIX_TO_MODULES[_prefix] = existing + (_item.key,)


def _module_label(module_key: str) -> str:
    item = FEATURE_TOGGLE_BY_KEY.get(module_key)
    return item.label if item is not None else module_key


def module_disabled_message(module_key: str) -> str:
    return f'Раздел «{_module_label(module_key)}» отключён администратором.'


def _modules_for_path(path: str) -> tuple[str, ...] | None:
    if path in PATH_TO_MODULES:
        return PATH_TO_MODULES[path]

    for prefix, modules in SHARED_PREFIX_TO_MODULES.items():
        if path.startswith(prefix):
            return modules

    matched: tuple[str, ...] = ()
    for prefix, modules in PREFIX_TO_MODULES.items():
        if path.startswith(prefix):
            for key in modules:
                if key not in matched:
                    matched = matched + (key,)
    return matched or None


def _is_always_allowed(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ALWAYS_ALLOWED_PREFIXES)


def check_path_access(path: str, *, service: FeatureToggleService) -> tuple[str, str] | None:
    """Return (module_key, message) when access must be denied, else None."""
    if _is_always_allowed(path):
        return None

    module_keys = _modules_for_path(path)
    if not module_keys:
        return None

    if any(service.is_enabled(key) for key in module_keys):
        return None

    return module_keys[0], module_disabled_message(module_keys[0])


def blocked_json_response(module_key: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": module_disabled_message(module_key),
            "feature_disabled": module_key,
            "success": False,
            "message": module_disabled_message(module_key),
        },
    )


def require_vpn_type(vpn_type: str, *, service: FeatureToggleService) -> None:
    key = "openvpn" if str(vpn_type).lower() == "openvpn" else "wireguard"
    if not service.is_enabled(key):
        raise HTTPException(status_code=403, detail=module_disabled_message(key))


def get_feature_service() -> FeatureToggleService:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    return FeatureToggleService(env_path)
