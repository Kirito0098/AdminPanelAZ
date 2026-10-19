"""Stage 4: массовая выдача / снятие / перенос серверов пользователям.

Схема работы: область выбора → предпросмотр (что именно изменится) → одна
фоновая задача ``bulk_user_nodes`` (``subject_key="bulk_nodes"``), которая
обрабатывает пользователей последовательно. Сеть трогается только в
применении — через Stage 1 ``provision_config`` / ``deprovision_config``;
активный узел панели не используется никогда.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import SessionLocal
from app.models import (
    BackgroundTask,
    Node,
    NodeStatus,
    User,
    UserNodeAssignment,
    UserRole,
    VpnConfig,
    VpnType,
)

# Реэкспорт моделей запроса: диалог и тесты импортируют их отсюда.
from app.schemas import BulkNodesRequest, BulkNodesScope
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import _submit_in_current_context, background_task_service
from app.services.bulk_user_nodes_notify import (
    ACTION_TITLES,
    TelegramBulkThrottle,
    maybe_notify_after_user,
    render_bulk_notify_text,
)
from app.services.client_names import parse_plan_indexes, plan_name_for_index
from app.services.config_provisioning import deprovision_config, provision_config
from app.services.expected_node import forget_confirmed_node
from app.services.feature_guards import get_feature_service
from app.services.node_sync.groups import find_sync_group_containing_node
from app.services.user_provisioning import (
    _FEATURE_PROTOCOLS,
    TASK_TYPE as USER_PROVISION_TASK_TYPE,
    apply_users_list_filters,
    is_in_plan_config,
    recompute_provision_state,
)
from app.services.user_subscription import user_subscription_expired

BULK_NODES_TASK_TYPE = "bulk_user_nodes"
BULK_NODES_SUBJECT = "bulk_nodes"

BulkNodesAction = Literal["add", "remove", "replace"]

# «Убрать»/«Перенести» без живого сервера удалить конфиги нельзя.
OFFLINE_MSG = (
    "Сервер недоступен — конфиги на нём не удалить. "
    "Если сервер списан, удалите его в «Серверах»"
)


@dataclass
class BulkNodesPreview:
    """Что изменится у пользователей — без сетевых вызовов."""

    action: str
    node_id: int
    to_node_id: int | None
    node_label: str
    to_node_label: str | None
    affected: list[dict[str, Any]] = field(default_factory=list)
    skipped: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    without_telegram: list[dict[str, Any]] = field(default_factory=list)
    notify_text_preview: str | None = None
    configs_to_create: int = 0
    configs_to_delete: int = 0


def assert_assignable_vpn_node(db: Session, node_id: int) -> Node:
    """Сервер для выдачи: standalone VPN или primary HA-группы.

    Прокси и реплики HA назначать пользователям нельзя (спека §10).
    """
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Сервер не найден"
        )
    if (node.node_kind or "vpn") != "vpn":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Прокси-сервер нельзя выдать пользователям",
        )
    group, role = find_sync_group_containing_node(db, node_id)
    if group is not None and role == "replica":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Реплику HA нельзя назначать — выберите primary",
        )
    return node


def resolve_bulk_scope(db: Session, scope: BulkNodesScope) -> list[User]:
    """Пользователи области: только с планом и без ожидающего удаления.

    ``all`` — все пользователи с планом, ``user_ids`` — выбранные в списке,
    ``filter`` — текущий фильтр списка (тот же DSL, что у ``GET /users``).
    """
    query = db.query(User).filter(
        User.role == UserRole.user,
        User.client_base_name.isnot(None),
        User.client_base_name != "",
        User.provision_state != "pending_deletion",
    )
    if scope.mode == "user_ids":
        ids = scope.user_ids or []
        if not ids:
            return []
        query = query.filter(User.id.in_(ids))
    elif scope.mode == "filter":
        query = apply_users_list_filters(query, state=scope.state, q=scope.q)
    return query.order_by(User.id.asc()).all()


def _node_label(node: Node) -> str:
    return (node.portal_label or node.name or str(node.id)).strip()


def _plan_names(user: User) -> list[str]:
    base = (getattr(user, "client_base_name", None) or "").strip()
    if not base:
        return []
    return [
        plan_name_for_index(base, index)
        for index in parse_plan_indexes(getattr(user, "plan_config_indexes", None))
    ]


def _desired_protocols(user: User) -> list[str]:
    raw = getattr(user, "desired_protocols", None) or ""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def _missing_plan_items(
    db: Session, user: User, node: Node
) -> list[tuple[str, VpnType]]:
    """Плановые конфиги пользователя (имя × протокол), которых ещё нет на узле.

    Протоколы отключённых модулей панели пропускаются — так же, как в
    Stage 1 (``compute_plan``), чтобы предпросмотр совпадал с планом.
    """
    names = _plan_names(user)
    protocols = _desired_protocols(user)
    if not names or not protocols:
        return []
    existing = {
        ((config.client_name or "").lower(), config.vpn_type.value)
        for config in db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.node_id == node.id)
        .all()
    }
    feature = get_feature_service()
    items: list[tuple[str, VpnType]] = []
    for protocol in protocols:
        if protocol in _FEATURE_PROTOCOLS and not feature.is_enabled(protocol):
            continue
        try:
            vpn_type = VpnType(protocol)
        except ValueError:
            continue
        for name in names:
            if (name.lower(), protocol) in existing:
                continue
            items.append((name, vpn_type))
    return items


def _in_plan_configs_on_node(db: Session, user: User, node: Node) -> int:
    """Сколько конфигов пользователя на узле входит в план (off-plan не считаются)."""
    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.node_id == node.id)
        .all()
    )
    return sum(1 for config in configs if is_in_plan_config(db, user, config))


def build_bulk_nodes_preview(
    db: Session,
    *,
    action: BulkNodesAction,
    node_id: int,
    to_node_id: int | None,
    scope: BulkNodesScope,
    notify_telegram: bool = False,
    note: str | None = None,
) -> BulkNodesPreview:
    """Предпросмотр массовой операции: что изменится и кто будет пропущен.

    Сетевых вызовов нет — только подсчёт по базе.
    """
    node = assert_assignable_vpn_node(db, node_id)
    to_node = None
    if action == "replace":
        if to_node_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите сервер, на который переносим",
            )
        to_node = assert_assignable_vpn_node(db, to_node_id)
        if to_node.id == node.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Новый сервер должен отличаться от старого",
            )
    if action in ("remove", "replace") and node.status != NodeStatus.online:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=OFFLINE_MSG
        )

    users = resolve_bulk_scope(db, scope)
    skipped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    affected: list[dict[str, Any]] = []
    without_telegram: list[dict[str, Any]] = []
    create_total = 0
    delete_total = 0

    for user in users:
        if background_task_service.find_active_task(
            USER_PROVISION_TASK_TYPE, subject_key=f"user:{user.id}"
        ):
            skipped["busy_provision"].append(
                {"user_id": user.id, "username": user.username}
            )
            continue

        assigned_ids = {
            row.node_id
            for row in db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
        }
        expired = user_subscription_expired(user)

        if action == "add":
            if node.id in assigned_ids:
                skipped["already_assigned"].append(
                    {"user_id": user.id, "username": user.username}
                )
                continue
            creates = 0 if expired else len(_missing_plan_items(db, user, node))
            deletes = 0
        elif action == "remove":
            if node.id not in assigned_ids:
                skipped["not_assigned"].append(
                    {"user_id": user.id, "username": user.username}
                )
                continue
            if len(assigned_ids) == 1:
                # Останется без серверов — такие идут в «Перенести» вручную.
                skipped["only_server"].append(
                    {"user_id": user.id, "username": user.username}
                )
                continue
            creates = 0
            deletes = _in_plan_configs_on_node(db, user, node)
        else:  # replace
            if node.id not in assigned_ids:
                skipped["not_assigned"].append(
                    {"user_id": user.id, "username": user.username}
                )
                continue
            creates = (
                0 if expired else len(_missing_plan_items(db, user, to_node))
            )
            deletes = _in_plan_configs_on_node(db, user, node)

        affected.append(
            {
                "user_id": user.id,
                "username": user.username,
                "configs_create": creates,
                "configs_delete": deletes,
                "expired": expired,
                # Истёкший доступ — не пропуск, а примечание: конфиги появятся
                # при продлении (D10, §7.3).
                "detail": "expired_no_create" if expired and creates == 0 else None,
            }
        )
        create_total += creates
        delete_total += deletes
        if not (user.telegram_id or "").strip():
            without_telegram.append({"user_id": user.id, "username": user.username})

    notify_text = None
    if notify_telegram:
        notify_text = render_bulk_notify_text(
            action,
            node_label=_node_label(node),
            to_node_label=_node_label(to_node) if to_node else None,
            note=note,
            other_servers_hint=True,
        )

    return BulkNodesPreview(
        action=action,
        node_id=node.id,
        to_node_id=to_node.id if to_node else None,
        node_label=_node_label(node),
        to_node_label=_node_label(to_node) if to_node else None,
        affected=affected,
        skipped=dict(skipped),
        without_telegram=without_telegram,
        notify_text_preview=notify_text,
        configs_to_create=create_total,
        configs_to_delete=delete_total,
    )


@dataclass
class BulkUserNodeResult:
    """Итог операции по одному пользователю."""

    user_id: int
    username: str
    status: Literal["ok", "noop", "failed", "skipped"]
    skip_reason: str | None = None
    created: int = 0
    deleted: int = 0
    error: str | None = None
    # replace: старый сервер убран только после успешного создания на новом.
    replaced: bool = False


def apply_bulk_user_node(
    db: Session,
    *,
    user: User,
    action: BulkNodesAction,
    node: Node,
    to_node: Node | None,
    actor: User,
) -> BulkUserNodeResult:
    """Применить операцию с сервером к одному пользователю.

    Работает только с явным узлом — активный узел панели не используется.
    """
    forget_confirmed_node()
    if action == "add":
        return _apply_add(db, user=user, node=node, actor=actor)
    if action == "remove":
        return _apply_remove(db, user=user, node=node, actor=actor)
    if action == "replace":
        if to_node is None:
            return BulkUserNodeResult(
                user_id=user.id,
                username=user.username,
                status="failed",
                error="Не указан сервер, на который переносим",
            )
        return _apply_replace(db, user=user, old=node, new=to_node, actor=actor)
    return BulkUserNodeResult(
        user_id=user.id,
        username=user.username,
        status="failed",
        error=f"Неизвестное действие: {action}",
    )


def _apply_add(
    db: Session, *, user: User, node: Node, actor: User
) -> BulkUserNodeResult:
    result = BulkUserNodeResult(user_id=user.id, username=user.username, status="ok")
    existing = (
        db.query(UserNodeAssignment)
        .filter_by(user_id=user.id, node_id=node.id)
        .first()
    )
    if existing is not None:
        result.status = "noop"
        return result

    db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    db.commit()

    if user_subscription_expired(user):
        # D10: доступ истёк — конфиги создадутся при продлении (§7.3).
        _refresh_provision_state(db, user)
        return result

    created, errors = _create_plan_configs(db, user=user, node=node, actor=actor)
    result.created = created
    if errors:
        result.status = "failed"
        result.error = "; ".join(errors)
    _refresh_provision_state(db, user)
    return result


def _apply_remove(
    db: Session, *, user: User, node: Node, actor: User, allow_last: bool = False
) -> BulkUserNodeResult:
    result = BulkUserNodeResult(user_id=user.id, username=user.username, status="ok")
    rows = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    assigned_ids = {row.node_id for row in rows}
    if node.id not in assigned_ids:
        result.status = "noop"
        return result
    if len(assigned_ids) == 1 and not allow_last:
        result.status = "skipped"
        result.skip_reason = "only_server"
        return result

    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.node_id == node.id)
        .all()
    )
    deleted = 0
    errors: list[str] = []
    for config in configs:
        if not is_in_plan_config(db, user, config):
            continue  # off-plan конфиги не трогаем
        try:
            deprovision_config(db, config=config, actor=actor, notify=False)
            deleted += 1
        except Exception as exc:
            errors.append(f"{config.client_name}: {exc}")

    if errors:
        # Присвоение оставляем: конфиг ещё жив, операцию можно повторить.
        result.status = "failed"
        result.error = "; ".join(errors)
        result.deleted = deleted
        _refresh_provision_state(db, user)
        return result

    db.query(UserNodeAssignment).filter_by(user_id=user.id, node_id=node.id).delete(
        synchronize_session=False
    )
    db.commit()
    result.deleted = deleted
    _refresh_provision_state(db, user)
    return result


def _apply_replace(
    db: Session, *, user: User, old: Node, new: Node, actor: User
) -> BulkUserNodeResult:
    """Перенос: сначала новый сервер, старый убираем только после успеха."""
    result = BulkUserNodeResult(user_id=user.id, username=user.username, status="ok")

    old_assigned = (
        db.query(UserNodeAssignment)
        .filter_by(user_id=user.id, node_id=old.id)
        .first()
    )
    if old_assigned is None:
        # Переносить нечего — пользователь и так не на старом сервере.
        result.status = "noop"
        return result

    already_assigned = (
        db.query(UserNodeAssignment)
        .filter_by(user_id=user.id, node_id=new.id)
        .first()
    )
    if already_assigned is None:
        db.add(UserNodeAssignment(user_id=user.id, node_id=new.id))
        db.commit()

    errors: list[str] = []
    created = 0
    if not user_subscription_expired(user):
        created, errors = _create_plan_configs(db, user=user, node=new, actor=actor)
    result.created = created

    if errors:
        # Неудача на новом сервере: старый оставляем, у пользователя оба сервера.
        user.provision_state = "partial"
        db.commit()
        result.status = "failed"
        result.error = "; ".join(errors)
        return result

    removal = _apply_remove(db, user=user, node=old, actor=actor, allow_last=True)
    result.deleted = removal.deleted
    if removal.status == "failed":
        result.status = "failed"
        result.error = removal.error
        return result

    result.replaced = True
    _refresh_provision_state(db, user)
    return result


def _create_plan_configs(
    db: Session, *, user: User, node: Node, actor: User
) -> tuple[int, list[str]]:
    """Создать плановые конфиги пользователя на узле. Возвращает (создано, ошибки)."""
    created = 0
    errors: list[str] = []
    for client_name, vpn_type in _missing_plan_items(db, user, node):
        try:
            provision_config(
                db,
                node=node,
                client_name=client_name,
                vpn_type=vpn_type,
                owner=user,
                actor=actor,
                notify=False,
            )
            created += 1
        except Exception as exc:
            errors.append(f"{client_name} ({vpn_type.value}): {exc}")
    return created, errors


def _refresh_provision_state(db: Session, user: User) -> None:
    user.provision_state = recompute_provision_state(db, user)
    db.commit()


def run_bulk_user_nodes_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Обработать пользователей массовой операции — строго по очереди.

    Пользователи идут последовательно (спека §10): сетевые вызовы идут на узел
    и не должны пересекаться. Прогресс: «{сервер}: {готово} / {всего} пользователей».
    """
    forget_confirmed_node()

    action = str(payload.get("action") or "add")
    user_ids = [int(item) for item in (payload.get("user_ids") or [])]
    actor_username = payload.get("actor_username")
    notify_telegram = bool(payload.get("notify_telegram"))
    note = payload.get("note")

    db = SessionLocal()
    try:
        node = db.get(Node, payload.get("node_id"))
        to_node = db.get(Node, payload.get("to_node_id")) if payload.get("to_node_id") else None
        if node is None:
            message = "Сервер не найден"
            return {
                "message": message,
                "output": json.dumps(
                    {"action": action, "error": message, "results": []}, ensure_ascii=False
                ),
            }
        label = _node_label(node)
        to_node_label = _node_label(to_node) if to_node else None
        node_id = node.id
        to_node_id = to_node.id if to_node else None
        users = (
            db.query(User).filter(User.id.in_(user_ids)).order_by(User.id).all()
            if user_ids
            else []
        )
        bot_token = ""
        portal_base = None
        if notify_telegram:
            from app.services.app_setting_store import _get_setting
            from app.services.client_portal import resolve_portal_base_url

            bot_token = _get_setting(db, "telegram_bot_token", "").strip()
            portal_base = resolve_portal_base_url(db)
    finally:
        db.close()

    total = len(users)
    results: list[dict[str, Any]] = []
    notify_stats = _empty_notify_stats()
    throttle = TelegramBulkThrottle()
    for index, user in enumerate(users, start=1):
        stage = f"{label}: {index - 1} / {total} пользователей"
        background_task_service.update_background_task(
            task_id,
            status="running",
            progress_percent=int((index - 1) * 100 / max(total, 1)),
            progress_stage=stage,
            message=stage,
        )
        # Сессия на пользователя: падение одного не должно ломать остальных.
        with SessionLocal() as session:
            fresh_user = session.get(User, user.id)
            if fresh_user is None:
                continue
            fresh_node = session.get(Node, node_id)
            fresh_to_node = session.get(Node, to_node_id) if to_node_id else None
            if fresh_node is None:
                results.append(
                    asdict(
                        BulkUserNodeResult(
                            user_id=fresh_user.id,
                            username=fresh_user.username,
                            status="failed",
                            error="Сервер не найден",
                        )
                    )
                )
                continue
            actor = None
            if actor_username:
                actor = session.query(User).filter(User.username == actor_username).first()
            if actor is None:
                actor = session.query(User).filter(User.role == UserRole.admin).first()
            try:
                result = apply_bulk_user_node(
                    db=session,
                    user=fresh_user,
                    action=action,
                    node=fresh_node,
                    to_node=fresh_to_node,
                    actor=actor or fresh_user,
                )
            except Exception as exc:
                # Ошибка одного пользователя не должна прерывать операцию.
                logger.exception("bulk_user_nodes: не удалось применить операцию")
                result = BulkUserNodeResult(
                    user_id=fresh_user.id,
                    username=fresh_user.username,
                    status="failed",
                    error=str(exc),
                )
            results.append(asdict(result))

            if notify_telegram:
                # Уведомляем только тех, у кого операция прошла успешно.
                status = "skipped_status"
                if result.status == "ok":
                    status = _notify_user(
                        session,
                        user=fresh_user,
                        result=result,
                        action=action,
                        label=label,
                        to_node_label=to_node_label,
                        note=note,
                        bot_token=bot_token,
                        portal_base=portal_base,
                        throttle=throttle,
                    )
                _count_notify_status(notify_stats, status)

    if not notify_telegram:
        notify_stats["disabled"] = total
    summary = _build_bulk_summary(
        action=action, label=label, results=results, notify=notify_stats
    )
    _notify_admin(actor_username=actor_username, summary=summary)
    return {
        "message": summary["title"],
        "action": action,
        "node_label": label,
        "ok_count": summary["ok_count"],
        "failed_count": summary["failed_count"],
        "skipped_count": summary["skipped_count"],
        "results": results,
        "output": json.dumps({**summary, "results": results}, ensure_ascii=False),
    }


