"""Hub-виджет: меню, статус, трафик и заявки в одном сообщении.

Один виджет на пользователя. Вид переключается через ``chat_data`` — новых
сообщений при навигации не появляется. Действия, которым нужен отдельный экран
(конфиги, узлы, настройки), уходят в существующие обработчики бота.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import TelegramWidget, User, UserAccessRequest
from app.services import telegram_bot_i18n as i18n
from app.services.app_setting_store import _get_setting
from app.services.telegram_api import (
    answer_widget_query,
    delete_message,
    edit_widget_data,
    send_widget,
)
from app.services.telegram_bot_handlers.base import is_admin, resolve_user
from app.services.telegram_widgets.access_request import (
    refresh_access_request_cards,
    widgets_enabled,
)

logger = logging.getLogger(__name__)

KIND_HUB = "hub"
_VIEWS = frozenset({"menu", "status", "traffic", "requests"})
_MAX_QUEUE = 4
_KIND_CODES = {"new_user": "nu", "add_config": "ac", "extend_access": "ex"}

# HTML неизменен после отправки; всё изменяемое — в chatData. Кнопки рисуются
# из состояния (сервер присылает готовый список), поэтому один шаблон на все роли.
HUB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{margin:0}
p{margin:0}
.t{font-weight:600;margin-bottom:6px}
.m{color:var(--tg-theme-hint-color);font-size:13px;margin-bottom:8px}
.grid{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}
.grid button{flex:1 1 45%;min-width:45%}
.row{display:flex;gap:8px;margin-bottom:3px;font-size:14px}
.row b{margin-left:auto}
.top{font-size:13px;margin:2px 0;color:var(--tg-theme-hint-color)}
.nav{display:flex;gap:6px;margin-top:8px}
.nav button{flex:1}
.req{display:flex;gap:6px;align-items:center;margin-bottom:4px}
.req span{flex:1;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.req button{padding:2px 8px;min-width:36px}
.err{color:var(--tg-theme-destructive-text-color);font-size:13px;min-height:16px;margin-top:4px}
</style></head><body>
<div id="v"></div>
<p class="err" id="e"></p>
<script>
(function () {
  var W = window.TelegramWidget;
  var ROOT = document.getElementById("v");
  var ERR = document.getElementById("e");
  var CLOSE = {nu: "доступ", ac: "конфиг", ex: "продление"};
  var MSG = {
    forbidden: "Нет прав",
    decided: "Заявка уже обработана",
    preset: "Нужен шаблон по умолчанию — откройте панель",
    unsupported: "Этот тип заявки — в панели",
    unknown: "Неизвестное действие",
    error: "Не удалось, попробуйте ещё раз"
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c];
    });
  }
  function state() {
    try { return JSON.parse((W && W.chatData) || "null") || {}; } catch (e) { return {}; }
  }
  function row(label, value) {
    return '<div class="row"><span>' + esc(label) + "</span><b>" + esc(value) + "</b></div>";
  }
  function nav() {
    return '<div class="nav"><button data-a="r">🔄 Обновить</button>' +
      '<button data-a="v:menu">← Меню</button></div>';
  }
  function menu(d) {
    var items = d.m || [];
    var buttons = items.map(function (it) {
      return '<button data-a="' + esc(it[2]) + '">' + esc(it[0]) + " " + esc(it[1]) + "</button>";
    }).join("");
    var meta = "";
    if (d.r === "admin") { meta = "Ожидают решения: " + (d.pc || 0); }
    else if (d.r === "user" && d.u) { meta = "Конфигов: " + d.u.c + (d.u.until ? " · доступ до " + d.u.until : ""); }
    else if (d.r === "guest") { meta = guestLine(d.g); }
    return '<p class="t">Меню</p><p class="m">' +
      (d.n ? esc(d.n) + " · " : "") + esc(meta) + "</p>" +
      '<div class="grid">' + buttons + "</div>";
  }
  function guestLine(g) {
    if (g === "pending") { return "Заявка ожидает решения"; }
    if (g === "approved") { return "Доступ выдан"; }
    if (g === "rejected") { return "Заявка отклонена"; }
    return "Заявки нет";
  }
  function status(d) {
    if (d.r === "guest") { return '<p class="t">Статус заявки</p><p class="m">' + esc(guestLine(d.g)) + "</p>" + nav(); }
    var s = d.st;
    if (!s) { return '<p class="t">Статус</p><p class="m">Нет данных</p>' + nav(); }
    return '<p class="t">Статус панели</p>' +
      row("Узел", s.node) + row("Конфигов", s.cfg) + row("Онлайн", s.on) +
      row("OpenVPN", s.ovpn) + row("WireGuard", s.wg) + row("IP", s.ip) + nav();
  }
  function traffic(d) {
    var t = d.tr;
    if (!t) { return '<p class="t">Трафик</p><p class="m">Нет данных</p>' + nav(); }
    var top = (t.top || []).map(function (it) {
      return '<p class="top">' + (it.active ? "🟢" : "⚪") + " " + esc(it.name) + " — " + esc(it.traffic) + "</p>";
    }).join("");
    return '<p class="t">Трафик</p>' + row("Узел", t.node) + row("Учтено", t.n) +
      row("Онлайн", t.on) + row("За 24 часа", t.d1) + row("Всего", t.all) + top + nav();
  }
  function requests(d) {
    var q = d.q || [];
    if (!q.length) { return '<p class="t">Заявки</p><p class="m">Ожидающих нет</p>' + nav(); }
    var rows = q.map(function (it) {
      return '<div class="req"><span>' + esc(it.n) + " · " + esc(CLOSE[it.k] || "") +
        " · " + esc(it.m) + " мин</span>" +
        '<button data-a="q:a:' + it.i + '">' + (it.k === "ex" ? "30д" : "✓") + "</button>" +
        '<button data-a="q:r:' + it.i + '">✕</button></div>';
    }).join("");
    return '<p class="t">Заявки</p>' + rows + nav();
  }
  function render() {
    var d = state();
    var v = d.v || "menu";
    if (v === "status") { ROOT.innerHTML = status(d); }
    else if (v === "traffic") { ROOT.innerHTML = traffic(d); }
    else if (v === "requests") { ROOT.innerHTML = requests(d); }
    else { ROOT.innerHTML = menu(d); }
    bind();
  }
  function bind() {
    var els = document.querySelectorAll("[data-a]");
    for (var i = 0; i < els.length; i++) { els[i].addEventListener("click", tap); }
  }
  function ask(a) {
    if (!W) { return; }
    ERR.textContent = "";
    W.request(a).then(function (r) {
      var d = null;
      try { d = JSON.parse(r.result || "null"); } catch (e) {}
      if (d && d.e) { ERR.textContent = MSG[d.e] || MSG.unknown; }
    }, function (e) {
      if (!e) { return; }
      if (e.code === "BUSY") { return; }
      ERR.textContent = e.code === "RATE_LIMITED" ? "Попробуйте через пару секунд" : "Не удалось";
    });
  }
  function tap(ev) {
    var a = ev.currentTarget.getAttribute("data-a");
    if (a) { ask(a); }
  }

  if (W) { W.onEvent("chatDataChanged", render); }
  render();
  if (W && W.ready) { W.ready(); }
  var d0 = state();
  if (W && d0.v && d0.v !== "menu") { W.request("r").then(function () {}, function () {}); }
})();
</script>
</body></html>"""


