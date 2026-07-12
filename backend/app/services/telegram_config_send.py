"""Send VPN profile files to a Telegram chat (Mini App + interactive bot)."""

from __future__ import annotations

import os
import tempfile
from typing import Literal

from sqlalchemy.orm import Session, joinedload

from app.models import User, VpnConfig, VpnType
from app.services.node_manager import get_active_adapter
from app.services.node_manager import get_active_adapter
from app.services.profile_download_name import build_profile_download_filename
from app.services.telegram_profile_ui import file_caption
from app.services.telegram import send_tg_document, send_tg_message
from app.services.vpn_install_instructions import InstallPlatform, build_install_instruction_message


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
    install_platform: InstallPlatform | None = None,
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
    last_file_item: dict | None = None
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
        last_file_item = file_item

    if install_platform and last_file_item and sent > 0:
        instruction = build_install_instruction_message(
            protocol=last_file_item.get("protocol", ""),
            platform=install_platform,
            client_name=config.client_name,
        )
        if instruction:
            if not send_tg_message(bot_token, str(chat_id), instruction, run_async=run_async):
                return sent, "Конфиг отправлен, но инструкция не доставлена"

    return sent, None


def send_config_for_user(
    db: Session,
    config: VpnConfig,
    user: User,
    *,
    bot_token: str,
    path: str | None = None,
    destination: Literal["self", "chat", "owner"] = "self",
    chat_id_override: str | int | None = None,
    send_all: bool = False,
    run_async: bool = False,
    install_platform: InstallPlatform | None = None,
) -> tuple[int, str | None]:
    """Resolve destination chat and send config files."""
    from app.routers.maintenance import _get_setting
    from app.services.telegram_recipients import get_setting_chat_ids

    if chat_id_override is not None:
        chat_ids = [str(chat_id_override).strip()]
    elif destination == "owner":
        if user.role.value != "admin":
            return 0, "Недостаточно прав"
        owner = db.query(User).filter(User.id == config.owner_id).first()
        if not owner:
            return 0, "Владелец конфига не найден"
        chat_id = (owner.telegram_id or "").strip()
        if not chat_id:
            return 0, "У пользователя не привязан Telegram"
        chat_ids = [chat_id]
    elif destination == "chat":
        if user.role.value != "admin":
            return 0, "Только admin может отправлять в общий chat"
        chat_ids = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
        if not chat_ids:
            return 0, "Получатели бэкапов не настроены"
    else:
        chat_id = (user.telegram_id or "").strip()
        if not chat_id and user.role.value == "admin":
            fallback = get_setting_chat_ids(lambda key, default="": _get_setting(db, key, default))
            chat_id = fallback[0] if fallback else ""
        if not chat_id:
            return 0, "Telegram ID не привязан к вашему аккаунту"
        chat_ids = [chat_id]

    total_sent = 0
    last_error: str | None = None
    for chat_id in chat_ids:
        sent, err = send_config_files_to_chat(
            db,
            config,
            bot_token=bot_token,
            chat_id=chat_id,
            path=path,
            send_all=send_all,
            run_async=run_async,
            install_platform=install_platform,
        )
        total_sent += sent
        if err:
            last_error = err
    return total_sent, last_error
