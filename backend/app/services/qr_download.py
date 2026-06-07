"""One-time download tokens for VPN profiles (ported from AdminAntizapret)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import QrDownloadAuditLog, QrDownloadToken


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


class QrDownloadService:
    def __init__(self, db: Session, *, base_url: str = "", ttl_seconds: int = 600, max_downloads: int = 1, pin: str = ""):
        self.db = db
        self.base_url = base_url.rstrip("/")
        self.ttl_seconds = max(60, min(ttl_seconds, 3600))
        self.max_downloads = max_downloads if max_downloads in (1, 3, 5) else 1
        self.pin_hash = _hash_pin(pin) if pin else None

    def create_token(
        self,
        *,
        file_path: str,
        config_type: str,
        config_name: str,
        creator_id: int | None = None,
        creator_username: str | None = None,
        remote_addr: str | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(24)
        row = QrDownloadToken(
            token_hash=_hash_token(token),
            config_type=config_type,
            config_name=config_name,
            file_path=file_path,
            created_by_user_id=creator_id,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            max_downloads=self.max_downloads,
            pin_hash=self.pin_hash,
        )
        self.db.add(row)
        self.db.flush()
        self.db.add(
            QrDownloadAuditLog(
                token_id=row.id,
                event_type="generated",
                actor_user_id=creator_id,
                actor_username=creator_username,
                remote_addr=remote_addr,
                details=f"cfg={config_type}/{config_name} ttl={self.ttl_seconds}s",
            )
        )
        self.db.commit()
        url = f"{self.base_url}/api/public/qr-download/{token}"
        return {
            "url": url,
            "token": token,
            "expires_at": row.expires_at.isoformat(),
            "max_downloads": self.max_downloads,
            "pin_required": bool(self.pin_hash),
        }

    def redeem_token(self, token: str, *, pin: str | None = None, remote_addr: str | None = None) -> QrDownloadToken:
        now = datetime.now(timezone.utc)
        row = self.db.query(QrDownloadToken).filter_by(token_hash=_hash_token(token)).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка недействительна")
        if row.expires_at.replace(tzinfo=timezone.utc) < now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка истекла")
        if row.download_count >= row.max_downloads:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Лимит скачиваний исчерпан")
        if row.pin_hash:
            if not pin or _hash_pin(pin) != row.pin_hash:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный PIN")
        row.download_count += 1
        if row.download_count >= row.max_downloads:
            row.used_at = now
        self.db.add(
            QrDownloadAuditLog(
                token_id=row.id,
                event_type="downloaded",
                remote_addr=remote_addr,
                details=f"count={row.download_count}/{row.max_downloads}",
            )
        )
        self.db.commit()
        return row
