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
    "/api/settings",
    "/api/nodes",
    "/api/monitoring/summary",
)

WG_ACCESS_PREFIX = "/api/client-access/wireguard"
CONFIGS_QR_PATH_MARKERS = ("/download", "/qr", "/one-time-link")

PATH_TO_MODULES: dict[str, tuple[str, ...]] = {}
PREFIX_TO_MODULES: dict[str, tuple[str, ...]] = {}
SHARED_PREFIX_TO_MODULES: dict[str, tuple[str, ...]] = {
    "/api/routing/cidr-db/tasks/": ("routing", "diagnostics_tests"),
    "/api/tasks/": ("settings",),
}

ALL_REQUIRED_PREFIXES: dict[str, tuple[str, ...]] = {
    "/api/public/route-download": ("security", "openvpn"),
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


def _configs_qr_modules(path: str) -> tuple[str, ...] | None:
    if not path.startswith("/api/configs/"):
        return None
    if any(marker in path for marker in CONFIGS_QR_PATH_MARKERS):
        return ("qr_downloads",)
    return None


def _public_qr_modules(path: str) -> tuple[str, ...] | None:
    if path.startswith("/api/public/qr-download"):
        return ("qr_downloads",)
    return None


def _security_public_download_modules(path: str) -> tuple[str, ...] | None:
    if path == "/api/security/public-download":
        return ("security",)
    return None


def _openvpn_group_modules(path: str) -> tuple[str, ...] | None:
    if path == "/api/configs/openvpn-group":
        return ("openvpn",)
    return None


def _wg_access_modules(path: str) -> tuple[str, ...] | None:
    if not path.startswith(WG_ACCESS_PREFIX):
        return None
    return ("wireguard", "amneziawg")


def _modules_for_path(path: str) -> tuple[str, ...] | None:
    for resolver in (
        _public_qr_modules,
        _security_public_download_modules,
        _openvpn_group_modules,
        _configs_qr_modules,
        _wg_access_modules,
    ):
        modules = resolver(path)
        if modules is not None:
            return modules

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


def _module_guard_under_always_allowed(path: str, *, service: FeatureToggleService) -> tuple[str, str] | None:
    """Modules whose API paths sit under broad always-allowed prefixes (e.g. /api/settings)."""
    maintenance = FEATURE_TOGGLE_BY_KEY.get("maintenance")
    if maintenance is not None and not service.is_enabled("maintenance"):
        if path in maintenance.api_paths or any(path.startswith(prefix) for prefix in maintenance.api_prefixes):
            return "maintenance", module_disabled_message("maintenance")
    return None


def _all_required_modules(path: str) -> tuple[str, ...] | None:
    for prefix, modules in ALL_REQUIRED_PREFIXES.items():
        if path.startswith(prefix):
            return modules
    return None


def check_path_access(path: str, *, service: FeatureToggleService) -> tuple[str, str] | None:
    """Return (module_key, message) when access must be denied, else None."""
    blocked_under_allow = _module_guard_under_always_allowed(path, service=service)
    if blocked_under_allow is not None:
        return blocked_under_allow

    if _is_always_allowed(path):
        return None

    all_required = _all_required_modules(path)
    if all_required is not None:
        for key in all_required:
            if not service.is_enabled(key):
                return key, module_disabled_message(key)
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
    vt = str(vpn_type).lower()
    if vt == "openvpn":
        if not service.is_enabled("openvpn"):
            raise HTTPException(status_code=403, detail=module_disabled_message("openvpn"))
        return
    if service.is_enabled("wireguard") or service.is_enabled("amneziawg"):
        return
    raise HTTPException(status_code=403, detail=module_disabled_message("wireguard"))


def require_qr_downloads(*, service: FeatureToggleService) -> None:
    if not service.is_enabled("qr_downloads"):
        raise HTTPException(status_code=403, detail=module_disabled_message("qr_downloads"))


def require_openvpn_and_security(*, service: FeatureToggleService | None = None) -> None:
    svc = service or get_feature_service()
    if not svc.is_enabled("security"):
        raise HTTPException(status_code=403, detail=module_disabled_message("security"))
    if not svc.is_enabled("openvpn"):
        raise HTTPException(status_code=403, detail=module_disabled_message("openvpn"))


def get_feature_service() -> FeatureToggleService:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    return FeatureToggleService(env_path)
