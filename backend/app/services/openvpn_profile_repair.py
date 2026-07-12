"""OpenVPN profile helpers: validate and recreate without automatic cert re-issue."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.openvpn_pki import (
    ProfileValidationResult,
    validate_all_openvpn_profiles,
    validate_client_profiles,
)

logger = logging.getLogger(__name__)


@dataclass
class RecreateResult:
    success: bool
    recreated: bool = False
    validation: ProfileValidationResult | None = None
    errors: list[str] = field(default_factory=list)


def recreate_openvpn_profiles(adapter) -> RecreateResult:
    """Run client.sh 7 only — never re-issue certificates."""
    result = RecreateResult(success=True)
    try:
        adapter.recreate_profiles()
        result.recreated = True
    except Exception as exc:
        logger.warning("OpenVPN profile recreate failed: %s", exc)
        result.errors.append(f"recreate_profiles: {exc}")
        result.success = False
    return result


def validate_openvpn_profiles(
    adapter,
    *,
    client_names: list[str] | None = None,
) -> ProfileValidationResult:
    """Read-only check: embedded cert serial must not be revoked in index.txt."""
    if client_names is None:
        return validate_all_openvpn_profiles(adapter)
    issues = []
    for name in client_names:
        partial = validate_client_profiles(adapter, name)
        issues.extend(partial.issues)
    return ProfileValidationResult(ready=not issues, issues=tuple(issues))


def recreate_openvpn_profiles_after_admin_change(
    adapter,
    *,
    client_names: list[str] | None = None,
) -> RecreateResult:
    """After explicit create/renew (client.sh 1 on primary), regenerate .ovpn files."""
    result = recreate_openvpn_profiles(adapter)
    if not result.success:
        return result
    result.validation = validate_openvpn_profiles(adapter, client_names=client_names)
    if not result.validation.ready:
        logger.warning(
            "OpenVPN profiles still invalid after recreate for clients: %s",
            sorted({issue.client_name for issue in result.validation.issues}),
        )
    return result
