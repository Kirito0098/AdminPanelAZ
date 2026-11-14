"""Карточка клиентского портала для абонента в боте (Bot API 10.4)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import TelegramWidget, User
from app.services.client_portal import (
    _active_user_token,
    get_or_create_user_portal_token,
    portal_page_url,
    resolve_portal_base_url,
    rotate_user_portal_token,
)
from app.services.feature_guards import get_feature_service
from app.services.portal_link_settings import (
    get_portal_link_ttl_days,
    portal_link_expires_at,
)
from app.services.telegram_api import (
    answer_widget_query,
    delete_message,
    edit_widget_data,
    send_widget,
)
from app.services.telegram_widgets.access_request import widgets_enabled

logger = logging.getLogger(__name__)

KIND_PORTAL = "portal"

PORTAL_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{margin:0;padding:10px 12px;font-size:15px}
p{margin:0}
.h{font-size:17px;font-weight:600;margin-bottom:8px}
.card{background:var(--tg-theme-secondary-bg-color);border-radius:10px;padding:12px;margin-bottom:4px}
.u{font-family:ui-monospace,monospace;font-size:11px;word-break:break-all}
.m{color:var(--tg-theme-hint-color);font-size:12px;margin-top:4px}
.nav{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.nav button{flex:1 1 40%;padding:9px;border:0;border-radius:9px;background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);font:inherit;font-size:13px}
.nav .p{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);font-weight:600}
.nav button:active{opacity:.7}
.err{color:var(--tg-theme-destructive-text-color);font-size:13px;min-height:16px;margin-top:6px}
</style></head><body>
<p class="h">🔗 Клиентский портал</p>
<div id="v"></div>
<p class="err" id="e"></p>
<script>
(function () {
  var W = window.TelegramWidget;
  var ROOT = document.getElementById("v");
  var ERR = document.getElementById("e");
  var CONFIRM = false;
  var MSG = {
    disabled: "Модуль клиентского портала выключен",
    noportal: "Портал ещё не настроен — обратитесь к администратору",
    error: "Не удалось, попробуйте ещё раз",
    unknown: "Неизвестное действие"
  };

  function state() {
    try { return JSON.parse((W && W.chatData) || "null") || {}; } catch (e) { return {}; }
  }
  function render(d) {
    d = d || state();
    var out = "";
    if (!d.a) {
      out = '<p class="card m">Портал ещё не настроен.</p>';
    } else if (d.e && d.u) {
      out = '<div class="card"><p class="u">' + d.u + "</p>" +
        '<p class="m">' + (d.x ? "Действует до " + d.x : "Срок действия не ограничен") + "</p></div>" +
        '<div class="nav"><button data-copy="' + d.u + '">Скопировать</button>' +
        '<button data-open="' + d.u + '">Открыть</button>' +
        (CONFIRM
          ? '<button class="p" data-a="r">Точно</button><button data-cancel="1">Отмена</button>'
          : '<button data-ask="1">Перевыпустить</button>') + "</div>";
    } else {
      out = '<p class="card m">' + (d.q ? "Срок действия ссылки истёк." : "Ссылка ещё не создана.") + "</p>" +
        '<div class="nav"><button class="p" data-a="c">' +
        (d.q ? "Получить новую" : "Получить ссылку") + "</button></div>";
    }
    ROOT.innerHTML = out;
    bind();
  }
  function bind() {
    var els = document.querySelectorAll("[data-copy],[data-open],[data-a],[data-ask],[data-cancel]");
    for (var i = 0; i < els.length; i++) { els[i].addEventListener("click", tap); }
  }
  function tap(ev) {
    var el = ev.currentTarget;
    var copy = el.getAttribute("data-copy");
    if (copy) {
      try { W.copyText(copy); ERR.textContent = "Скопировано"; } catch (e) { ERR.textContent = "Не удалось скопировать"; }
      return;
    }
    var open = el.getAttribute("data-open");
    if (open) { W.openLink(open); return; }
    if (el.getAttribute("data-ask")) { CONFIRM = true; render(); return; }
    if (el.getAttribute("data-cancel")) { CONFIRM = false; render(); return; }
    var a = el.getAttribute("data-a");
    if (a) { req(a); }
  }
  function req(a) {
    ERR.textContent = "";
    W.request(a).then(function (r) {
      var d = null;
      try { d = JSON.parse(r.result || "null"); } catch (e) {}
      if (d && d.e) { ERR.textContent = MSG[d.e] || MSG.unknown; }
      CONFIRM = false;
    }, function (e) {
      if (e && e.code !== "BUSY") {
        ERR.textContent = e.code === "RATE_LIMITED" ? "Попробуйте через пару секунд" : "Не удалось";
      }
    });
  }

  if (W) { W.onEvent("chatDataChanged", function () { render(); }); }
  render();
  if (W && W.ready) { W.ready(); }
})();
</script>
</body></html>"""


