"""OpenVPN profile helpers: validate and recreate without automatic cert re-issue."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.openvpn_pki import (
    ProfileValidationResult,
    validate_all_openvpn_profiles,
    validate_client_profiles,
)
from app.services.profile_delivery import patch_openvpn_profiles_on_node

logger = logging.getLogger(__name__)


@dataclass
class RecreateResult:
    success: bool
    recreated: bool = False
    output: str = ""
    validation: ProfileValidationResult | None = None
    errors: list[str] = field(default_factory=list)
    patch: dict[str, Any] | None = None


def recreate_openvpn_profiles(
    adapter,
    hosts: list[str] | None = None,
) -> RecreateResult:
    """Run client.sh 7 only — never re-issue certificates.

    When ``hosts`` is non-empty, patch on-disk ``.ovpn`` remotes after a
    successful recreate (stage 06a). Patch failures are recorded in
    ``result.patch`` / logs and do not mark recreate as failed.
    """
    result = RecreateResult(success=True)
    try:
        result.output = adapter.recreate_profiles() or ""
        result.recreated = True
    except Exception as exc:
        logger.warning("OpenVPN profile recreate failed: %s", exc)
        result.errors.append(f"recreate_profiles: {exc}")
        result.success = False
        return result
    if hosts:
        result.patch = patch_openvpn_profiles_on_node(adapter, hosts)
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
    hosts: list[str] | None = None,
) -> RecreateResult:
    """After explicit create/renew (client.sh 1 on primary), regenerate .ovpn files."""
    result = recreate_openvpn_profiles(adapter, hosts=hosts)
    if not result.success:
        return result
    result.validation = validate_openvpn_profiles(adapter, client_names=client_names)
    if not result.validation.ready:
        logger.warning(
            "OpenVPN profiles still invalid after recreate for clients: %s",
            sorted({issue.client_name for issue in result.validation.issues}),
        )
    return result
