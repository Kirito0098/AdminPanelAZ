"""Per-user / default VPN profile visibility policy (routes × protocols × OpenVPN groups)."""

from __future__ import annotations

import json
from typing import Any, Mapping

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.constants.public_routes import (
    DEFAULT_OPENVPN_GROUP,
    OPENVPN_GROUP_LABELS,
    OPENVPN_GROUP_VARIANTS,
)
from app.models import AppSetting, User, UserRole, VpnType
from app.services.telegram_profile_ui import is_az_profile

SETTING_VISIBLE_VPN_PROFILES_DEFAULT = "user_visible_vpn_profiles_default"

ROUTES = frozenset({"az", "vpn"})
PROTOCOLS = frozenset({"openvpn", "wireguard", "amneziawg"})
OPENVPN_GROUPS = frozenset({"udp_tcp", "udp", "tcp"})

# Policy openvpn_groups key ↔ stored GROUP_* preference key
POLICY_GROUP_TO_SETTING: dict[str, str] = {
    "udp_tcp": r"GROUP_UDP\TCP",
    "udp": "GROUP_UDP",
    "tcp": "GROUP_TCP",
}
SETTING_GROUP_TO_POLICY: dict[str, str] = {v: k for k, v in POLICY_GROUP_TO_SETTING.items()}

VARIANT_TO_OPENVPN_GROUP: dict[str, str] = {
    "antizapret": "udp_tcp",
    "vpn": "udp_tcp",
    "antizapret-udp": "udp",
    "vpn-udp": "udp",
    "antizapret-tcp": "tcp",
    "vpn-tcp": "tcp",
}

FULL_POLICY: dict[str, list[str]] = {
    "routes": sorted(ROUTES),
    "protocols": sorted(PROTOCOLS),
    "openvpn_groups": sorted(OPENVPN_GROUPS),
}

EMPTY_CATALOG_MESSAGE = "Администратор ограничил доступные типы конфигураций"


def copy_policy(policy: Mapping[str, Any] | None = None) -> dict[str, list[str]]:
    source = policy or FULL_POLICY
    return {
        "routes": list(source.get("routes") or []),
        "protocols": list(source.get("protocols") or []),
        "openvpn_groups": list(source.get("openvpn_groups") or []),
    }


def normalize_policy(raw: Any, *, strict: bool = False) -> dict[str, list[str]]:
    """Parse and sanitize a policy object.

    Unknown keys/values are dropped when strict=False.
    When strict=True (write API), unknown values raise 400.
    """
    if raw is None:
        return copy_policy(FULL_POLICY)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return copy_policy(FULL_POLICY)
        try:
            raw = json.loads(text)
        except (ValueError, TypeError) as exc:
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный JSON политики видимости VPN-профилей",
                ) from exc
            return copy_policy(FULL_POLICY)
    if not isinstance(raw, dict):
        if strict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Политика видимости VPN-профилей должна быть объектом",
            )
        return copy_policy(FULL_POLICY)

    known_keys = {"routes", "protocols", "openvpn_groups"}
    if strict:
        unknown = set(raw.keys()) - known_keys
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неизвестные поля политики: {', '.join(sorted(unknown))}",
            )

    def _axis(name: str, allowed: frozenset[str]) -> list[str]:
        value = raw.get(name, [])
        if value is None:
            value = []
        if not isinstance(value, list):
            if strict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Поле «{name}» должно быть массивом",
                )
            return []
        result: list[str] = []
        for item in value:
            key = str(item).strip().lower()
            if key in allowed:
                if key not in result:
                    result.append(key)
            elif strict:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Недопустимое значение «{item}» в поле «{name}»",
                )
        return result

    return {
        "routes": _axis("routes", ROUTES),
        "protocols": _axis("protocols", PROTOCOLS),
        "openvpn_groups": _axis("openvpn_groups", OPENVPN_GROUPS),
    }


def policy_to_json(policy: Mapping[str, Any]) -> str:
    return json.dumps(normalize_policy(policy), ensure_ascii=False, separators=(",", ":"))


def _get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def get_default_visible_vpn_profiles(db: Session) -> dict[str, list[str]]:
    raw = _get_setting(db, SETTING_VISIBLE_VPN_PROFILES_DEFAULT, "")
    if not raw.strip():
        return copy_policy(FULL_POLICY)
    return normalize_policy(raw, strict=False)


