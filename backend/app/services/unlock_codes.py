"""Unlock code lifecycle and redemption helpers."""

from __future__ import annotations

import json
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AmneziaWg2AccessPolicy,
    Node,
    OpenVpnAccessPolicy,
    UnlockCode,
    UnlockCodeRedemption,
    User,
    VpnConfig,
    WgAccessPolicy,
)
from app.services.access_until import _policy_service_for_node, _reconcile_access_until, get_access_until, set_access_until
from app.services.feature_guards import get_feature_service, module_disabled_message

_ALLOWED_PROTOCOLS = ("openvpn", "wireguard", "amneziawg2")
_CODE_CHARS = string.ascii_uppercase + string.digits
_CUSTOM_CODE_RE = re.compile(r"^[A-Z0-9-]+$")
_REDEEM_INVALID_MESSAGE = "Неверный unlock-ключ"
_REDEEM_REVOKED_MESSAGE = "Unlock-ключ отозван"
_REDEEM_EXPIRED_MESSAGE = "Срок действия unlock-ключа истёк"
_REDEEM_LIMIT_MESSAGE = "Лимит активаций unlock-ключа исчерпан"
_REDEEM_ALREADY_USED_MESSAGE = "Этот unlock-ключ уже использован вами"
_REDEEM_PROTOCOL_MISMATCH_MESSAGE = "Нет пересечения протоколов клиента и unlock-ключа"
_REDEEM_GENERIC_ERROR_MESSAGE = "Не удалось активировать unlock-ключ"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_code(code: str) -> str:
    return (code or "").strip().upper()


def _normalize_client_name(client_name: str) -> str:
    return (client_name or "").strip().lower()


