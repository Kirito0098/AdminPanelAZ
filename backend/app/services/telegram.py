import json
import logging
import threading
import urllib.request

import httpx

from app.services import telegram_api

logger = logging.getLogger(__name__)


def _outbound_enabled() -> bool:
    try:
        from app.services.feature_guards import get_feature_service

        return get_feature_service().is_enabled("telegram")
    except Exception:
        return False


def send_tg_message(bot_token: str, chat_id: str, text: str, *, run_async: bool = True) -> bool:
    if not _outbound_enabled():
        return False
    def _send() -> bool:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            return True
        except Exception as exc:
            logger.warning("TG notify failed chat_id=%s: %s", chat_id, exc)
            return False

    if run_async:
        threading.Thread(target=_send, daemon=True).start()
        return True
    return _send()


def send_tg_document_result(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    *,
    filename: str | None = None,
    content_type: str = "application/gzip",
    run_async: bool = True,
    timeout_seconds: int = 120,
) -> tuple[bool, str | None]:
    if not _outbound_enabled():
        return False, None
    upload_timeout = max(15, int(timeout_seconds or 120))

    def _send() -> tuple[bool, str | None]:
        try:
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            upload_name = (filename or "").strip() or (file_path or "").strip().split("/")[-1] or "backup.tar.gz"
            mime = (content_type or "application/octet-stream").strip()
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            client = telegram_api._get_bot_api_sync_client()
            with open(file_path, "rb") as fh:
                response = client.post(
                    url,
                    data=data,
                    files={"document": (upload_name, fh, mime)},
                    timeout=httpx.Timeout(float(upload_timeout), connect=5.0),
                )
            payload = response.json()
            if not payload.get("ok"):
                detail = str(payload.get("description") or "sendDocument failed")
                return False, telegram_api.format_telegram_connect_error(
                    detail,
                    operation="отправить документ",
                )
            return True, None
        except Exception as exc:
            logger.warning("TG document send failed chat_id=%s file=%s: %s", chat_id, file_path, exc)
            return False, telegram_api.format_telegram_connect_error(
                str(exc),
                operation="отправить документ",
            )

    if run_async:
        threading.Thread(target=_send, daemon=True).start()
        return True, None
    return _send()


def send_tg_document(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    *,
    filename: str | None = None,
    content_type: str = "application/gzip",
    run_async: bool = True,
    timeout_seconds: int = 120,
) -> bool:
    ok, _ = send_tg_document_result(
        bot_token,
        chat_id,
        file_path,
        caption,
        filename=filename,
        content_type=content_type,
        run_async=run_async,
        timeout_seconds=timeout_seconds,
    )
    return ok


def send_tg_photo(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    *,
    filename: str | None = None,
    run_async: bool = True,
    timeout_seconds: int = 120,
) -> bool:
    if not _outbound_enabled():
        return False
    upload_timeout = max(15, int(timeout_seconds or 120))

    def _send() -> bool:
        try:
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            upload_name = (filename or "").strip() or (file_path or "").strip().split("/")[-1] or "report.png"
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            client = telegram_api._get_bot_api_sync_client()
            with open(file_path, "rb") as fh:
                response = client.post(
                    url,
                    data=data,
                    files={"photo": (upload_name, fh, "image/png")},
                    timeout=httpx.Timeout(float(upload_timeout), connect=5.0),
                )
            payload = response.json()
            if not payload.get("ok"):
                logger.warning(
                    "TG photo send failed chat_id=%s file=%s: %s",
                    chat_id,
                    file_path,
                    payload.get("description") or "sendPhoto failed",
                )
                return False
            return True
        except Exception as exc:
            logger.warning("TG photo send failed chat_id=%s file=%s: %s", chat_id, file_path, exc)
            return False

    if run_async:
        threading.Thread(target=_send, daemon=True).start()
        return True
    return _send()