def _empty_notify_stats() -> dict[str, int]:
    """Счётчики доставки уведомлений (отчёт по задаче)."""
    return {
        "sent": 0,
        "undelivered": 0,
        "no_telegram": 0,
        "disabled": 0,
        "error": 0,
        "skipped": 0,
    }


def _count_notify_status(stats: dict[str, int], status: str) -> None:
    if status in ("sent", "undelivered", "no_telegram", "error"):
        stats[status] += 1
        return
    # Нечего сообщать: операция не удалась или конфиги не создавались.
    stats["skipped"] += 1


def _user_portal_url(db: Session, user: User, portal_base: str) -> str | None:
    """Личная ссылка портала пользователя (только ему в Telegram)."""
    try:
        from app.services.client_portal import get_or_create_user_portal_token

        row = get_or_create_user_portal_token(db, user_id=user.id)
    except Exception:
        logger.warning("bulk_user_nodes: нет ссылки портала для user_id=%s", user.id)
        return None
    return f"{portal_base.rstrip('/')}/p/{row.token}"


def _remaining_node_labels(db: Session, user: User) -> list[str]:
    """Серверы пользователя после операции — «используйте конфиг для …»."""
    rows = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    labels: list[str] = []
    for row in rows:
        node = db.get(Node, row.node_id)
        if node is not None:
            labels.append(_node_label(node))
    return labels