def _normalize_protocols(protocols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in protocols:
        protocol = (raw or "").strip().lower()
        if not protocol:
            continue
        if protocol not in _ALLOWED_PROTOCOLS:
            raise ValueError(f"Unsupported protocol: {raw}")
        if protocol in seen:
            continue
        seen.add(protocol)
        normalized.append(protocol)
    if not normalized:
        raise ValueError("Specify at least one supported protocol")
    return normalized


def _validate_custom_code(code: str) -> str:
    normalized = _normalize_code(code)
    if not normalized:
        raise ValueError("Code cannot be empty")
    if not 8 <= len(normalized) <= 32:
        raise ValueError("Code must be between 8 and 32 characters")
    if not _CUSTOM_CODE_RE.fullmatch(normalized):
        raise ValueError("Code may contain only A-Z, 0-9, and hyphen")
    return normalized


def _parse_code_protocols(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except ValueError as exc:
        raise ValueError("Invalid unlock code protocol payload") from exc
    if not isinstance(parsed, list):
        raise ValueError("Invalid unlock code protocol payload")
    return _normalize_protocols([str(item) for item in parsed])


def _serialize_code(code: UnlockCode) -> dict:
    return {
        "id": code.id,
        "code": code.code,
        "grant_days": code.grant_days,
        "protocols": _parse_code_protocols(code.protocols),
        "mode": code.mode,
        "max_redemptions": code.max_redemptions,
        "redemption_count": int(getattr(code, "redemption_count", None) or len(code.redemptions)),
        "code_expires_at": _as_utc(code.code_expires_at).isoformat() if code.code_expires_at else None,
        "created_by_user_id": code.created_by_user_id,
        "created_at": _as_utc(code.created_at).isoformat() if code.created_at else None,
        "revoked_at": _as_utc(code.revoked_at).isoformat() if code.revoked_at else None,
    }


def generate_code_value() -> str:
    parts = [
        "".join(secrets.choice(_CODE_CHARS) for _ in range(4)),
        "".join(secrets.choice(_CODE_CHARS) for _ in range(4)),
        "".join(secrets.choice(_CODE_CHARS) for _ in range(4)),
    ]
    return "-".join(parts)


def create_unlock_code(
    db: Session,
    *,
    grant_days: int,
    protocols: list[str],
    mode: str,
    max_redemptions: int,
    code_expires_at: datetime | None,
    creator: User | None,
    code: str | None = None,
) -> UnlockCode:
    if int(grant_days) < 1:
        raise ValueError("grant_days must be at least 1")

    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in {"single", "multi"}:
        raise ValueError("mode must be 'single' or 'multi'")

    if normalized_mode == "single" and int(max_redemptions) != 1:
        raise ValueError("single mode requires max_redemptions=1")
    if int(max_redemptions) < 1:
        raise ValueError("max_redemptions must be at least 1")

    normalized_protocols = _normalize_protocols(protocols)
    code_value = _validate_custom_code(code) if code is not None and _normalize_code(code) else ""
    if not code_value:
        for _ in range(32):
            candidate = generate_code_value()
            if db.query(UnlockCode.id).filter(UnlockCode.code == candidate).first() is None:
                code_value = candidate
                break
        if not code_value:
            raise ValueError("Could not generate a unique unlock code")
    elif db.query(UnlockCode.id).filter(UnlockCode.code == code_value).first() is not None:
        raise ValueError("Code already exists")

    row = UnlockCode(
        code=code_value,
        grant_days=int(grant_days),
        protocols=json.dumps(normalized_protocols, ensure_ascii=False),
        mode=normalized_mode,
        max_redemptions=int(max_redemptions),
        redemption_count=0,
        code_expires_at=_to_db_datetime(code_expires_at),
        created_by_user_id=creator.id if creator is not None else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_unlock_code(db: Session, code_id: int) -> None:
    row = db.get(UnlockCode, code_id)
    if row is None:
        raise ValueError("Unlock code not found")
    if row.revoked_at is None:
        row.revoked_at = _to_db_datetime(_now())
        db.commit()


def list_unlock_codes(db: Session, *, include_revoked: bool = False) -> list[dict]:
    query = db.query(UnlockCode)
    if not include_revoked:
        query = query.filter(UnlockCode.revoked_at.is_(None))
    rows = query.order_by(UnlockCode.created_at.desc(), UnlockCode.id.desc()).all()
    return [_serialize_code(row) for row in rows]


def _policy_rows_for_client(db: Session, node_id: int, client_name: str) -> dict[str, object | None]:
    return {
        "openvpn": (
            db.query(OpenVpnAccessPolicy)
            .filter(OpenVpnAccessPolicy.node_id == node_id, OpenVpnAccessPolicy.client_name == client_name)
            .first()
        ),
        "wireguard": (
            db.query(WgAccessPolicy)
            .filter(WgAccessPolicy.node_id == node_id, WgAccessPolicy.client_name == client_name)
            .first()
        ),
        "amneziawg2": (
            db.query(AmneziaWg2AccessPolicy)
            .filter(AmneziaWg2AccessPolicy.node_id == node_id, AmneziaWg2AccessPolicy.client_name == client_name)
            .first()
        ),
    }


def _client_config_name_and_protocols(db: Session, node_id: int, client_name: str) -> tuple[str, set[str]]:
    client_key = _normalize_client_name(client_name)
    rows = (
        db.query(VpnConfig.client_name, VpnConfig.vpn_type)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name.ilike(client_key),
            VpnConfig.ha_primary_config_id.is_(None),
        )
        .all()
    )
    if not rows:
        return client_key, set()
    canonical_name = str(rows[0][0] or "").strip()
    protocols = {
        str(vpn_type.value if hasattr(vpn_type, "value") else vpn_type).lower()
        for (_name, vpn_type) in rows
    }
    return canonical_name, protocols


def _clear_policy_block(row, *, actor: str) -> None:
    row.is_temp_blocked = False
    row.is_permanent_blocked = False
    row.block_reason = None
    row.block_started_at = None
    row.block_days = None
    row.block_until = None
    row.updated_by = actor


def _require_unlock_codes_enabled() -> None:
    if not get_feature_service().is_enabled("unlock_codes"):
        raise ValueError(module_disabled_message("unlock_codes"))


def _is_duplicate_redemption_error(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "uq_unlock_code_redemptions_code_client" in message
        or "unlock_code_redemptions.code_id, unlock_code_redemptions.client_name" in message
        or (
            "unlock_code_redemptions" in message
            and "code_id" in message
            and "client_name" in message
            and "unique" in message
        )
    )


def redeem_unlock_code(
    db: Session,
    *,
    code: str,
    client_name: str,
    node_id: int,
) -> dict:
    _require_unlock_codes_enabled()
    normalized_code = _normalize_code(code)
    client_key = _normalize_client_name(client_name)
    now = _now()
    now_db = _to_db_datetime(now)
    node = db.get(Node, node_id)
    if node is None:
        raise ValueError("Узел не найден")

    policy_service = _policy_service_for_node(db, node)
    canonical_client_name = client_key
    access_until_by_protocol: dict[str, str] = {}
    protocols_applied: list[str] = []
    grant_days = 0
    try:
        row = db.query(UnlockCode).filter(UnlockCode.code == normalized_code).first()
        if row is None:
            raise ValueError(_REDEEM_INVALID_MESSAGE)
        if row.revoked_at is not None:
            raise ValueError(_REDEEM_REVOKED_MESSAGE)
        if row.code_expires_at is not None and _as_utc(row.code_expires_at) <= now:
            raise ValueError(_REDEEM_EXPIRED_MESSAGE)

        if (
            db.query(UnlockCodeRedemption.id)
            .filter(UnlockCodeRedemption.code_id == row.id, UnlockCodeRedemption.client_name == client_key)
            .first()
            is not None
        ):
            raise ValueError(_REDEEM_ALREADY_USED_MESSAGE)

        canonical_client_name, client_protocols = _client_config_name_and_protocols(db, node_id, client_key)
        code_protocols = _parse_code_protocols(row.protocols)
        protocols_applied = [protocol for protocol in code_protocols if protocol in client_protocols]
        if not protocols_applied:
            raise ValueError(_REDEEM_PROTOCOL_MISMATCH_MESSAGE)

        # Atomic slot reservation — works on SQLite (page write lock) and Postgres.
        reserved = db.execute(
            text(
                """
                UPDATE unlock_codes
                SET redemption_count = redemption_count + 1
                WHERE id = :id
                  AND revoked_at IS NULL
                  AND redemption_count < max_redemptions
                  AND (code_expires_at IS NULL OR code_expires_at > :now)
                """
            ),
            {"id": row.id, "now": now_db},
        )
        if reserved.rowcount != 1:
            db.refresh(row)
            if row.revoked_at is not None:
                raise ValueError(_REDEEM_REVOKED_MESSAGE)
            if row.code_expires_at is not None and _as_utc(row.code_expires_at) <= now:
                raise ValueError(_REDEEM_EXPIRED_MESSAGE)
            raise ValueError(_REDEEM_LIMIT_MESSAGE)

        grant_days = int(row.grant_days)
        policy_rows = {
            "openvpn": _policy_rows_for_client(db, node_id, canonical_client_name)["openvpn"],
            "wireguard": _policy_rows_for_client(db, node_id, canonical_client_name.lower())["wireguard"],
            "amneziawg2": _policy_rows_for_client(db, node_id, canonical_client_name.lower())["amneziawg2"],
        }
        grant_until_base = now
        for protocol in protocols_applied:
            policy_client_name = canonical_client_name if protocol == "openvpn" else canonical_client_name.lower()
            current = get_access_until(db, protocol, node_id, policy_client_name)
            current_utc = _as_utc(current)
            grant_until = max(grant_until_base, current_utc or grant_until_base) + timedelta(days=grant_days)

            policy_row = policy_rows[protocol]
            if policy_row is not None:
                _clear_policy_block(policy_row, actor="unlock_codes")

            result = set_access_until(
                db,
                protocol,
                node_id,
                policy_client_name,
                grant_until,
                actor="unlock_codes",
                commit=False,
            )
            access_until_by_protocol[protocol] = result.get("access_until") or grant_until.isoformat()

        redemption = UnlockCodeRedemption(
            code_id=row.id,
            client_name=client_key,
            node_id=node_id,
        )
        db.add(redemption)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_redemption_error(exc):
            raise ValueError(_REDEEM_ALREADY_USED_MESSAGE) from exc
        raise ValueError(_REDEEM_GENERIC_ERROR_MESSAGE) from exc
    except Exception:
        db.rollback()
        raise

    for protocol in protocols_applied:
        policy_client_name = canonical_client_name if protocol == "openvpn" else canonical_client_name.lower()
        _reconcile_access_until(policy_service, protocol, policy_client_name)

    return {
        "grant_days": grant_days,
        "protocols_applied": protocols_applied,
        "access_until_by_protocol": access_until_by_protocol,
    }
