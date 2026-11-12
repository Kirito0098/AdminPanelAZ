"""Карточка статуса заявки на доступ (виджет Bot API 10.4).

Виджет в проде живёт только в личке с ботом: HTML фиксируется при отправке,
меняется только ``chat_data``, которое пишет бот. Секретов в карточке нет —
только статус заявки и время отправки.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import TelegramWidget, UserAccessRequest
from app.services import telegram_bot_i18n as i18n
from app.services.app_setting_store import _get_setting
from app.services.telegram_api import (
    answer_widget_query,
    edit_message_caption,
    edit_widget_data,
    send_widget,
)

logger = logging.getLogger(__name__)

KIND_ACCESS_REQUEST = "access_request"

_STATUS_CAPTION = {
    "pending": i18n.WIDGET_ACCESS_PENDING,
    "approved": i18n.WIDGET_ACCESS_APPROVED,
    "rejected": i18n.WIDGET_ACCESS_REJECTED,
}

# HTML неизменен после отправки: тексты статусов статичны, данные — из chatData.
# Без внешних ресурсов и клавиатуры; кнопка «Обновить» — единственный тап.
ACCESS_REQUEST_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
#w p{margin:0}
.ttl{font-weight:600;margin-bottom:6px}
.row{display:flex;gap:8px;align-items:center;margin-bottom:4px}
.meta{color:var(--tg-theme-hint-color);font-size:13px;margin-bottom:10px!important}
#refresh{width:100%}
.err{color:var(--tg-theme-destructive-text-color);font-size:13px;margin-top:6px!important;min-height:16px}
</style></head><body>
<div id="w">
<p class="ttl">🔐 Доступ к панели</p>
<div class="row"><span id="ic"></span><span id="st"></span></div>
<p class="meta" id="mt"></p>
<button id="refresh">Обновить</button>
<p class="err" id="er"></p>
</div>
<script>
(function () {
  var W = window.TelegramWidget;
  var M = {
    pending: ["⏳", "Заявка ожидает решения администратора"],
    approved: ["✅", "Доступ выдан"],
    rejected: ["❌", "Заявка отклонена"],
    unknown: ["❔", "Заявка не найдена"]
  };
  var ic = document.getElementById("ic");
  var st = document.getElementById("st");
  var mt = document.getElementById("mt");
  var er = document.getElementById("er");
  var btn = document.getElementById("refresh");

  function state() {
    try { return JSON.parse((W && W.chatData) || "null") || {}; } catch (e) { return {}; }
  }
  function render(data) {
    var d = data || state();
    var row = M[d.s] || M.unknown;
    ic.textContent = row[0];
    st.textContent = row[1];
    mt.textContent = d.t ? "Отправлена " + d.t : "";
    btn.style.display = d.s === "pending" ? "" : "none";
  }
  function ask(silent) {
    if (!W) { return; }
    W.request("r").then(function (a) {
      var d = null;
      try { d = JSON.parse(a.result || "null"); } catch (e) {}
      if (d && d.s) { render(d); }
      er.textContent = "";
    }, function (e) {
      if (silent || !e) { return; }
      if (e.code === "BUSY") { return; }
      er.textContent = e.code === "RATE_LIMITED"
        ? "Попробуйте через несколько секунд"
        : "Не удалось обновить";
    });
  }
  function askOnce() {
    // Фон — один раз на сообщение: прокрутка чата не должна спамить запросами
    // (лимит Telegram — 5 запросов за 5 секунд на пользователя и бота).
    try {
      if (localStorage.getItem("bg")) { return; }
      localStorage.setItem("bg", "1");
    } catch (e) {}
    ask(true);
  }

  if (W) {
    W.onEvent("chatDataChanged", function () { render(); });
  }
  render();
  if (W) {
    if (W.ready) { W.ready(); }
    askOnce();
  }
  btn.addEventListener("click", function () { ask(false); });
})();
</script>
</body></html>"""


def widgets_enabled() -> bool:
    """Фича-тоггл: гейтит только новые отправки, диспетчер работает всегда."""
    from app.services.feature_guards import get_feature_service

    try:
        return get_feature_service().is_enabled("telegram_widgets")
    except Exception:  # noqa: BLE001 — тоггл не должен ломать выдачу доступа
        logger.warning("telegram widgets: feature check failed", exc_info=True)
        return False


def _bot_token(db: Session) -> str:
    return (_get_setting(db, "telegram_bot_token") or "").strip()


