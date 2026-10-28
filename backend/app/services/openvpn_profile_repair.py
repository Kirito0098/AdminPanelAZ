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


def finalize_openvpn_profiles_after_add(
    adapter,
    *,
    client_names: list[str],
    hosts: list[str] | None = None,
) -> RecreateResult:
    """After client.sh 1: patch remotes if needed and validate — never client.sh 7.

    ``client.sh 1`` already writes the new client's ``.ovpn`` files. A full
    recreate would rebuild every client (and WG/AWG) for no gain on create/renew.
    """
    result = RecreateResult(success=True, recreated=False)
    if hosts:
        result.patch = patch_openvpn_profiles_on_node(
            adapter, hosts, client_names=client_names
        )
        for warning in result.patch.get("warnings") or []:
            result.errors.append(str(warning))
    result.validation = validate_openvpn_profiles(adapter, client_names=client_names)
    if not result.validation.ready:
        logger.warning(
            "OpenVPN profiles invalid after add for clients: %s",
            sorted({issue.client_name for issue in result.validation.issues}),
        )
    return result