def _state(db: Session, user: User) -> dict:
    ttl_days = get_portal_link_ttl_days(db)
    if not resolve_portal_base_url(db):
        return {"a": 0, "t": ttl_days}
    row = _active_user_token(db, user_id=user.id)
    if row is None:
        return {"a": 1, "e": 0, "t": ttl_days, "q": 0}
    expires = portal_link_expires_at(row.created_at, ttl_days)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "a": 1,
        "e": 1,
        "u": portal_page_url(db, row.token),
        "x": expires.strftime("%d.%m.%Y") if expires else "",
        "t": ttl_days,
        "q": 1 if (expires is not None and now >= expires) else 0,
    }


def _state_text(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


async def send_portal_card(
    db: Session,
    *,
    bot_token: str,
    chat_id: str | int,
    telegram_id: str,
    user: User,
) -> bool:
    """Отправить карточку портала (старую убираем); False — вызывающий шлёт текст."""
    if not bot_token or not widgets_enabled():
        return False
    if not get_feature_service().is_enabled("client_portal"):
        return False
    row = (
        db.query(TelegramWidget)
        .filter(
            TelegramWidget.kind == KIND_PORTAL,
            TelegramWidget.telegram_id == str(telegram_id),
        )
        .order_by(TelegramWidget.id.desc())
        .first()
    )
    if row is not None:
        await delete_message(bot_token, row.chat_id, row.message_id)
        db.delete(row)
        db.commit()
    state_text = _state_text(_state(db, user))
    message = await send_widget(
        bot_token,
        chat_id,
        html=PORTAL_HTML,
        caption="🔗 Клиентский портал",
        chat_data=state_text,
    )
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not message_id:
        logger.warning("telegram portal: sendWidget failed, falling back to text")
        return False
    db.add(
        TelegramWidget(
            chat_id=str(chat_id),
            message_id=int(message_id),
            telegram_id=str(telegram_id),
            kind=KIND_PORTAL,
            ref_id=user.id,
            last_state=state_text,
        )
    )
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — карточка уже ушла
        logger.exception("telegram portal: row save failed")
        db.rollback()
    return True


async def handle_query(
    db: Session,
    row: TelegramWidget,
    query: dict,
    *,
    bot_token: str,
) -> None:
    query_id = str(query.get("id") or "")
    if not query_id:
        return
    data = str(query.get("data") or "").strip()
    user = db.get(User, row.ref_id) if row.ref_id else None
    if user is None:
        user = db.query(User).filter(User.telegram_id == str(row.telegram_id)).first()
    if user is None:
        if bot_token:
            await answer_widget_query(bot_token, query_id)
        return
    if not get_feature_service().is_enabled("client_portal"):
        if bot_token:
            await answer_widget_query(
                bot_token, query_id, data=json.dumps({"e": "disabled"}, separators=(",", ":"))
            )
        return

    code = "ok"
    try:
        if data == "c":
            current = _active_user_token(db, user_id=user.id)
            ttl = get_portal_link_ttl_days(db)
            if current is not None and _expired(current, ttl):
                rotate_user_portal_token(db, user_id=user.id)
            elif current is None:
                get_or_create_user_portal_token(db, user_id=user.id)
        elif data == "r":
            rotate_user_portal_token(db, user_id=user.id)
        else:
            code = "unknown"
    except Exception:  # noqa: BLE001 — не роняем обработку апдейтов
        logger.exception("telegram portal: action %s failed", data)
        code = "error"

    if bot_token:
        await answer_widget_query(
            bot_token, query_id, data=json.dumps({"ok": 1} if code == "ok" else {"e": code}, separators=(",", ":"))
        )
    if code != "ok" or not bot_token:
        return
    state_text = _state_text(_state(db, user))
    if (row.last_state or "") == state_text:
        return
    if await edit_widget_data(bot_token, row.chat_id, row.message_id, chat_data=state_text):
        row.last_state = state_text
        row.updated_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("telegram portal: state save failed")
            db.rollback()


def _expired(row, ttl_days: int) -> bool:
    expires = portal_link_expires_at(row.created_at, ttl_days)
    return bool(expires is not None and datetime.now(timezone.utc).replace(tzinfo=None) >= expires)