def _status_of(request: UserAccessRequest | None) -> str:
    status = (request.status if request is not None else "") or ""
    return status if status in _STATUS_CAPTION else "unknown"


def _state_text(request: UserAccessRequest | None) -> str:
    status = _status_of(request)
    created = getattr(request, "created_at", None) if request is not None else None
    stamp = created.strftime("%d.%m.%Y %H:%M UTC") if isinstance(created, datetime) else ""
    return json.dumps({"s": status, "t": stamp}, ensure_ascii=False, separators=(",", ":"))


def _caption_for(status: str) -> str:
    return f"{i18n.WIDGET_ACCESS_TITLE} — {_STATUS_CAPTION.get(status, i18n.WIDGET_ACCESS_UNKNOWN)}"


async def send_access_request_card(
    db: Session,
    *,
    bot_token: str,
    chat_id: str | int,
    request: UserAccessRequest,
) -> bool:
    """Отправить карточку заявки; False — вызывающий шлёт обычный текст."""
    if not bot_token or not widgets_enabled():
        return False
    state_text = _state_text(request)
    message = await send_widget(
        bot_token,
        chat_id,
        html=ACCESS_REQUEST_HTML,
        caption=_caption_for(_status_of(request)),
        chat_data=state_text,
    )
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not message_id:
        logger.warning("telegram widgets: sendWidget failed, falling back to text")
        return False
    db.add(
        TelegramWidget(
            chat_id=str(chat_id),
            message_id=int(message_id),
            telegram_id=str(request.telegram_id),
            kind=KIND_ACCESS_REQUEST,
            ref_id=request.id,
            last_state=state_text,
        )
    )
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — карточка уже ушла, без строки просто не обновится
        logger.exception("telegram widgets: card row save failed")
        db.rollback()
    return True


async def refresh_access_request_cards(request_id: int) -> None:
    """Обновить карточки конкретной заявки после approve/reject (best-effort)."""
    from app.database import SessionLocal

    with SessionLocal() as db:
        request = db.get(UserAccessRequest, request_id)
        if request is None:
            return
        bot_token = _bot_token(db)
        if not bot_token:
            return
        rows = (
            db.query(TelegramWidget)
            .filter(
                TelegramWidget.kind == KIND_ACCESS_REQUEST,
                TelegramWidget.ref_id == request_id,
            )
            .all()
        )
        if not rows:
            return
        state_text = _state_text(request)
        caption = _caption_for(_status_of(request))
        changed = False
        for row in rows:
            if (row.last_state or "") == state_text:
                continue
            if not await edit_widget_data(
                bot_token, row.chat_id, row.message_id, chat_data=state_text
            ):
                continue
            await edit_message_caption(bot_token, row.chat_id, row.message_id, caption=caption)
            row.last_state = state_text
            row.updated_at = datetime.utcnow()
            changed = True
        if changed:
            try:
                db.commit()
            except Exception:  # noqa: BLE001 — повторная правка не критична
                logger.exception("telegram widgets: state save failed")
                db.rollback()


def refresh_access_request_cards_sync(request_id: int) -> None:
    """Sync-обёртка для веб-роутов: обновление идёт на bot-loop, ответ API не ждёт."""
    from app.services.telegram_bot_loop import submit_on_bot_loop

    submit_on_bot_loop(
        refresh_access_request_cards(request_id),
        label=f"widget refresh request {request_id}",
    )



async def handle_query(
    db: Session,
    row: TelegramWidget,
    query: dict,
    *,
    bot_token: str,
) -> None:
    """Тап/фон из карточки заявки. Отвечаем всегда — иначе виджет получит TIMEOUT."""
    query_id = str(query.get("id") or "")
    if not query_id:
        return

    data = str(query.get("data") or "").strip()
    request = db.get(UserAccessRequest, row.ref_id) if row.ref_id else None
    status = _status_of(request)
    state_text = _state_text(request)
    reply = state_text if data == "r" else json.dumps({"e": "unknown"}, separators=(",", ":"))
    if bot_token:
        await answer_widget_query(bot_token, query_id, data=reply)
    if data != "r" or not bot_token:
        return
    if (row.last_state or "") == state_text:
        return
    if not await edit_widget_data(bot_token, row.chat_id, row.message_id, chat_data=state_text):
        return
    await edit_message_caption(bot_token, row.chat_id, row.message_id, caption=_caption_for(status))
    row.last_state = state_text
    row.updated_at = datetime.utcnow()
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — ответ уже ушёл, состояние дошлётся следующим тапом
        logger.exception("telegram widgets: state save failed")
        db.rollback()