def _state_text(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, separators=(",", ":"))


def _role(user: User | None) -> str:
    if user is None:
        return "guest"
    return "admin" if is_admin(user) else "user"


def _fmt_until(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y") if isinstance(value, datetime) else ""


def _pending_count(db: Session) -> int:
    return (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.status == "pending")
        .count()
    )


def _guest_status(db: Session, telegram_id: str) -> str:
    row = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.telegram_id == str(telegram_id))
        .order_by(UserAccessRequest.id.desc())
        .first()
    )
    return row.status if row is not None else "none"


def _queue_snapshot(db: Session) -> list[dict]:
    rows = (
        db.query(UserAccessRequest)
        .filter(UserAccessRequest.status == "pending")
        .order_by(UserAccessRequest.created_at.asc())
        .limit(_MAX_QUEUE)
        .all()
    )
    now = datetime.utcnow()
    items: list[dict] = []
    for row in rows:
        name = (row.telegram_username or row.telegram_name or row.telegram_id or "").strip()
        created = row.created_at or now
        minutes = max(0, int((now - created).total_seconds() // 60))
        items.append(
            {
                "i": row.id,
                "n": name[:18],
                "k": _KIND_CODES.get(row.request_type, "nu"),
                "m": minutes,
            }
        )
    return items


def _status_snapshot(db: Session, user: User) -> dict | None:
    from app.services.telegram_bot_data import build_dashboard_summary

    try:
        summary = build_dashboard_summary(db, user)
    except Exception:  # noqa: BLE001 — статус не должен ломать меню
        logger.warning("telegram hub: status snapshot failed", exc_info=True)
        return None
    return {
        "node": str(summary["node_name"]),
        "cfg": summary["total_configs"],
        "on": summary["connected_openvpn"] + summary["connected_wireguard"],
        "ovpn": summary["connected_openvpn"],
        "wg": summary["connected_wireguard"],
        "ip": summary["server_ip"] or "—",
    }


def _traffic_view(db: Session, user: User) -> dict | None:
    from app.services.telegram_bot_handlers.traffic import traffic_snapshot

    snapshot, _reason = traffic_snapshot(db, user, top_limit=3)
    if snapshot is None:
        return None
    return {
        "node": snapshot["node"],
        "n": snapshot["count"],
        "on": snapshot["active"],
        "d1": snapshot["traffic_1d"],
        "all": snapshot["total_all"],
        "top": snapshot["top"],
    }


def _user_summary(db: Session, user: User) -> dict:
    from app.services.telegram_bot_data import list_user_configs

    return {
        "c": len(list_user_configs(db, user)),
        "until": _fmt_until(user.access_until),
    }


def _feature_on(key: str) -> bool:
    from app.services.feature_guards import get_feature_service

    try:
        return get_feature_service().is_enabled(key)
    except Exception:  # noqa: BLE001 — меню не падает из-за чтения тоглов
        logger.warning("telegram hub: feature %s check failed", key, exc_info=True)
        return False


def _accept_requests(db: Session) -> bool:
    from app.services.user_access_requests import _accept_requests as accept

    return accept(db)


def _menu_items(db: Session, user: User | None, role: str, pending: int) -> list[list[str]]:
    if role == "admin":
        return [
            ["📊", "Статус", "v:status"],
            ["📈", "Трафик", "v:traffic"],
            ["📥", f"Заявки ({pending})", "v:requests"],
            ["📁", "Конфиги", "a:configs"],
            ["🖥", "Узлы", "a:nodes"],
            ["⚙️", "Настройки", "a:settings"],
            ["⋯", "Ещё", "a:more"],
            ["❓", "Помощь", "a:help"],
        ]
    if role == "user":
        items = [
            ["📈", "Трафик", "v:traffic"],
            ["📁", "Конфиги", "a:configs"],
        ]
        if _feature_on("unlock_codes"):
            items.append(["🎟", "Продлить по ключу", "a:redeem_unlock"])
        items.append(["➕", "Запросить ещё конфиг", "a:request_more_config"])
        if _accept_requests(db):
            items.append(["💳", "Оплатить (чек)", "a:pay_request"])
        if _feature_on("user_messaging"):
            items.append(["✉️", "Написать администратору", "a:admin_chat"])
        items.append(["❓", "Помощь", "a:help"])
        return items
    items = []
    if _accept_requests(db):
        items.append(["📝", "Запросить доступ", "a:request_access"])
    items.append(["🔗", "Привязать код", "a:link_code"])
    items.append(["🔄", "Обновить статус", "r"])
    items.append(["❓", "Помощь", "a:help"])
    return items


def build_state(db: Session, *, telegram_id: str, view: str = "menu") -> dict:
    user = resolve_user(db, str(telegram_id))
    role = _role(user)
    state: dict = {"v": view, "r": role}
    if user is not None:
        state["n"] = user.username
    if role == "admin":
        state["pc"] = _pending_count(db)
        if view == "status" and user is not None:
            snapshot = _status_snapshot(db, user)
            if snapshot is not None:
                state["st"] = snapshot
        if view == "requests":
            state["q"] = _queue_snapshot(db)
    elif role == "user":
        if user is not None:
            state["u"] = _user_summary(db, user)
    else:
        state["g"] = _guest_status(db, telegram_id)
    if view == "traffic" and user is not None:
        snapshot = _traffic_view(db, user)
        if snapshot is not None:
            state["tr"] = snapshot
    if view == "menu":
        state["m"] = _menu_items(db, user, role, int(state.get("pc") or 0))
    return state


def _latest_hub(db: Session, telegram_id: str) -> TelegramWidget | None:
    return (
        db.query(TelegramWidget)
        .filter(
            TelegramWidget.kind == KIND_HUB,
            TelegramWidget.telegram_id == str(telegram_id),
        )
        .order_by(TelegramWidget.id.desc())
        .first()
    )


async def send_hub(
    db: Session,
    *,
    bot_token: str,
    chat_id: str | int,
    telegram_id: str,
    reply_markup: dict | None = None,
) -> bool:
    """Отправить hub заново (старое сообщение убираем); False — фолбэк на текст."""
    if not bot_token or not widgets_enabled():
        return False
    state_text = _state_text(build_state(db, telegram_id=str(telegram_id), view="menu"))
    row = _latest_hub(db, str(telegram_id))
    if row is not None:
        await delete_message(bot_token, row.chat_id, row.message_id)
        db.delete(row)
        db.commit()

    message = await send_widget(
        bot_token,
        chat_id,
        html=HUB_HTML,
        caption=i18n.WIDGET_HUB_CAPTION,
        chat_data=state_text,
        reply_markup=reply_markup,
    )
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not message_id:
        logger.warning("telegram hub: sendWidget failed, falling back to text menu")
        return False
    db.add(
        TelegramWidget(
            chat_id=str(chat_id),
            message_id=int(message_id),
            telegram_id=str(telegram_id),
            kind=KIND_HUB,
            ref_id=None,
            last_state=state_text,
        )
    )
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — меню откроется, просто не обновится
        logger.exception("telegram hub: row save failed")
        db.rollback()
    return True


def _current_view(row: TelegramWidget) -> str:
    try:
        state = json.loads(row.last_state or "{}")
    except ValueError:
        return "menu"
    view = str(state.get("v") or "menu")
    return view if view in _VIEWS else "menu"


async def _set_view(
    db: Session,
    row: TelegramWidget,
    *,
    view: str,
    bot_token: str,
) -> None:
    state_text = _state_text(build_state(db, telegram_id=row.telegram_id, view=view))
    if (row.last_state or "") == state_text:
        return
    if not await edit_widget_data(bot_token, row.chat_id, row.message_id, chat_data=state_text):
        return
    row.last_state = state_text
    row.updated_at = datetime.utcnow()
    try:
        db.commit()
    except Exception:  # noqa: BLE001 — ответ уже ушёл
        logger.exception("telegram hub: state save failed")
        db.rollback()


def _allowed_actions(db: Session, _user: User | None, role: str) -> set[str]:
    if role == "guest":
        actions = {"help", "home", "link_code"}
        if _accept_requests(db):
            actions.add("request_access")
        return actions
    if role == "admin":
        return {"configs", "nodes", "settings", "more", "help", "home"}
    actions = {"configs", "help", "home", "request_more_config"}
    if _feature_on("unlock_codes"):
        actions.add("redeem_unlock")
    if _accept_requests(db):
        actions.add("pay_request")
    if _feature_on("user_messaging"):
        actions.add("admin_chat")
    return actions


def _profile(from_user: dict) -> tuple[str, str]:
    username = str(from_user.get("username") or "").strip()
    name = " ".join(
        str(part).strip()
        for part in (from_user.get("first_name"), from_user.get("last_name"))
        if part
    ).strip()
    return username, name


async def _run_action(
    db: Session,
    row: TelegramWidget,
    query: dict,
    action: str,
    *,
    mini_app_url: str,
) -> None:
    from app.services.telegram_bot import _build_context
    from app.services.telegram_bot_handlers.menu import _dispatch_action

    username, name = _profile(query.get("from") or {})
    chat_id: int | str = int(row.chat_id) if str(row.chat_id).isdigit() else row.chat_id
    ctx = _build_context(
        db,
        chat_id=chat_id,
        telegram_user_id=str(row.telegram_id),
        mini_app_url=mini_app_url,
        telegram_username=username,
        telegram_name=name,
    )
    await _dispatch_action(ctx, action)


def _decide(db: Session, request_id: int, *, approve: bool, admin: User) -> str:
    from app.services.user_access_requests import (
        AlreadyDecided,
        _default_preset_id,
        approve_request,
        reject_request,
    )

    request = db.get(UserAccessRequest, request_id)
    if request is None or request.status != "pending":
        return "decided"
    try:
        if not approve:
            reject_request(db, request_id=request_id, admin=admin)
        elif request.request_type == "new_user":
            preset_id = _default_preset_id(db)
            if preset_id is None:
                return "preset"
            approve_request(db, request_id=request_id, admin=admin, preset_id=preset_id)
        elif request.request_type == "add_config":
            approve_request(
                db,
                request_id=request_id,
                admin=admin,
                ad_hoc={"count": max(1, int(request.requested_count or 1))},
            )
        elif request.request_type == "extend_access":
            approve_request(db, request_id=request_id, admin=admin, ad_hoc={"days": 30})
        else:
            return "unsupported"
    except AlreadyDecided:
        return "decided"
    except Exception:  # noqa: BLE001 — решение не должно ронять виджет
        logger.exception("telegram hub: decide request %s failed", request_id)
        return "error"
    return "ok"


async def handle_query(
    db: Session,
    row: TelegramWidget,
    query: dict,
    *,
    bot_token: str,
    mini_app_url: str = "",
) -> None:
    query_id = str(query.get("id") or "")
    if not query_id:
        return
    data = str(query.get("data") or "").strip()
    user = resolve_user(db, str(row.telegram_id))

    async def answer(payload: str | None = None) -> None:
        if bot_token:
            await answer_widget_query(bot_token, query_id, data=payload)

    if data == "r":
        await answer(json.dumps({"ok": 1}, separators=(",", ":")))
        await _set_view(db, row, view=_current_view(row), bot_token=bot_token)
        return

    if data.startswith("v:"):
        view = data[2:] or "menu"
        if view not in _VIEWS:
            await answer(json.dumps({"e": "unknown"}, separators=(",", ":")))
            return
        await answer(json.dumps({"ok": 1}, separators=(",", ":")))
        await _set_view(db, row, view=view, bot_token=bot_token)
        return

    if data.startswith("a:"):
        action = data[2:]
        role = _role(user)
        if action not in _allowed_actions(db, user, role):
            await answer(json.dumps({"e": "forbidden"}, separators=(",", ":")))
            return
        await answer(json.dumps({"ok": 1}, separators=(",", ":")))
        try:
            await _run_action(db, row, query, action, mini_app_url=mini_app_url)
        except Exception:  # noqa: BLE001 — действие не должно ронять виджет
            logger.exception("telegram hub: action %s failed", action)
        await _set_view(db, row, view="menu", bot_token=bot_token)
        return

    if data.startswith("q:"):
        parts = data.split(":", 2)
        if len(parts) != 3 or not parts[2].isdigit():
            await answer(json.dumps({"e": "unknown"}, separators=(",", ":")))
            return
        if _role(user) != "admin" or user is None:
            await answer(json.dumps({"e": "forbidden"}, separators=(",", ":")))
            return
        code = _decide(db, int(parts[2]), approve=parts[1] == "a", admin=user)
        await answer(json.dumps({"ok": 1} if code == "ok" else {"e": code}, separators=(",", ":")))
        if code == "ok":
            try:
                await refresh_access_request_cards(int(parts[2]))
            except Exception:  # noqa: BLE001 — карточка заявителя не критична
                logger.warning("telegram hub: applicant card refresh failed", exc_info=True)
            await _set_view(db, row, view="requests", bot_token=bot_token)
        return

    await answer(json.dumps({"e": "unknown"}, separators=(",", ":")))
