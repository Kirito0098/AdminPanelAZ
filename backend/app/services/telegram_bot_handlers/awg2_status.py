"""Telegram bot /awg2 — AZ-AWG2 status (wave 3b, admin, if awg2 enabled)."""

from __future__ import annotations

from app.services.feature_guards import get_feature_service
from app.services.tg_mini_status import build_awg2_status_payload
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


def _format_top_traffic(rows: list) -> str:
    if not rows:
        return i18n.AWG2_NONE
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "—")
        rx = int(row.get("rx") or 0)
        tx = int(row.get("tx") or 0)
        lines.append(f"• <code>{name}</code> — ↓{rx} ↑{tx}")
    return "\n".join(lines) if lines else i18n.AWG2_NONE


def _format_awg2_text(payload: dict) -> str:
    installed = bool(payload.get("installed"))
    installed_label = i18n.AWG2_YES if installed else i18n.AWG2_NO
    details_parts: list[str] = []
    if payload.get("health_error"):
        details_parts.append(i18n.AWG2_HEALTH_ERROR.format(detail=payload["health_error"]))
    if not installed:
        missing = payload.get("missing_components") or []
        if missing:
            details_parts.append(
                i18n.AWG2_MISSING.format(components=", ".join(str(x) for x in missing))
            )
        install_cmd = payload.get("install_command")
        if install_cmd:
            details_parts.append(i18n.AWG2_INSTALL_HINT.format(command=install_cmd))
    details = ("\n".join(details_parts) + "\n") if details_parts else ""
    return i18n.AWG2_BODY.format(
        title=i18n.AWG2_TITLE,
        node_name=payload.get("node_name") or i18n.AWG2_NONE,
        node_host=payload.get("node_host") or i18n.AWG2_NONE,
        installed_label=installed_label,
        details=details,
        online_count=int(payload.get("online_count") or 0),
        peer_count=int(payload.get("peer_count") or 0),
        ifaces_summary=payload.get("ifaces_summary") or i18n.AWG2_NONE,
        top_traffic=_format_top_traffic(payload.get("top_traffic") or []),
    )


async def handle_awg2_status(ctx: BotContext, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return
    if not get_feature_service().is_enabled("awg2"):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.AWG2_DISABLED)
        return

    try:
        payload = build_awg2_status_payload(ctx.db)
        text = _format_awg2_text(payload)
    except Exception as exc:  # noqa: BLE001
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.AWG2_ERROR.format(detail=exc))
        return

    markup = nav_footer_keyboard(refresh="nav:awg2")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