def _notify_user(
    db: Session,
    *,
    user: User,
    result: BulkUserNodeResult,
    action: BulkNodesAction,
    label: str,
    to_node_label: str | None,
    note: str | None,
    bot_token: str,
    portal_base: str | None,
    throttle: TelegramBulkThrottle,
) -> str:
    """Уведомить пользователя о его части операции (Telegram или баннер портала).

    Сбой доставки не должен прерывать саму операцию — он попадает в отчёт.
    """
    try:
        portal_url = _user_portal_url(db, user, portal_base) if portal_base else None
        remaining = _remaining_node_labels(db, user) if action == "remove" else None
        return maybe_notify_after_user(
            enabled=True,
            user=user,
            result=result,
            action=action,
            node_label=label,
            to_node_label=to_node_label,
            note=note,
            remaining_labels=remaining,
            bot_token=bot_token,
            portal_url=portal_url,
            throttle=throttle,
            db=db,
        )
    except Exception:
        logger.exception("bulk_user_nodes: не удалось уведомить пользователя user_id=%s", user.id)
        return "error"


def _notify_admin(*, actor_username: str | None, summary: dict[str, Any]) -> None:
    """Одна сводка админу за задачу (колокольчик + Telegram)."""
    try:
        session = SessionLocal()
        try:
            details = (
                f"успешно {summary['ok_count']}, ошибок {summary['failed_count']}, "
                f"пропущено {summary['skipped_count']}"
            )
            admin_notify_service.send(
                session,
                "bulk_user_nodes",
                actor_username=actor_username,
                target_name=str(summary["title"]),
                details=details,
            )
        finally:
            session.close()
    except Exception:
        logger.exception("bulk_user_nodes: не удалось отправить сводку админу")