def set_default_visible_vpn_profiles(db: Session, policy: Mapping[str, Any]) -> dict[str, list[str]]:
    normalized = normalize_policy(policy, strict=True)
    value = policy_to_json(normalized)
    row = db.query(AppSetting).filter(AppSetting.key == SETTING_VISIBLE_VPN_PROFILES_DEFAULT).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=SETTING_VISIBLE_VPN_PROFILES_DEFAULT, value=value))
    db.commit()
    return normalized


def parse_user_visible_vpn_profiles(raw: str | None) -> dict[str, list[str]] | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return normalize_policy(text, strict=False)


def resolve_visible_vpn_profiles(db: Session, user: User) -> dict[str, list[str]]:
    """Effective policy for user (before feature-toggle ceiling). Admin → full catalog."""
    if user.role == UserRole.admin:
        return copy_policy(FULL_POLICY)
    override = parse_user_visible_vpn_profiles(getattr(user, "visible_vpn_profiles", None))
    if override is not None:
        return override
    return get_default_visible_vpn_profiles(db)


def intersect_policy_with_features(
    policy: Mapping[str, Any],
    *,
    openvpn_enabled: bool = True,
    wireguard_enabled: bool = True,
    amneziawg_enabled: bool = True,
) -> dict[str, list[str]]:
    protocols = list(policy.get("protocols") or [])
    allowed: list[str] = []
    for key in protocols:
        if key == "openvpn" and openvpn_enabled:
            allowed.append(key)
        elif key == "wireguard" and wireguard_enabled:
            allowed.append(key)
        elif key == "amneziawg" and amneziawg_enabled:
            allowed.append(key)
    result = copy_policy(policy)
    result["protocols"] = allowed
    if "openvpn" not in allowed:
        result["openvpn_groups"] = []
    return result


def feature_flags_from_service(service: Any | None = None) -> dict[str, bool]:
    if service is None:
        from app.services.feature_guards import get_feature_service

        service = get_feature_service()
    return {
        "openvpn": bool(service.is_enabled("openvpn")),
        "wireguard": bool(service.is_enabled("wireguard")),
        "amneziawg": bool(service.is_enabled("amneziawg")),
    }


def resolve_effective_visible_vpn_profiles(
    db: Session,
    user: User,
    *,
    feature_flags: Mapping[str, bool] | None = None,
) -> dict[str, list[str]]:
    policy = resolve_visible_vpn_profiles(db, user)
    flags = feature_flags or feature_flags_from_service()
    return intersect_policy_with_features(
        policy,
        openvpn_enabled=flags.get("openvpn", True),
        wireguard_enabled=flags.get("wireguard", True),
        amneziawg_enabled=flags.get("amneziawg", True),
    )


def protocol_key_from_file(*, protocol: str, path: str = "") -> str | None:
    value = (protocol or "").strip().lower()
    if value in PROTOCOLS:
        return value
    lowered = f"{path}".replace("\\", "/").lower()
    if "/amneziawg/" in lowered or lowered.endswith("-am.conf"):
        return "amneziawg"
    if "/wireguard/" in lowered or lowered.endswith("-wg.conf"):
        return "wireguard"
    if "/openvpn/" in lowered or lowered.endswith(".ovpn"):
        return "openvpn"
    return None


def route_key_from_file(*, variant: str, path: str) -> str:
    return "az" if is_az_profile(variant=variant, path=path) else "vpn"


def openvpn_group_from_variant(variant: str) -> str | None:
    return VARIANT_TO_OPENVPN_GROUP.get((variant or "").strip().lower())


def profile_file_allowed(
    policy: Mapping[str, Any],
    *,
    protocol: str = "",
    variant: str = "",
    path: str = "",
) -> bool:
    protocol_key = protocol_key_from_file(protocol=protocol, path=path)
    if protocol_key is None:
        return False
    protocols = set(policy.get("protocols") or [])
    if protocol_key not in protocols:
        return False
    route = route_key_from_file(variant=variant, path=path)
    if route not in set(policy.get("routes") or []):
        return False
    if protocol_key == "openvpn":
        groups = set(policy.get("openvpn_groups") or [])
        if not groups:
            return False
        group = openvpn_group_from_variant(variant)
        if group is None:
            # Fallback: infer from path/filename
            lowered = f"{variant} {path}".lower()
            if "-udp" in lowered or "/antizapret-udp" in lowered or "/vpn-udp" in lowered:
                group = "udp"
            elif "-tcp" in lowered or "/antizapret-tcp" in lowered or "/vpn-tcp" in lowered:
                group = "tcp"
            else:
                group = "udp_tcp"
        if group not in groups:
            return False
    return True


