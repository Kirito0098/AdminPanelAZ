"""Telegram bot /cidr — CIDR pipeline status (Phase 4, admin)."""

from __future__ import annotations

from sqlalchemy import func

from app.models import ProviderMeta
from app.services.cidr.cidr_tasks import find_any_active_pipeline_task
from app.services.cidr.pipeline.deploy import list_compile_artifacts
from app.services.telegram_bot_handlers.base import BotContext, is_admin, unlinked_message
from app.services.telegram_bot_handlers.ui import nav_footer_keyboard, send_or_edit
from app.services import telegram_bot_i18n as i18n


def _summarize_last_compile() -> str:
    from app.routers.cidr_db import _summarize_last_compile as _compile

    row = _compile()
    if not row:
        return i18n.CIDR_NONE
    return str(row.get("finished_at") or row.get("started_at") or i18n.CIDR_NONE)


def _summarize_last_deploy() -> str:
    from app.routers.cidr_db import _summarize_last_deploy as _deploy

    row = _deploy()
    if not row:
        return i18n.CIDR_NONE
    status = row.get("status") or row.get("finished_at") or i18n.CIDR_NONE
    return str(status)


def _format_cidr_status(db) -> str:
    from app.cidr_database import CidrSessionLocal
    from app.services.cidr.pipeline.db_service import CidrDbUpdaterService

    total_cidrs = int(db.query(func.coalesce(func.sum(ProviderMeta.cidr_count), 0)).scalar() or 0)
    active = find_any_active_pipeline_task()
    active_label = active.get("type") if active else i18n.CIDR_NONE

    cidr_session = CidrSessionLocal()
    try:
        svc = CidrDbUpdaterService(db=db, cidr_db=cidr_session)
        status_data = svc.get_db_status()
    finally:
        cidr_session.close()

    last_status = status_data.get("last_refresh_status") or i18n.CIDR_NONE
    last_finished = status_data.get("last_refresh_finished") or i18n.CIDR_NONE

    compile_hint = i18n.CIDR_NONE
    if list_compile_artifacts():
        compile_hint = _summarize_last_compile()

    return i18n.CIDR_BODY.format(
        title=i18n.CIDR_TITLE,
        total=total_cidrs,
        last_status=last_status,
        last_finished=last_finished,
        active_task=active_label,
        last_compile=compile_hint,
        last_deploy=_summarize_last_deploy(),
    )


async def handle_cidr_status(ctx: BotContext, *, message_id: int | None = None) -> None:
    if ctx.user is None:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, unlinked_message())
        return
    if not is_admin(ctx.user):
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.ADMIN_ONLY)
        return

    try:
        text = _format_cidr_status(ctx.db)
    except Exception as exc:
        from app.services.telegram_api import send_message

        await send_message(ctx.bot_token, ctx.chat_id, i18n.CIDR_ERROR.format(detail=exc))
        return

    markup = nav_footer_keyboard(refresh="nav:cidr")
    await send_or_edit(ctx, text, markup=markup, message_id=message_id)
