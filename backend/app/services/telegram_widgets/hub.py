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

from app.models import NodeStatus, TelegramWidget, User, UserAccessRequest
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
from app.services.user_access_requests import expire_stale_pending_requests

logger = logging.getLogger(__name__)

KIND_HUB = "hub"
_VIEWS = frozenset(
    {
        "menu", "status", "traffic", "requests", "configs",
        "nodes", "more", "cidr", "warper", "awg2", "help", "link",
    }
)
_MAX_QUEUE = 4
_MAX_ROWS = 5
_KIND_CODES = {"new_user": "nu", "add_config": "ac", "extend_access": "ex"}
_PROTO_SHORT = {"openvpn": "OVPN", "wireguard": "WG", "amneziawg2": "AWG2"}

# HTML неизменен после отправки; всё изменяемое — в chatData. Кнопки рисуются
# из состояния (сервер присылает готовый список), поэтому один шаблон на все роли.
HUB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{margin:0;padding:10px 12px;font-size:15px}
p{margin:0}
.h{display:flex;align-items:baseline;gap:8px;margin:2px 0 8px}
.h b{font-size:17px}
.h span{color:var(--tg-theme-hint-color);font-size:12px;margin-left:auto}
.list{border-radius:10px;overflow:hidden;background:var(--tg-theme-secondary-bg-color)}
.item{display:flex;align-items:center;gap:10px;width:100%;padding:10px 12px;background:transparent;border:0;border-top:1px solid var(--tg-theme-section-separator-color);color:var(--tg-theme-text-color);font:inherit;text-align:left}
.item:first-child{border-top:0}
.item:active{background:rgba(127,127,127,.14)}
.ic{width:20px;text-align:center;flex:none}
.lb{flex:1;min-width:0;display:block}
.nm{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sub{display:block;font-size:12px;color:var(--tg-theme-hint-color);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rt{color:var(--tg-theme-hint-color);font-size:16px;flex:none}
.badge{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);border-radius:9px;padding:1px 7px;font-size:12px;font-weight:600;flex:none}
.card{background:var(--tg-theme-secondary-bg-color);border-radius:10px;padding:12px 14px;margin-bottom:8px}
.kpi{display:flex;gap:14px}
.kpi div{flex:1;min-width:0}
.kpi b{display:block;font-size:20px;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kpi span{color:var(--tg-theme-hint-color);font-size:12px}
.kv{display:flex;gap:10px;padding:9px 12px;border-top:1px solid var(--tg-theme-section-separator-color)}
.kv:first-child{border-top:0}
.kv span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv b{font-weight:600;flex:none}
.req{display:flex;align-items:center;gap:8px;padding:9px 12px;border-top:1px solid var(--tg-theme-section-separator-color)}
.req:first-child{border-top:0}
.req .lb{flex:1;min-width:0}
.ok,.no{border:0;border-radius:8px;padding:6px 10px;font:inherit;font-weight:600;background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);flex:none}
.ok{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color)}
.no{color:var(--tg-theme-destructive-text-color)}
.nav{display:flex;gap:8px;margin-top:8px}
.nav button{flex:1;padding:10px;border:0;border-radius:10px;background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);font:inherit;font-size:14px}
.nav button:active{opacity:.7}
.nav .primary{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);font-weight:600}
.err{color:var(--tg-theme-destructive-text-color);font-size:13px;min-height:16px;margin-top:6px}
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
  function head(t, meta) {
    return '<div class="h"><b>' + esc(t) + '</b><span>' + esc(meta || "") + "</span></div>";
  }
  function kv(l, v) {
    return '<div class="kv"><span>' + esc(l) + "</span><b>" + esc(v) + "</b></div>";
  }
  function rowItem(icon, title, sub, action, right, badge) {
    return '<button class="item" data-a="' + esc(action) + '">' +
      '<span class="ic">' + esc(icon) + "</span>" +
      '<span class="lb"><span class="nm">' + esc(title) + "</span>" +
      (sub ? '<span class="sub">' + esc(sub) + "</span>" : "") + "</span>" +
      (badge ? '<span class="badge">' + esc(badge) + "</span>" : "") +
      (right ? '<span class="rt">' + esc(right) + "</span>" : "") + "</button>";
  }
  function nav(extra) {
    return '<div class="nav">' + (extra || "") +
      '<button class="primary" data-a="r">Обновить</button>' +
      '<button data-a="v:menu">Меню</button></div>';
  }
  function guestLine(g) {
    if (g === "pending") { return "ожидает решения"; }
    if (g === "approved") { return "доступ выдан"; }
    if (g === "rejected") { return "заявка отклонена"; }
    return "заявки нет";
  }
  function menu(d) {
    var items = d.m || [];
    var rows = items.map(function (it) {
      return rowItem(it[0], it[1], "", it[2], "", it[3] || "");
    }).join("");
    var meta = d.r === "admin" ? "админ" : d.r === "user" ? "абонент" : "гость";
    return head("Меню", (d.n ? d.n + " · " : "") + meta) +
      '<div class="list">' + rows + "</div>";
  }
  function status(d) {
    if (d.r === "guest") {
      return head("Статус заявки", "") +
        '<div class="list">' + kv("Заявка", guestLine(d.g)) + "</div>" + nav();
    }
    if (d.r === "user") {
      return head("Мой доступ", d.n || "") +
        '<div class="card kpi"><div><b>' + esc(d.u ? d.u.c : 0) + "</b><span>конфигов</span></div>" +
        "<div><b>" + esc((d.u && d.u.until) || "бессрочно") + "</b><span>доступ до</span></div></div>" + nav();
    }
    var s = d.st;
    if (!s) { return head("Статус", "") + '<p class="sub">Нет данных</p>' + nav(); }
    return head("Статус", s.node) +
      '<div class="card kpi"><div><b>' + esc(s.on) + "</b><span>онлайн</span></div>" +
      "<div><b>" + esc(s.cfg) + "</b><span>конфигов</span></div></div>" +
      '<div class="list">' + kv("OpenVPN", s.ovpn) + kv("WireGuard", s.wg) + kv("IP", s.ip) + "</div>" + nav();
  }
  function traffic(d) {
    var t = d.tr;
    if (!t) { return head("Трафик", "") + '<p class="sub">Нет данных</p>' + nav(); }
    var top = (t.top || []).map(function (it) {
      return kv((it.active ? "🟢 " : "⚪ ") + it.name, it.traffic);
    }).join("");
    return head("Трафик", t.node) +
      '<div class="card kpi"><div><b>' + esc(t.d1) + "</b><span>за 24 часа</span></div>" +
      "<div><b>" + esc(t.all) + "</b><span>всего</span></div></div>" +
      '<div class="list">' + kv("Клиентов", t.n) + kv("Онлайн", t.on) + top + "</div>" + nav();
  }
  function requests(d) {
    var q = d.q || [];
    if (!q.length) {
      return head("Заявки", "нет") + '<p class="sub">Ожидающих заявок нет</p>' + nav();
    }
    var rows = q.map(function (it) {
      return '<div class="req"><span class="lb"><span class="nm">' + esc(it.n) + "</span>" +
        '<span class="sub">' + esc(CLOSE[it.k] || "") + " · " + esc(it.m) + ' мин</span></span>' +
        '<button class="ok" data-a="q:a:' + it.i + '">' + (it.k === "ex" ? "30д" : "✓") + "</button>" +
        '<button class="no" data-a="q:r:' + it.i + '">✕</button></div>';
    }).join("");
    return head("Заявки", q.length + " ждут") + '<div class="list">' + rows + "</div>" + nav();
  }
  function configs(d) {
    var c = d.cf;
    if (!c || !c.c || !c.c.length) {
      return head("Конфиги", "") + '<p class="sub">Конфигов нет</p>' + nav();
    }
    var rows = c.c.map(function (it) {
      return '<button class="item" data-a="a:cfg:' + it.i + '">' +
        '<span class="ic">📄</span>' +
        '<span class="lb"><span class="nm">' + esc(it.n) + '</span>' +
        '<span class="sub">' + esc(it.p) + " · " + esc(it.t) + '</span>' +
        '<span class="sub">' + esc(it.nd) + (it.d ? " · до " + esc(it.d) : "") + "</span></span>" +
        '<span class="rt">›</span></button>';
    }).join("");
    var more = c.n > c.c.length
      ? '<p class="sub" style="padding:6px 2px">Показаны ' + c.c.length + " из " + c.n + "</p>" : "";
    return head("Конфиги", c.n + " шт") + '<div class="list">' + rows + "</div>" + more +
      '<div class="nav"><button data-a="a:configs">Все конфиги</button>' +
      '<button data-a="v:menu">← Меню</button></div>';
  }
  function cidr(d) {
    var c = d.cd;
    if (!c) { return head("CIDR", "") + '<p class="sub">Нет данных</p>' + nav(); }
    return head("CIDR") + '<div class="list">' +
      kv("Всего CIDR", c.t) + kv("Обновление", c.s) + kv("Обновлено", c.f) +
      kv("Задача", c.a) + kv("Компиляция", c.c) + kv("Деплой", c.d) + "</div>" + nav();
  }
  function warper(d) {
    var w = d.wp;
    if (!w) { return head("WARP", "") + '<p class="sub">Нет данных</p>' + nav(); }
    return head("WARP", w.n) + '<div class="list">' +
      kv("Хост", w.h) + kv("Статус", w.s) + "</div>" + nav();
  }
  function awg2(d) {
    var a = d.aw;
    if (!a) { return head("AWG2", "") + '<p class="sub">Нет данных</p>' + nav(); }
    if (!a.i) {
      return head("AWG2", a.n) + '<div class="list">' + kv("Установлен", "нет") + "</div>" + nav();
    }
    var top = (a.t || []).map(function (it) {
      return kv(it.n, "↓" + it.rx + " ↑" + it.tx);
    }).join("");
    return head("AWG2", a.n) +
      '<div class="card kpi"><div><b>' + esc(a.on) + "</b><span>онлайн</span></div>" +
      "<div><b>" + esc(a.pe) + "</b><span>пиров</span></div></div>" +
      '<div class="list">' + kv("Интерфейсы", a.if) + top + "</div>" + nav();
  }
  function listView(title, meta, items) {
    var rows = (items || []).map(function (it) {
      return rowItem(it[0], it[1], "", it[2], "", it[3] || "");
    }).join("");
    return head(title, meta) + '<div class="list">' + rows + "</div>" + nav();
  }
  function more(d) { return listView("Ещё", "админ", d.mm); }
  function help(d) { return listView("Помощь", "команды", d.hm); }
  function link(d) {
    return head("Привязка Telegram", "") + '<div class="list">' +
      kv("Команда", "/link КОД") + kv("Код", "выдаёт админ в панели") + "</div>" + nav();
  }
  function nodes(d) {
    var c = d.nl;
    if (!c || !c.c || !c.c.length) {
      return head("Узлы", "") + '<p class="sub">Узлов нет</p>' + nav();
    }
    var icons = {on: "🟢", off: "🔴", unk: "🟡"};
    var labels = {on: "online", off: "offline", unk: "неизвестно"};
    var rows = c.c.map(function (it) {
      return rowItem(icons[it.s] || icons.unk, it.n,
        labels[it.s] || labels.unk, "a:nd:" + it.i, it.a ? "★" : "›");
    }).join("");
    var more = c.n > c.c.length
      ? '<p class="sub" style="padding:6px 2px">Показаны ' + c.c.length + " из " + c.n + "</p>" : "";
    return head("Узлы", c.n + " шт") + '<div class="list">' + rows + "</div>" + more +
      '<div class="nav"><button data-a="a:nodes">Все узлы</button>' +
      '<button data-a="v:menu">← Меню</button></div>';
  }
  function render() {
    var d = state();
    var v = d.v || "menu";
    if (v === "status") { ROOT.innerHTML = status(d); }
    else if (v === "traffic") { ROOT.innerHTML = traffic(d); }
    else if (v === "requests") { ROOT.innerHTML = requests(d); }
    else if (v === "configs") { ROOT.innerHTML = configs(d); }
    else if (v === "nodes") { ROOT.innerHTML = nodes(d); }
    else if (v === "more") { ROOT.innerHTML = more(d); }
    else if (v === "cidr") { ROOT.innerHTML = cidr(d); }
    else if (v === "warper") { ROOT.innerHTML = warper(d); }
    else if (v === "awg2") { ROOT.innerHTML = awg2(d); }
    else if (v === "help") { ROOT.innerHTML = help(d); }
    else if (v === "link") { ROOT.innerHTML = link(d); }
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


def _view_allowed(role: str, view: str) -> bool:
    if view in ("menu", "status", "help", "link"):
        return True
    if view == "traffic":
        return role in ("admin", "user")
    if view == "requests":
        return role == "admin"
    if view == "configs":
        return role == "user"
    if view in ("nodes", "more", "cidr", "warper", "awg2"):
        return role == "admin"
    return False


def _fmt_until(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y") if isinstance(value, datetime) else ""


def _pending_count(db: Session) -> int:
    expire_stale_pending_requests(db)
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
    expire_stale_pending_requests(db)
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


def _configs_view(db: Session, user: User) -> dict | None:
    from app.services.telegram_bot_data import list_user_configs, node_labels
    from app.services.telegram_bot_handlers.traffic import traffic_by_client
    from app.services.traffic_limit import human_bytes

    configs = list_user_configs(db, user)
    if not configs:
        return None
    traffic = traffic_by_client(db, user)
    labels = node_labels(db, {config.node_id for config in configs})
    items: list[dict] = []
    for config in configs[:_MAX_ROWS]:
        expiry = getattr(config, "expires_at", None) or getattr(
            config, "cert_expires_at", None
        )
        items.append(
            {
                "i": config.id,
                "n": (config.client_name or "")[:18],
                "p": _PROTO_SHORT.get(str(config.vpn_type.value), str(config.vpn_type.value)),
                "nd": str(labels.get(config.node_id, config.node_id))[:14],
                "d": expiry.strftime("%d.%m.%y") if isinstance(expiry, datetime) else "",
                "t": human_bytes(traffic.get((config.client_name or "").lower(), 0)) or "0 B",
            }
        )
    return {"n": len(configs), "c": items}


def _nodes_view(db: Session) -> dict | None:
    from app.services.node_manager import get_active_node_id
    from app.services.telegram_bot_handlers.nodes import _list_nodes

    nodes = _list_nodes(db)
    if not nodes:
        return None
    active_id = get_active_node_id(db)
    status_code = {
        NodeStatus.online: "on",
        NodeStatus.offline: "off",
    }
    return {
        "n": len(nodes),
        "c": [
            {
                "i": node.id,
                "n": (node.name or "")[:16],
                "s": status_code.get(node.status, "unk"),
                "a": 1 if node.id == active_id else 0,
            }
            for node in nodes[:_MAX_ROWS]
        ],
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


def _short_ts(value: object) -> str:
    text = str(value or "—").replace("T", " ")
    return text[:16]


def _cidr_view(db: Session) -> dict | None:
    from app.services.tg_mini_status import build_cidr_status_payload

    try:
        data = build_cidr_status_payload(db)
    except Exception:  # noqa: BLE001 — вид не должен ронять меню
        logger.warning("telegram hub: CIDR snapshot failed", exc_info=True)
        return None
    compile_payload = data.get("last_compile") or {}
    deploy_payload = data.get("last_deploy") or {}
    return {
        "t": data.get("total_cidrs", 0),
        "s": _short_ts(data.get("last_refresh_status")),
        "f": _short_ts(data.get("last_refresh_finished")),
        "a": _short_ts(data.get("active_task")),
        "c": _short_ts(compile_payload.get("finished_at") or compile_payload.get("started_at")),
        "d": _short_ts(deploy_payload.get("status") or deploy_payload.get("finished_at")),
    }


def _warper_view(db: Session) -> dict | None:
    from app.services.tg_mini_status import build_warper_status_payload

    try:
        payload = build_warper_status_payload(db)
    except Exception:  # noqa: BLE001
        logger.warning("telegram hub: WARP snapshot failed", exc_info=True)
        return None
    return {
        "n": str(payload.get("node_name") or "—"),
        "h": str(payload.get("node_host") or "—"),
        "s": str(payload.get("status") or "—"),
    }


def _awg2_view(db: Session) -> dict | None:
    from app.services.tg_mini_status import build_awg2_status_payload

    try:
        payload = build_awg2_status_payload(db)
    except Exception:  # noqa: BLE001
        logger.warning("telegram hub: AWG2 snapshot failed", exc_info=True)
        return None
    return {
        "i": 1 if payload.get("installed") else 0,
        "n": str(payload.get("node_name") or "—"),
        "on": payload.get("online_count", 0),
        "pe": payload.get("peer_count", 0),
        "if": str(payload.get("ifaces_summary") or "—")[:24],
        "t": [
            {"n": str(row.get("name") or "")[:14], "rx": row.get("rx"), "tx": row.get("tx")}
            for row in (payload.get("top_traffic") or [])[:3]
        ],
    }


def _help_items(db: Session, role: str) -> list[list[str]]:
    if role == "admin":
        items = [
            ["🏠", "/start — меню", "a:home"],
            ["📈", "/traffic — трафик", "v:traffic"],
            ["📁", "/configs — конфиги", "a:configs"],
            ["🖥", "/nodes — узлы", "v:nodes"],
            ["⚙️", "/settings — настройки", "a:settings"],
            ["🗂", "/cidr — CIDR", "v:cidr"],
            ["🌐", "/warper — WARP", "v:warper"],
            ["🛡️", "/awg2 — AWG2", "v:awg2"],
            ["🎟", "/unlock — коды", "a:unlock"],
            ["🔗", "/link <код> — привязка", "v:link"],
        ]
        if _feature_on("client_portal"):
            items.insert(3, ["🔗", "/portal — ссылка портала", "a:portal"])
        return items
    if role == "user":
        items = [
            ["🏠", "/start — меню", "a:home"],
            ["📈", "/traffic — трафик", "v:traffic"],
            ["📁", "/myconfigs — конфиги", "v:configs"],
            ["🔗", "/link <код> — привязка", "v:link"],
        ]
        if _feature_on("client_portal"):
            items.insert(3, ["🔗", "/portal — ссылка портала", "a:portal"])
        return items
    items = [["🏠", "/start — меню", "a:home"]]
    if _accept_requests(db):
        items.append(["📝", "Запросить доступ", "a:request_access"])
    items.append(["🔗", "/link <код> — привязка", "v:link"])
    return items


def _more_items(db: Session) -> list[list[str]]:
    items: list[list[str]] = []
    if _feature_on("routing"):
        items.append(["🗂", "CIDR", "v:cidr"])
    if _feature_on("warper"):
        items.append(["🌐", "WARP", "v:warper"])
    if _feature_on("awg2"):
        items.append(["🛡️", "AWG2", "v:awg2"])
    if _feature_on("unlock_codes"):
        items.append(["🎟", "Коды доступа", "a:unlock"])
    items.append(["❓", "Помощь", "v:help"])
    return items


def _menu_items(db: Session, user: User | None, role: str, pending: int) -> list[list[str]]:
    if role == "admin":
        return [
            ["📊", "Статус", "v:status"],
            ["📈", "Трафик", "v:traffic"],
            ["📥", "Заявки", "v:requests", pending],
            ["📁", "Конфиги", "a:configs"],
            ["🖥", "Узлы", "v:nodes"],
            ["⚙️", "Настройки", "a:settings"],
            ["⋯", "Ещё", "v:more"],
            ["❓", "Помощь", "v:help"],
        ]
    if role == "user":
        items = [
            ["📈", "Трафик", "v:traffic"],
            ["📁", "Конфиги", "v:configs"],
            ["🔐", "Мой доступ", "v:status"],
        ]
        if _feature_on("client_portal"):
            items.append(["🔗", "Портал", "a:portal"])
        if _feature_on("unlock_codes"):
            items.append(["🎟", "Продлить по ключу", "a:redeem_unlock"])
        items.append(["➕", "Запросить ещё конфиг", "a:request_more_config"])
        if _accept_requests(db):
            items.append(["💳", "Оплатить (чек)", "a:pay_request"])
        if _feature_on("user_messaging"):
            items.append(["✉️", "Написать администратору", "a:admin_chat"])
        items.append(["❓", "Помощь", "v:help"])
        return items
    items = []
    if _accept_requests(db):
        items.append(["📝", "Запросить доступ", "a:request_access"])
    items.append(["🔗", "Привязать код", "v:link"])
    items.append(["🔄", "Обновить статус", "r"])
    items.append(["❓", "Помощь", "v:help"])
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
        if view == "nodes":
            snapshot = _nodes_view(db)
            if snapshot is not None:
                state["nl"] = snapshot
        if view == "more":
            state["mm"] = _more_items(db)
        if view == "cidr":
            snapshot = _cidr_view(db)
            if snapshot is not None:
                state["cd"] = snapshot
        if view == "warper":
            snapshot = _warper_view(db)
            if snapshot is not None:
                state["wp"] = snapshot
        if view == "awg2":
            snapshot = _awg2_view(db)
            if snapshot is not None:
                state["aw"] = snapshot
    elif role == "user":
        if user is not None:
            state["u"] = _user_summary(db, user)
        if view == "configs" and user is not None:
            snapshot = _configs_view(db, user)
            if snapshot is not None:
                state["cf"] = snapshot
    else:
        state["g"] = _guest_status(db, telegram_id)
    if view == "traffic" and user is not None:
        snapshot = _traffic_view(db, user)
        if snapshot is not None:
            state["tr"] = snapshot
    if view == "menu":
        state["m"] = _menu_items(db, user, role, int(state.get("pc") or 0))
    if view == "help":
        state["hm"] = _help_items(db, role)
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
    view: str = "menu",
) -> bool:
    """Отправить hub заново (старое сообщение убираем); False — фолбэк на текст."""
    if not bot_token or not widgets_enabled():
        return False
    if view not in _VIEWS:
        view = "menu"
    state_text = _state_text(build_state(db, telegram_id=str(telegram_id), view=view))
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
        actions = {"configs", "nodes", "settings", "more", "help", "home"}
        for key, action in (
            ("routing", "cidr"),
            ("warper", "warper"),
            ("awg2", "awg2"),
            ("unlock_codes", "unlock"),
        ):
            if _feature_on(key):
                actions.add(action)
        return actions
    actions = {"configs", "help", "home", "request_more_config"}
    if _feature_on("client_portal"):
        actions.add("portal")
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
    if action == "portal":
        from app.services.telegram_bot_handlers.portal import handle_portal

        await handle_portal(ctx)
        return
    if action.startswith("cfg:") and action[4:].isdigit():
        from app.services.telegram_bot_handlers.configs import handle_config_callback

        await handle_config_callback(ctx, int(action[4:]))
        return
    if action.startswith("nd:") and action[3:].isdigit():
        from app.services.telegram_bot_handlers.nodes import handle_node_detail

        await handle_node_detail(ctx, int(action[3:]))
        return
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
        if view not in _VIEWS or not _view_allowed(_role(user), view):
            await answer(json.dumps({"e": "forbidden"}, separators=(",", ":")))
            return
        await answer(json.dumps({"ok": 1}, separators=(",", ":")))
        await _set_view(db, row, view=view, bot_token=bot_token)
        return

    if data.startswith("a:"):
        action = data[2:]
        role = _role(user)
        prefixed_ok = (
            action.startswith("cfg:") and role in ("admin", "user")
        ) or (action.startswith("nd:") and role == "admin")
        if not prefixed_ok and action not in _allowed_actions(db, user, role):
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
