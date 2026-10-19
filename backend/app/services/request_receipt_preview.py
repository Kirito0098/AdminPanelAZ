"""Payment receipt preview: Telegram getFile → Pillow re-encode → JPEG bytes (Task 12).

Ничего не пишется на диск. Кэш превью в памяти с TTL ~60 с, ключ (request_id, file_id).
"""

from __future__ import annotations

import asyncio
import io
import logging
import threading
from time import monotonic
from typing import Any

from PIL import Image

from sqlalchemy.orm import Session

from app.models import UserAccessRequest
from app.services import telegram_api as _telegram_api_service
from app.services.app_setting_store import _get_setting
from app.services.telegram_api import MAX_FILE_BYTES, download_file_bytes, get_file

logger = logging.getLogger(__name__)

MAX_BYTES = MAX_FILE_BYTES  # 5 МБ — отказ при скачивании большего
MAX_EDGE = 1600  # большая сторона превью
_CACHE_TTL_SECONDS = 60

_PREVIEW_CACHE: dict[tuple[Any, str], tuple[float, bytes]] = {}
_PREVIEW_CACHE_LOCK = threading.Lock()


class ReceiptDecodeError(Exception):
    """Не удалось декодировать или перекодировать чек."""


def reencode_receipt_bytes(data: bytes) -> bytes:
    """Перекодировать чек в JPEG: RGB, не более 1600 px по большой стороне, EXIF удалён.

    Ничего не записывает на диск.
    """
    if len(data) > MAX_BYTES:
        raise ReceiptDecodeError("too large")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ReceiptDecodeError("decode") from exc
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_EDGE / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue()


def _cache_get(key: tuple[Any, str]) -> bytes | None:
    with _PREVIEW_CACHE_LOCK:
        hit = _PREVIEW_CACHE.get(key)
    if hit is None:
        return None
    expires, data = hit
    if monotonic() > expires:
        with _PREVIEW_CACHE_LOCK:
            _PREVIEW_CACHE.pop(key, None)
        return None
    return data


def _cache_set(key: tuple[Any, str], data: bytes) -> None:
    with _PREVIEW_CACHE_LOCK:
        _PREVIEW_CACHE[key] = (monotonic() + _CACHE_TTL_SECONDS, data)


async def _fetch_telegram_file(bot_token: str, file_id: str) -> bytes:
    info = await get_file(bot_token, file_id)
    if not info or not isinstance(info, dict):
        raise ReceiptDecodeError("file info not found")
    file_path = info.get("file_path")
    if not file_path:
        raise ReceiptDecodeError("file path not found")
    return await download_file_bytes(bot_token, file_path)


def download_telegram_file(file_id: str, bot_token: str) -> bytes:
    """Скачать файл из Telegram (синхронная обёртка для роутера и сервисов)."""
    try:
        _telegram_api_service.reset_bot_api_client_for_tests()
        return asyncio.run(_fetch_telegram_file(bot_token, file_id))
    except ReceiptDecodeError:
        raise
    except Exception as exc:  # сетевой/Telegram-ошибка → ошибка декодирования чека
        raise ReceiptDecodeError(f"Не удалось скачать файл из Telegram: {exc}") from exc


def build_receipt_preview_jpeg(file_id: str, bot_token: str) -> bytes:
    """Скачать файл бота и перекодировать в превью-JPEG."""
    data = download_telegram_file(file_id, bot_token)
    return reencode_receipt_bytes(data)


def get_cached_or_build_preview(db: Session, req: UserAccessRequest) -> bytes:
    """Превью чека из кэша или перекодирование нового; ключ (request_id, file_id)."""
    if not req.receipt_file_id:
        raise ReceiptDecodeError("no receipt_file_id")
    key = (req.id, req.receipt_file_id)
    data = _cache_get(key)
    if data is not None:
        return data
    bot_token = _get_setting(db, "telegram_bot_token", "").strip()
    data = build_receipt_preview_jpeg(req.receipt_file_id, bot_token)
    _cache_set(key, data)
    return data
