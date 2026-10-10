"""One-time download tokens for VPN profiles (ported from AdminAntizapret)."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import QrDownloadAuditLog, QrDownloadToken

MAX_PIN_FAILURES = 5
PIN_LOCKED_DETAIL = "Ссылка заблокирована после 5 неверных PIN — запросите новую"
DOWNLOADS_EXHAUSTED_DETAIL = "Лимит скачиваний исчерпан"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _pins_match(provided: str | None, expected_hash: str | None) -> bool:
    if not expected_hash:
        return True
    if not provided:
        return False
    return hmac.compare_digest(_hash_pin(provided), expected_hash)


class QrDownloadService:
    def __init__(self, db: Session, *, base_url: str = "", ttl_seconds: int = 600, max_downloads: int = 1, pin: str = ""):
        self.db = db
        self.base_url = base_url.rstrip("/")
        self.ttl_seconds = max(60, min(ttl_seconds, 86400))
        self.max_downloads = max_downloads if max_downloads in (1, 3, 5) else 1
        self.pin_hash = _hash_pin(pin) if pin else None

    def create_token(
        self,
        *,
        file_path: str,
        config_type: str,
        config_name: str,
        node_id: int | None,
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
            node_id=node_id,
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

    def peek_token(self, token: str) -> QrDownloadToken:
        row = self.db.query(QrDownloadToken).filter_by(token_hash=_hash_token(token)).first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка недействительна")
        return row

    def redeem_token(self, token: str, *, pin: str | None = None, remote_addr: str | None = None) -> QrDownloadToken:
        now = datetime.now(timezone.utc)
        row = self.peek_token(token)
        if row.expires_at.replace(tzinfo=timezone.utc) < now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Ссылка истекла")
        if (row.pin_failures or 0) >= MAX_PIN_FAILURES:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=PIN_LOCKED_DETAIL)
        if row.download_count >= row.max_downloads:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=DOWNLOADS_EXHAUSTED_DETAIL)

        # Token PIN if set; otherwise fall back to current global PIN (protects older unpinned links
        # after an admin enables a global PIN).
        required_hash = row.pin_hash or self.pin_hash
        if required_hash and not _pins_match(pin, required_hash):
            self.db.query(QrDownloadToken).filter(QrDownloadToken.id == row.id).update(
                {QrDownloadToken.pin_failures: QrDownloadToken.pin_failures + 1},
                synchronize_session=False,
            )
            self.db.add(
                QrDownloadAuditLog(
                    token_id=row.id,
                    event_type="pin_failed",
                    remote_addr=remote_addr,
                    details="bad_pin",
                )
            )
            self.db.commit()
            self.db.refresh(row)
            if row.pin_failures >= MAX_PIN_FAILURES:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail=PIN_LOCKED_DETAIL)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный PIN")

        claimed = (
            self.db.query(QrDownloadToken)
            .filter(
                QrDownloadToken.id == row.id,
                QrDownloadToken.download_count < QrDownloadToken.max_downloads,
                QrDownloadToken.pin_failures < MAX_PIN_FAILURES,
            )
            .update(
                {QrDownloadToken.download_count: QrDownloadToken.download_count + 1},
                synchronize_session=False,
            )
        )
        if not claimed:
            self.db.rollback()
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=DOWNLOADS_EXHAUSTED_DETAIL)
        self.db.refresh(row)
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
