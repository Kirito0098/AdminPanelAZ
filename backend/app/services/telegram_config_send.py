"""Send VPN profile files to a Telegram chat (Mini App + interactive bot)."""

from __future__ import annotations

import os
import tempfile
from typing import Literal

from sqlalchemy.orm import Session

from app.models import User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter
from app.services.profile_download_name import build_profile_download_filename
from app.services.telegram_profile_ui import file_caption
from app.services.telegram import send_tg_document


def _download_name(config: VpnConfig, file_item: dict, selected_path: str) -> str:
    return file_item.get("download_filename") or build_profile_download_filename(
        config.client_name,
        protocol=file_item.get("protocol", ""),
        variant=file_item.get("variant", ""),
        path=file_item.get("path", selected_path),
    )


def send_config_files_to_chat(
    db: Session,
    config: VpnConfig,
    *,
    bot_token: str,
    chat_id: str | int,
    path: str | None = None,
    send_all: bool = False,
    run_async: bool = False,
) -> tuple[int, str | None]:
    """Send profile file(s) as Telegram documents. Returns (sent_count, error_message)."""
    if not bot_token:
        return 0, "Telegram не настроен"
    if not chat_id:
        return 0, "Chat ID не задан"

    adapter = get_active_adapter(db)
    files = adapter.get_profile_files(config.client_name, VpnType(config.vpn_type.value))
    if not files:
        return 0, "Файлы конфигурации не найдены"

    if path:
        targets = [item for item in files if item.get("path") == path]
        if not targets:
            return 0, "Файл конфигурации не найден"
    elif send_all and len(files) > 1:
        targets = files
    else:
        targets = [files[0]]

    sent = 0
    for index, file_item in enumerate(targets):
        selected_path = file_item.get("path", "")
        if not selected_path:
            continue
        try:
            content = adapter.read_profile_file(selected_path)
        except Exception as exc:
            return sent, str(exc) if sent == 0 else None

        download_name = _download_name(config, file_item, selected_path)
        caption = file_caption(client_name=config.client_name, file_item=file_item)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False) as handle:
            handle.write(content)
            tmp = handle.name
        try:
            ok = send_tg_document(
                bot_token,
                str(chat_id),
                tmp,
                caption=caption,
                filename=download_name,
                run_async=run_async,
            )
        finally:
            os.unlink(tmp)

        if not ok:
            return sent, "Не удалось отправить файл в Telegram" if sent == 0 else None
        sent += 1

    return sent, None


def send_config_for_user(
    db: Session,
    config: VpnConfig,
    user: User,
    *,
    bot_token: str,
    path: str | None = None,
    destination: Literal["self", "chat"] = "self",
    chat_id_override: str | int | None = None,
    send_all: bool = False,
    run_async: bool = False,
) -> tuple[int, str | None]:
    """Resolve destination chat and send config files."""
    from app.routers.maintenance import _get_setting

    if chat_id_override is not None:
        chat_id = chat_id_override
    elif destination == "chat":
        if user.role.value != "admin":
            return 0, "Только admin может отправлять в общий chat"
        chat_id = _get_setting(db, "telegram_chat_id").strip()
        if not chat_id:
            return 0, "Глобальный chat_id не настроен"
    else:
        chat_id = (user.telegram_id or "").strip()
        if not chat_id and user.role.value == "admin":
            chat_id = _get_setting(db, "telegram_chat_id").strip()
        if not chat_id:
            return 0, "Telegram ID не привязан к вашему аккаунту"

    return send_config_files_to_chat(
        db,
        config,
        bot_token=bot_token,
        chat_id=chat_id,
        path=path,
        send_all=send_all,
        run_async=run_async,
    )
