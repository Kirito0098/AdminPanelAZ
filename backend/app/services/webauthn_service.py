"""WebAuthn passkey registration and authentication."""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from app.config import get_settings
from app.models import User, WebAuthnCredential

CHALLENGE_STORE: dict[str, dict[str, Any]] = {}
CHALLENGE_LOCK = threading.Lock()
CHALLENGE_TTL = 300


def _cleanup_challenges() -> None:
    now = time.time()
    with CHALLENGE_LOCK:
        stale = [k for k, v in CHALLENGE_STORE.items() if now - v.get("created", 0) > CHALLENGE_TTL]
        for k in stale:
            CHALLENGE_STORE.pop(k, None)


def _store_challenge(key: str, *, challenge: bytes, purpose: str, user_id: int | None = None) -> None:
    _cleanup_challenges()
    with CHALLENGE_LOCK:
        CHALLENGE_STORE[key] = {
            "challenge": challenge,
            "purpose": purpose,
            "user_id": user_id,
            "created": time.time(),
        }


def _pop_challenge(key: str, *, purpose: str, user_id: int | None = None) -> bytes:
    _cleanup_challenges()
    with CHALLENGE_LOCK:
        entry = CHALLENGE_STORE.pop(key, None)
    if not entry or entry.get("purpose") != purpose:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сессия passkey истекла")
    if user_id is not None and entry.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сессия passkey недействительна")
    return entry["challenge"]


def _user_id_bytes(user_id: int) -> bytes:
    return user_id.to_bytes(8, byteorder="big", signed=False)


def get_webauthn_rp_config(request: Request) -> tuple[str, str, str]:
    settings = get_settings()
    host_header = (request.headers.get("host") or "localhost").split(",")[0].strip()
    host = host_header.split(":")[0]
    rp_id = (settings.webauthn_rp_id or host).strip()
    if settings.webauthn_origin:
        origin = settings.webauthn_origin.rstrip("/")
    else:
        scheme = request.url.scheme
        forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
        if forwarded:
            scheme = forwarded
        if settings.is_production or settings.enforce_https or settings.behind_nginx:
            scheme = "https"
        origin = f"{scheme}://{host_header}"
    return rp_id, origin, settings.webauthn_rp_name


def user_has_passkeys(db: Session, user_id: int) -> bool:
    return (
        db.query(WebAuthnCredential.id)
        .filter(WebAuthnCredential.user_id == user_id)
        .limit(1)
        .first()
        is not None
    )


def list_passkeys(db: Session, user_id: int) -> list[WebAuthnCredential]:
    return (
        db.query(WebAuthnCredential)
        .filter(WebAuthnCredential.user_id == user_id)
        .order_by(WebAuthnCredential.created_at.desc())
        .all()
    )


def _exclude_credentials(db: Session, user_id: int) -> list[PublicKeyCredentialDescriptor]:
    rows = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user_id).all()
    descriptors: list[PublicKeyCredentialDescriptor] = []
    for row in rows:
        try:
            descriptors.append(
                PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
            )
        except Exception:
            continue
    return descriptors


class WebAuthnService:
    def registration_options(self, db: Session, user: User, request: Request) -> dict[str, Any]:
        rp_id, _, rp_name = get_webauthn_rp_config(request)
        challenge = secrets.token_bytes(32)
        session_key = secrets.token_urlsafe(24)
        _store_challenge(session_key, challenge=challenge, purpose="register", user_id=user.id)
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name=rp_name,
            user_name=user.username,
            user_id=_user_id_bytes(user.id),
            user_display_name=user.username,
            challenge=challenge,
            exclude_credentials=_exclude_credentials(db, user.id),
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        payload = options_to_json(options)
        payload["sessionKey"] = session_key
        return payload

    def registration_verify(
        self,
        db: Session,
        user: User,
        request: Request,
        *,
        credential: dict[str, Any],
        session_key: str,
        nickname: str | None = None,
    ) -> WebAuthnCredential:
        rp_id, origin, _ = get_webauthn_rp_config(request)
        expected_challenge = _pop_challenge(session_key, purpose="register", user_id=user.id)
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=False,
        )
        credential_id = bytes_to_base64url(verification.credential_id)
        existing = db.query(WebAuthnCredential).filter(WebAuthnCredential.credential_id == credential_id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkey уже зарегистрирован")
        transports = credential.get("response", {}).get("transports")
        row = WebAuthnCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=bytes_to_base64url(verification.credential_public_key),
            sign_count=verification.sign_count,
            transports=json.dumps(transports) if transports else None,
            aaguid=str(verification.aaguid) if verification.aaguid else None,
            nickname=(nickname or "Passkey").strip() or "Passkey",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def authentication_options(
        self,
        db: Session,
        user: User,
        request: Request,
        *,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        rp_id, _, _ = get_webauthn_rp_config(request)
        credentials = db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).all()
        if not credentials:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passkeys не настроены")
        allow_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
            for row in credentials
        ]
        challenge = secrets.token_bytes(32)
        key = session_key or secrets.token_urlsafe(24)
        _store_challenge(key, challenge=challenge, purpose="authenticate", user_id=user.id)
        options = generate_authentication_options(
            rp_id=rp_id,
            challenge=challenge,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        payload = options_to_json(options)
        payload["sessionKey"] = key
        return payload

    def authentication_verify(
        self,
        db: Session,
        user: User,
        request: Request,
        *,
        credential: dict[str, Any],
        session_key: str,
    ) -> WebAuthnCredential:
        rp_id, origin, _ = get_webauthn_rp_config(request)
        expected_challenge = _pop_challenge(session_key, purpose="authenticate", user_id=user.id)
        raw_id = credential.get("rawId") or credential.get("id")
        if not raw_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный passkey")
        credential_id = raw_id if isinstance(raw_id, str) else bytes_to_base64url(raw_id)
        row = db.query(WebAuthnCredential).filter(
            WebAuthnCredential.user_id == user.id,
            WebAuthnCredential.credential_id == credential_id,
        ).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey не найден")
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=base64url_to_bytes(row.public_key),
            credential_current_sign_count=row.sign_count,
            require_user_verification=False,
        )
        if verification.new_sign_count <= row.sign_count:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Passkey отклонён")
        row.sign_count = verification.new_sign_count
        row.last_used_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row

    def delete_passkey(self, db: Session, user: User, credential_row_id: int) -> None:
        row = (
            db.query(WebAuthnCredential)
            .filter(WebAuthnCredential.id == credential_row_id, WebAuthnCredential.user_id == user.id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey не найден")
        db.delete(row)
        db.commit()

    def rename_passkey(self, db: Session, user: User, credential_row_id: int, nickname: str) -> WebAuthnCredential:
        row = (
            db.query(WebAuthnCredential)
            .filter(WebAuthnCredential.id == credential_row_id, WebAuthnCredential.user_id == user.id)
            .first()
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey не найден")
        row.nickname = nickname.strip() or "Passkey"
        db.commit()
        db.refresh(row)
        return row


webauthn_service = WebAuthnService()
