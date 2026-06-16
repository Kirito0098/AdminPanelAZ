"""Guided secrets rotation with preview → confirm → write flow."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AppSetting, Node, User
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.env_file import EnvFileService
from app.services.node_agent_env import resolve_node_agent_env_file

CONFIRM_PHRASE = "ROTATE"
PREVIEW_TTL_SECONDS = 600
_DEFAULT_SECRET_KEY = "change-me-in-production-use-long-random-string"
_DEFAULT_NODE_AGENT_KEY = "change-me-node-agent-key"
_TG_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class SecretDefinition:
    secret_id: str
    label: str
    description: str
    storage: str
    env_key: str | None = None
    db_key: str | None = None
    auto_generate: bool = True
    requires_restart: bool = False
    requires_relogin: bool = False


SECRET_DEFINITIONS: dict[str, SecretDefinition] = {
    "secret_key": SecretDefinition(
        secret_id="secret_key",
        label="SECRET_KEY (JWT)",
        description="JWT access/refresh и шифрование чувствительных данных в БД",
        storage="env",
        env_key="SECRET_KEY",
        auto_generate=True,
        requires_restart=True,
        requires_relogin=True,
    ),
    "node_agent_api_key": SecretDefinition(
        secret_id="node_agent_api_key",
        label="NODE_AGENT_API_KEY",
        description="API-ключ локального node agent (backend/node_agent.env)",
        storage="env",
        env_key="NODE_AGENT_API_KEY",
        auto_generate=True,
        requires_restart=True,
    ),
    "telegram_bot_token": SecretDefinition(
        secret_id="telegram_bot_token",
        label="Telegram bot token",
        description="Токен бота из @BotFather (хранится в БД панели)",
        storage="db",
        db_key="telegram_bot_token",
        auto_generate=False,
    ),
}


def _panel_env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _mask_secret(value: str) -> str:
    if not value:
        return "(не задан)"
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}…{value[-4:]}"


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode()).digest().hex()


def _create_preview_token(secret_id: str, value_hash: str, signing_key: str) -> str:
    expires = int(time.time()) + PREVIEW_TTL_SECONDS
    payload = json.dumps({"id": secret_id, "vh": value_hash, "exp": expires}, separators=(",", ":"))
    sig = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}.{sig}".encode()
    return urlsafe_b64encode(raw).decode()


def _verify_preview_token(token: str, secret_id: str, value_hash: str, signing_key: str) -> None:
    try:
        decoded = urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(".", 1)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Недействительный preview token") from exc

    expected_sig = hmac.new(signing_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Недействительный preview token")

    data = json.loads(payload)
    if data.get("id") != secret_id or data.get("vh") != value_hash:
        raise ValueError("Preview token не соответствует секрету")
    if int(data.get("exp", 0)) < int(time.time()):
        raise ValueError("Preview token истёк — повторите предпросмотр")


def _generate_value(defn: SecretDefinition) -> str:
    if defn.secret_id == "secret_key":
        return secrets.token_hex(32)
    if defn.secret_id == "node_agent_api_key":
        return secrets.token_hex(32)
    raise ValueError("Автогенерация недоступна для этого секрета")


def _validate_value(defn: SecretDefinition, value: str, *, production: bool) -> None:
    value = value.strip()
    if not value:
        raise ValueError("Значение не может быть пустым")

    if defn.secret_id == "secret_key":
        if production and (value == _DEFAULT_SECRET_KEY or len(value) < 32):
            raise ValueError("SECRET_KEY: минимум 32 символа в production")
        if not production and len(value) < 16:
            raise ValueError("SECRET_KEY: минимум 16 символов")
    elif defn.secret_id == "node_agent_api_key":
        if production and (value == _DEFAULT_NODE_AGENT_KEY or len(value) < 24):
            raise ValueError("NODE_AGENT_API_KEY: минимум 24 символа в production")
        if not production and len(value) < 16:
            raise ValueError("NODE_AGENT_API_KEY: минимум 16 символов")
    elif defn.secret_id == "telegram_bot_token":
        if not _TG_TOKEN_RE.match(value):
            raise ValueError("Некорректный формат Telegram bot token (ожидается 123456:ABC...)")


def _read_secret_value(defn: SecretDefinition, db: Session, settings: Settings) -> str:
    if defn.storage == "db" and defn.db_key:
        row = db.query(AppSetting).filter(AppSetting.key == defn.db_key).first()
        return row.value if row else ""
    if defn.storage == "env" and defn.env_key:
        if defn.env_key == "SECRET_KEY":
            return settings.secret_key
        if defn.env_key == "NODE_AGENT_API_KEY":
            env_path = resolve_node_agent_env_file()
            return EnvFileService(env_path).get_env_value("NODE_AGENT_API_KEY", "")
    return ""


def _is_configured(defn: SecretDefinition, current: str, settings: Settings) -> bool:
    if not current:
        return False
    if defn.secret_id == "secret_key":
        return current != _DEFAULT_SECRET_KEY and len(current) >= 32
    if defn.secret_id == "node_agent_api_key":
        return current != _DEFAULT_NODE_AGENT_KEY and len(current) >= 24
    return bool(current.strip())


def _build_warnings(defn: SecretDefinition, settings: Settings) -> list[str]:
    warnings: list[str] = []
    if defn.requires_relogin:
        warnings.append(
            "После смены SECRET_KEY все JWT-сессии станут недействительны — "
            "все пользователи должны войти заново."
        )
        warnings.append(
            "Зашифрованные в БД данные (API-ключи узлов, TOTP) будут перешифрованы автоматически."
        )
    if defn.secret_id == "node_agent_api_key":
        warnings.append("Перезапустите node agent после применения нового ключа.")
    if defn.secret_id == "telegram_bot_token":
        warnings.append("После смены токена зарегистрируйте webhook заново (Настройки → Telegram).")
    if defn.requires_restart and defn.secret_id == "secret_key":
        warnings.append("Перезапустите панель для полного применения SECRET_KEY.")
    if settings.is_production:
        warnings.append("Выполняйте ротацию в окно обслуживания — возможен кратковременный сбой авторизации.")
    return warnings


def _reencrypt_secrets_with_new_key(db: Session, old_key: str, new_key: str) -> dict[str, int]:
    stats = {"nodes": 0, "totp_users": 0, "errors": 0}

    for node in db.query(Node).all():
        if not (node.api_key_encrypted or "").strip():
            continue
        try:
            plain = decrypt_secret(node.api_key_encrypted, old_key)
            node.api_key_encrypted = encrypt_secret(plain, new_key)
            db.add(node)
            stats["nodes"] += 1
        except Exception:
            stats["errors"] += 1

    for user in db.query(User).all():
        if not user.totp_secret_encrypted and not user.totp_backup_codes_encrypted:
            continue
        try:
            if user.totp_secret_encrypted:
                plain = decrypt_secret(user.totp_secret_encrypted, old_key)
                user.totp_secret_encrypted = encrypt_secret(plain, new_key)
            if user.totp_backup_codes_encrypted:
                plain = decrypt_secret(user.totp_backup_codes_encrypted, old_key)
                user.totp_backup_codes_encrypted = encrypt_secret(plain, new_key)
            db.add(user)
            stats["totp_users"] += 1
        except Exception:
            stats["errors"] += 1

    return stats


class SecretsRotationService:
    def list_secrets(self, db: Session) -> list[dict]:
        settings = get_settings()
        items: list[dict] = []
        for defn in SECRET_DEFINITIONS.values():
            current = _read_secret_value(defn, db, settings)
            env_path = None
            if defn.storage == "env":
                env_path = str(_panel_env_path() if defn.env_key == "SECRET_KEY" else resolve_node_agent_env_file())
            items.append(
                {
                    "secret_id": defn.secret_id,
                    "label": defn.label,
                    "description": defn.description,
                    "storage": defn.storage,
                    "env_key": defn.env_key,
                    "env_path": env_path,
                    "configured": _is_configured(defn, current, settings),
                    "masked_current": _mask_secret(current),
                    "auto_generate": defn.auto_generate,
                    "requires_restart": defn.requires_restart,
                    "requires_relogin": defn.requires_relogin,
                }
            )
        return items

    def preview(self, db: Session, secret_id: str, *, value: str | None = None) -> dict:
        defn = SECRET_DEFINITIONS.get(secret_id)
        if not defn:
            raise ValueError("Неизвестный секрет")

        settings = get_settings()
        new_value = (value or "").strip()
        if not new_value:
            if not defn.auto_generate:
                raise ValueError("Укажите новый Telegram bot token")
            new_value = _generate_value(defn)

        _validate_value(defn, new_value, production=settings.is_production)

        current = _read_secret_value(defn, db, settings)
        if current and hmac.compare_digest(current, new_value):
            raise ValueError("Новое значение совпадает с текущим")

        value_hash = _hash_value(new_value)
        preview_token = _create_preview_token(secret_id, value_hash, settings.secret_key)

        env_change = None
        if defn.storage == "env" and defn.env_key:
            env_path = _panel_env_path() if defn.env_key == "SECRET_KEY" else resolve_node_agent_env_file()
            env_change = {
                "path": str(env_path),
                "key": defn.env_key,
                "masked_new_value": _mask_secret(new_value),
            }

        return {
            "secret_id": secret_id,
            "label": defn.label,
            "new_value": new_value,
            "masked_new_value": _mask_secret(new_value),
            "masked_current": _mask_secret(current),
            "preview_token": preview_token,
            "confirm_phrase": CONFIRM_PHRASE,
            "warnings": _build_warnings(defn, settings),
            "env_change": env_change,
            "storage": defn.storage,
            "requires_relogin": defn.requires_relogin,
            "requires_restart": defn.requires_restart,
        }

    def apply(
        self,
        db: Session,
        secret_id: str,
        *,
        new_value: str,
        preview_token: str,
        confirm: str,
        old_settings: Settings | None = None,
    ) -> dict:
        if confirm.strip() != CONFIRM_PHRASE:
            raise ValueError(f'Для подтверждения введите "{CONFIRM_PHRASE}"')

        defn = SECRET_DEFINITIONS.get(secret_id)
        if not defn:
            raise ValueError("Неизвестный секрет")

        settings = old_settings or get_settings()
        new_value = new_value.strip()
        _validate_value(defn, new_value, production=settings.is_production)

        value_hash = _hash_value(new_value)
        _verify_preview_token(preview_token, secret_id, value_hash, settings.secret_key)

        current = _read_secret_value(defn, db, settings)
        if current and hmac.compare_digest(current, new_value):
            raise ValueError("Новое значение совпадает с текущим")

        reencrypt_stats = None

        if defn.secret_id == "secret_key":
            old_key = settings.secret_key
            env_service = EnvFileService(_panel_env_path())
            env_service.set_env_value("SECRET_KEY", new_value)
            os.environ["SECRET_KEY"] = new_value
            get_settings.cache_clear()
            reencrypt_stats = _reencrypt_secrets_with_new_key(db, old_key, new_value)
        elif defn.secret_id == "node_agent_api_key":
            env_path = resolve_node_agent_env_file()
            EnvFileService(env_path).set_env_value("NODE_AGENT_API_KEY", new_value)
        elif defn.secret_id == "telegram_bot_token":
            row = db.query(AppSetting).filter(AppSetting.key == defn.db_key).first()
            if row:
                row.value = new_value
            else:
                db.add(AppSetting(key=defn.db_key, value=new_value))

        db.commit()

        next_steps = []
        if defn.requires_relogin:
            next_steps.append("Все пользователи должны войти заново.")
        if defn.requires_restart:
            next_steps.append("Перезапустите панель (systemctl restart admin-panel-az).")
        if defn.secret_id == "node_agent_api_key":
            next_steps.append("Перезапустите node agent.")
        if defn.secret_id == "telegram_bot_token":
            next_steps.append("Зарегистрируйте webhook в Настройки → Telegram.")

        result = {
            "secret_id": secret_id,
            "label": defn.label,
            "message": f"{defn.label} успешно обновлён",
            "requires_relogin": defn.requires_relogin,
            "next_steps": next_steps,
        }
        if reencrypt_stats is not None:
            result["reencrypt_stats"] = reencrypt_stats
        return result
