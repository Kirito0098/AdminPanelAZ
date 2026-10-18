"""D1: encrypt Telegram backup sends; skip groups/channels without a password."""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.app_setting_store import _get_setting, _set_setting
from app.services.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

BACKUP_PASSWORD_SETTING = "backup_password_encrypted"
GROUP_PAUSE_WARNED_SETTING = "backup_group_pause_warned"
GROUP_PAUSE_SETTINGS_KEY = "settings_backup_group_paused"
GROUP_PAUSE_MESSAGE = (
    "Бэкапы в группу приостановлены: задайте пароль бэкапа или укажите личный чат"
)
ENCRYPTED_MAGIC = b"APAZBK1\n"
ENCRYPTED_SUFFIX = ".enc"


def get_settings_secret_key() -> str:
    from app.config import get_settings

    return get_settings().secret_key


def is_group_or_channel_chat_id(chat_id: str) -> bool:
    try:
        return int(str(chat_id).strip()) < 0
    except (TypeError, ValueError):
        return False


def filter_backup_telegram_recipients(
    chat_ids: list[str],
    *,
    password_set: bool,
) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    skipped: list[str] = []
    for chat_id in chat_ids:
        if is_group_or_channel_chat_id(chat_id) and not password_set:
            skipped.append(chat_id)
        else:
            allowed.append(chat_id)
    return allowed, skipped


def backup_password_is_set(db: Session) -> bool:
    return bool(_get_setting(db, BACKUP_PASSWORD_SETTING, "").strip())


def get_backup_password(db: Session) -> str | None:
    encrypted = _get_setting(db, BACKUP_PASSWORD_SETTING, "").strip()
    if not encrypted:
        return None
    return decrypt_secret(encrypted, get_settings_secret_key())


def set_backup_password(db: Session, password: str | None) -> None:
    """Store password encrypted at rest; empty/None clears it."""
    if password is None or not str(password).strip():
        _set_setting(db, BACKUP_PASSWORD_SETTING, "")
        _set_setting(db, GROUP_PAUSE_WARNED_SETTING, "")
        return
    _set_setting(db, BACKUP_PASSWORD_SETTING, encrypt_secret(str(password).strip(), get_settings_secret_key()))
    _set_setting(db, GROUP_PAUSE_WARNED_SETTING, "")


def is_encrypted_backup_bytes(data: bytes) -> bool:
    return data.startswith(ENCRYPTED_MAGIC)


def encrypt_backup_bytes(plain: bytes, password: str) -> bytes:
    from app.services.crypto import encrypt_bytes

    return ENCRYPTED_MAGIC + encrypt_bytes(plain, password)


def decrypt_backup_bytes(data: bytes, password: str) -> bytes:
    from app.services.crypto import decrypt_bytes
    from cryptography.fernet import InvalidToken

    if not is_encrypted_backup_bytes(data):
        raise ValueError("Архив не зашифрован паролем бэкапа")
    try:
        return decrypt_bytes(data[len(ENCRYPTED_MAGIC) :], password)
    except InvalidToken as exc:
        raise ValueError("Неверный пароль бэкапа") from exc


def encrypted_telegram_filename(original_name: str) -> str:
    name = (original_name or "backup.tar.gz").strip() or "backup.tar.gz"
    if name.endswith(ENCRYPTED_SUFFIX):
        return name
    return f"{name}{ENCRYPTED_SUFFIX}"


def notify_group_backups_paused(db: Session, *, force: bool = False) -> None:
    """Admin Telegram (+ future bell) warning; once per streak unless force=True."""
    if not force and _get_setting(db, GROUP_PAUSE_WARNED_SETTING, ""):
        return
    try:
        from app.services.admin_notify import admin_notify_service

        admin_notify_service.send_settings_change(
            db,
            actor_username="system",
            settings_key=GROUP_PAUSE_SETTINGS_KEY,
            subject_name=GROUP_PAUSE_MESSAGE,
            details=GROUP_PAUSE_MESSAGE,
        )
    except Exception as exc:
        logger.warning("Backup group-pause notify failed: %s", exc)
    _set_setting(db, GROUP_PAUSE_WARNED_SETTING, "1")
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Could not persist backup_group_pause_warned")


@contextmanager
def telegram_backup_payload(
    db: Session,
    chat_ids: list[str],
    archive_path: Path,
    *,
    original_filename: str | None = None,
):
    """Yield (allowed_chat_ids, path, filename) for Telegram send; encrypts when password set.

    Skips group/channel recipients when no password; warns admins (idempotent).
    Caller must not send when allowed_chat_ids is empty.
    """
    password = get_backup_password(db)
    password_set = bool(password)
    allowed, skipped = filter_backup_telegram_recipients(chat_ids, password_set=password_set)
    if skipped:
        notify_group_backups_paused(db)

    display_name = (original_filename or archive_path.name).strip() or archive_path.name
    if not allowed:
        yield [], archive_path, display_name
        return

    if not password:
        yield allowed, archive_path, display_name
        return

    enc_name = encrypted_telegram_filename(display_name)
    tmp = tempfile.NamedTemporaryFile(suffix=ENCRYPTED_SUFFIX, delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(encrypt_backup_bytes(archive_path.read_bytes(), password))
        tmp.close()
        yield allowed, tmp_path, enc_name
    finally:
        tmp_path.unlink(missing_ok=True)


def warn_if_group_recipients_without_password(db: Session, *, force: bool = False) -> bool:
    """Upgrade / startup hook: warn when telegram_chat_id has groups and no password.

    Returns True if a warning condition was detected (groups without password).
    """
    from app.services.telegram_recipients import get_setting_chat_ids

    if backup_password_is_set(db):
        return False
    chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
    if not any(is_group_or_channel_chat_id(cid) for cid in chat_ids):
        return False
    notify_group_backups_paused(db, force=force)
    return True