def filter_profile_files(files: list[dict[str, str]], policy: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        item
        for item in files
        if profile_file_allowed(
            policy,
            protocol=item.get("protocol", ""),
            variant=item.get("variant", ""),
            path=item.get("path", ""),
        )
    ]


def can_create_vpn_type(
    policy: Mapping[str, Any],
    vpn_type: VpnType | str,
    feature_flags: Mapping[str, bool] | None = None,
) -> bool:
    flags = feature_flags or {"openvpn": True, "wireguard": True, "amneziawg": True}
    effective = intersect_policy_with_features(
        policy,
        openvpn_enabled=flags.get("openvpn", True),
        wireguard_enabled=flags.get("wireguard", True),
        amneziawg_enabled=flags.get("amneziawg", True),
    )
    protocols = set(effective.get("protocols") or [])
    vt = vpn_type.value if isinstance(vpn_type, VpnType) else str(vpn_type).lower()
    if vt == VpnType.openvpn.value:
        return "openvpn" in protocols and bool(effective.get("openvpn_groups"))
    if vt == VpnType.wireguard.value:
        return "wireguard" in protocols or "amneziawg" in protocols
    return False


def enforce_can_create_vpn_type(
    db: Session,
    user: User,
    vpn_type: VpnType | str,
    *,
    feature_flags: Mapping[str, bool] | None = None,
) -> None:
    if user.role == UserRole.admin:
        return
    policy = resolve_visible_vpn_profiles(db, user)
    flags = feature_flags or feature_flags_from_service()
    if not can_create_vpn_type(policy, vpn_type, flags):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=EMPTY_CATALOG_MESSAGE,
        )


def allowed_openvpn_groups(policy: Mapping[str, Any]) -> list[str]:
    """Return policy openvpn_groups keys in stable UI order."""
    allowed = set(policy.get("openvpn_groups") or [])
    return [key for key in ("udp_tcp", "udp", "tcp") if key in allowed]


def allowed_openvpn_group_options(policy: Mapping[str, Any]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for policy_key in allowed_openvpn_groups(policy):
        setting_key = POLICY_GROUP_TO_SETTING[policy_key]
        options.append(
            {
                "key": setting_key,
                "label": OPENVPN_GROUP_LABELS.get(setting_key, setting_key),
                "policy_key": policy_key,
            }
        )
    return options


def resolve_openvpn_group_for_user(
    db: Session,
    user: User,
    *,
    current_group: str | None = None,
) -> str:
    """Pick an allowed OpenVPN group; fallback when saved group is forbidden."""
    from app.services.openvpn_group import get_user_openvpn_group, normalize_openvpn_group

    policy = resolve_effective_visible_vpn_profiles(db, user)
    allowed_policy = allowed_openvpn_groups(policy)
    if not allowed_policy:
        return normalize_openvpn_group(current_group or DEFAULT_OPENVPN_GROUP)

    allowed_setting = {POLICY_GROUP_TO_SETTING[k] for k in allowed_policy}
    raw = current_group if current_group is not None else get_user_openvpn_group(db, user.id)
    normalized = normalize_openvpn_group(raw)
    if normalized in allowed_setting:
        return normalized
    # Prefer default among allowed, else first allowed
    if DEFAULT_OPENVPN_GROUP in allowed_setting:
        return DEFAULT_OPENVPN_GROUP
    return POLICY_GROUP_TO_SETTING[allowed_policy[0]]


def policy_is_empty(policy: Mapping[str, Any]) -> bool:
    routes = policy.get("routes") or []
    protocols = policy.get("protocols") or []
    if not routes or not protocols:
        return True
    if "openvpn" in protocols and not (policy.get("openvpn_groups") or []):
        protocols_without_ovpn = [p for p in protocols if p != "openvpn"]
        return not protocols_without_ovpn
    return False