def _build_bulk_summary(
    *, action: str, label: str, results: list[dict[str, Any]], notify: dict[str, int] | None = None
) -> dict[str, Any]:
    """Сводка по задаче: сколько удалось, сколько с ошибкой, кого пропустили."""
    ok = [row for row in results if row.get("status") == "ok"]
    failed = [row for row in results if row.get("status") == "failed"]
    skipped = [row for row in results if row.get("status") == "skipped"]
    skipped_by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in skipped:
        skipped_by_reason[str(row.get("skip_reason") or "skipped")].append(row)
    verb = ACTION_TITLES.get(action, action)
    title = f"{verb} {label}: {len(ok)} пользователей, ошибок {len(failed)}"
    return {
        "action": action,
        "node_label": label,
        "title": title,
        "ok_count": len(ok),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "skipped": dict(skipped_by_reason),
        "notify": dict(notify or _empty_notify_stats()),
    }


def enqueue_bulk_user_nodes(
    db: Session, *, body: BulkNodesRequest, actor: User
) -> BackgroundTask:
    """Поставить массовую операцию с серверами в очередь.

    Одновременно может идти только одна задача ``bulk_user_nodes``
    (``subject_key="bulk_nodes"``) — иначе 409. Подтверждение именем сервера
    для «Убрать»/«Перенести» проверяет маршрут.
    """
    active = background_task_service.find_active_task(
        BULK_NODES_TASK_TYPE, subject_key=BULK_NODES_SUBJECT
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "bulk_nodes_running",
                "task_id": active.id,
                "message": "Уже выполняется массовая операция с серверами",
            },
        )

    # Пересчитываем предпросмотр: сервер мог уйти в офлайн, а состав
    # пользователей — измениться с момента подтверждения в диалоге.
    preview = build_bulk_nodes_preview(
        db,
        action=body.action,
        node_id=body.node_id,
        to_node_id=body.to_node_id,
        scope=body.scope,
        notify_telegram=body.notify_telegram,
        note=body.note,
    )
    user_ids = [int(row["user_id"]) for row in preview.affected]
    if not user_ids and not any(preview.skipped.values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет пользователей в выбранной области",
        )

    payload = {
        "action": body.action,
        "node_id": body.node_id,
        "to_node_id": body.to_node_id,
        "user_ids": user_ids,
        "notify_telegram": body.notify_telegram,
        "note": body.note,
        "actor_username": actor.username,
        "actor_id": actor.id,
    }
    message = (
        f"{ACTION_TITLES.get(body.action, body.action)} {preview.node_label}: "
        f"{len(user_ids)} пользователей…"
    )
    task_id = background_task_service.create_queued_task(
        BULK_NODES_TASK_TYPE,
        message,
        created_by_username=actor.username,
        subject_key=BULK_NODES_SUBJECT,
        input=json.dumps(payload, ensure_ascii=False),
    )

    def _callable(progress_updater: Any = None) -> dict[str, Any]:
        return run_bulk_user_nodes_task(task_id, payload)

    _submit_in_current_context(background_task_service.run_background_task, task_id, _callable)
    task = background_task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("Не удалось создать фоновую задачу")
    return task
