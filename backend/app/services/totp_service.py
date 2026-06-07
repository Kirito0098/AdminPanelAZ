"""TOTP-based two-factor authentication for administrators."""

from __future__ import annotations

import json
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from fastapi import HTTPException, status
from io import BytesIO
import base64

from app.config import get_settings
from app.models import User
from app.services.crypto import decrypt_secret, encrypt_secret as _encrypt_secret

BACKUP_CODE_COUNT = 8


def _settings():
    return get_settings()


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return _encrypt_secret(secret, _settings().secret_key)


def decrypt_totp_secret(encrypted: str) -> str:
    return decrypt_secret(encrypted, _settings().secret_key)


def get_totp_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=_settings().app_name)


def generate_qr_data_url(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buf = BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def verify_totp_code(user: User, code: str) -> bool:
    if not user.totp_secret_encrypted:
        return False
    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    totp = pyotp.TOTP(secret)
    normalized = (code or "").strip().replace(" ", "")
    if totp.verify(normalized, valid_window=1):
        return True
    return _verify_backup_code(user, normalized)


def _verify_backup_code(user: User, code: str) -> bool:
    if not user.totp_backup_codes_encrypted:
        return False
    try:
        codes = json.loads(decrypt_secret(user.totp_backup_codes_encrypted, _settings().secret_key))
    except Exception:
        return False
    code_upper = code.upper()
    if code_upper in codes:
        codes.remove(code_upper)
        user.totp_backup_codes_encrypted = _encrypt_secret(json.dumps(codes), _settings().secret_key)
        return True
    return False


def generate_backup_codes() -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(BACKUP_CODE_COUNT)]


def encrypt_backup_codes(codes: list[str]) -> str:
    return _encrypt_secret(json.dumps(codes), _settings().secret_key)


def require_valid_totp(user: User, code: str) -> None:
    if not verify_totp_code(user, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверный код 2FA")
