"""Desired-state user provisioning.

``compute_plan`` is pure: it diffs the user's desired state
(nodes × protocols × plan names) against the configs they own and never makes
network calls. The background ``user_provision`` task applies the plan,
calling ``provision_config``/``deprovision_config`` with an explicit node —
never the active node.
"""

from __future__ import annotations

import httpx
import json
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    BackgroundTask,
    ClientPortalToken,
    Node,
    NodeStatus,
    NodeSyncGroup,
    QrDownloadAuditLog,
    QrDownloadToken,
    RefreshToken,
    UnlockCode,
    UnlockCodeRedemption,
    User,
    UserActionLog,
    UserConfigAccess,
    UserNodeAssignment,
    UserPortalToken,
    UserReminderLog,
    UserRole,
    VpnConfig,
    VpnType,
    WebAuthnCredential,
)
from app.services.admin_notify import admin_notify_service
from app.services.background_tasks import _submit_in_current_context, background_task_service
from app.services.client_names import (
    assert_client_base_name_valid,
    names_under_base,
    parse_plan_indexes,
    plan_name_for_index,
)
from app.services.config_provisioning import deprovision_config, provision_config
from app.services.expected_node import forget_confirmed_node
from app.services.feature_guards import get_feature_service
from app.services.ssh_tunnel_pool import SshTunnelError

TASK_TYPE = "user_provision"
USER_DELETE_CLEANUP_TASK_TYPE = "user_delete_cleanup"

# Сетевые ошибки узла: после первой такой ошибки на узле остальные его элементы
# пропускаются (та же политика, что у портала).
_NODE_NETWORK_ERRORS = (HTTPException, httpx.HTTPError, OSError, SshTunnelError)

# Протоколы, наличие включения которых проверяется через флаги модулей панели.
_FEATURE_PROTOCOLS = ("openvpn", "wireguard", "amneziawg")

ACTION_CREATE = "create"
ACTION_DELETE = "delete"
ACTION_CONFLICT = "conflict"
ACTION_SKIPPED = "skipped"


@dataclass
class PlanItem:
    node_id: int
    node_label: str
    client_name: str
    vpn_type: str
    action: str  # create|delete|conflict|skipped
    reason: str | None = None
    config_id: int | None = None


@dataclass
class ProvisionPlan:
    create: list[PlanItem] = field(default_factory=list)
    delete: list[PlanItem] = field(default_factory=list)
    conflict: list[PlanItem] = field(default_factory=list)
    skipped: list[PlanItem] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None


def user_has_plan(user: User, *, provisioning_enabled: bool = True) -> bool:
    """План есть, пока модуль включён и у пользователя задано базовое имя конфигов.

    Точка включения (toggle `user_provisioning`) подключается на следующем этапе;
    пока что достаточно ``bool(user.client_base_name)``.
    """
    return bool(provisioning_enabled and getattr(user, "client_base_name", None))


def _desired_protocols(user: User) -> list[str]:
    raw = getattr(user, "desired_protocols", None) or ""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(p) for p in data]


def _plan_names(user: User) -> list[str]:
    base = (getattr(user, "client_base_name", None) or "").strip()
    if not base:
        return []
    return [plan_name_for_index(base, index) for index in parse_plan_indexes(user.plan_config_indexes)]


def _tail_index(base: str, name: str) -> int | None:
    """Индекс k для имени base-k; None, если имя не подходит под пространство базы."""
    prefix = base + "-"
    if not name or not name.startswith(prefix):
        return None
    try:
        k = int(name[len(prefix):])
    except ValueError:
        return None
    return k if 1 <= k <= 20 else None


def prefill_for_unmanaged(db: Session, user: User) -> dict[str, Any] | None:
    """Подсказка плана для пользователя без базового имени (не пишет в БД).

    База — самое частое владельческое имя конфига, которое проходит валидацию и
    свободно среди других пользователей. Индексы восстанавливаются из имён
    base / base-k, узлы и протоколы — из владельческих конфигов.
    """
    configs = db.query(VpnConfig).filter(VpnConfig.owner_id == user.id).all()
    if not configs:
        return None

    counter = Counter((c.client_name or "") for c in configs)
    base: str | None = None
    for name, _ in counter.most_common():
        try:
            assert_client_base_name_valid(name)
        except ValueError:
            continue
        taken = (
            db.query(User)
            .filter(func.lower(User.client_base_name) == name.lower(), User.id != user.id)
            .first()
        )
        if taken is not None:
            continue
        base = name
        break
    if base is None:
        return None

    indexes: set[int] = set()
    for c in configs:
        name = c.client_name or ""
        if name == base:
            indexes.add(1)
        else:
            k = _tail_index(base, name)
            if k is not None:
                indexes.add(k)

    return {
        "client_base_name": base,
        "plan_config_indexes": sorted(indexes) if indexes else [1],
        "node_ids": sorted({c.node_id for c in configs}),
        "protocols": sorted({c.vpn_type.value for c in configs}),
    }


def validate_plan_nodes(db: Session, node_ids: list[int]) -> list[Node]:
    """Узлы для плана: существуют, не прокси и не реплики HA (только standalone/primary)."""
    if not node_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Укажите хотя бы один узел")
    unique = list(dict.fromkeys(node_ids))
    nodes = db.query(Node).filter(Node.id.in_(unique)).all()
    if len(nodes) != len(unique):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Один из узлов не найден")
    replicas: set[int] = set()
    for group in db.query(NodeSyncGroup).all():
        try:
            replicas.update(int(item) for item in json.loads(group.replica_node_ids or "[]"))
        except (TypeError, ValueError):
            continue
    for node in nodes:
        if node.node_kind == "proxy":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Узел «{node.name}» — прокси, его нельзя назначать в план абонента",
            )
        if node.id in replicas:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Узел «{node.name}» — реплика HA, назначьте первичный узел группы",
            )
    return nodes


def compute_plan(db: Session, user: User) -> ProvisionPlan:
    """Чистый diff желаемого и фактического состояния. Без сетевых вызовов."""
    plan = ProvisionPlan()
    if not user_has_plan(user):
        return plan

    until = getattr(user, "access_until", None)
    if until is not None:
        now = datetime.now(timezone.utc)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if until < now:
            plan.blocked = True
            plan.block_reason = "access_expired"
            return plan

    names = _plan_names(user)
    protocols = _desired_protocols(user)
    if not names or not protocols:
        return plan

    plan_names_lc = {name.lower() for name in names}
    under_base_lc = names_under_base(getattr(user, "client_base_name", None) or "")

    assignment_rows = (
        db.query(UserNodeAssignment).filter(UserNodeAssignment.user_id == user.id).all()
    )
    node_ids = [row.node_id for row in assignment_rows]
    nodes = {
        node.id: node
        for node in (db.query(Node).filter(Node.id.in_(node_ids)).all() if node_ids else [])
    }

    def node_label(node_id: int) -> str:
        node = nodes.get(node_id)
        return node.name if node else str(node_id)

    # Ключи желаемого состояния: (node_id, protocol, lower(name)).
    desired_keys = {
        (node_id, protocol, name.lower())
        for node_id in node_ids
        for protocol in protocols
        for name in names
    }

    # Owned configs on assigned nodes. Names outside this user's base namespace are
    # off-plan and ignored. Names under the base but not in desired indexes/protocols
    # are deletions (e.g. indexes [1,2,3]→[1,3] removes base-2).
    actual = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.node_id.in_(node_ids))
        .all()
    ) if node_ids else []

    key_to_config: dict[tuple[int, str, str], int] = {}
    for config in actual:
        name_lc = (config.client_name or "").lower()
        if name_lc not in under_base_lc:
            continue
        key = (config.node_id, config.vpn_type.value, name_lc)
        if key not in desired_keys:
            plan.delete.append(
                PlanItem(
                    node_id=config.node_id,
                    node_label=node_label(config.node_id),
                    client_name=config.client_name,
                    vpn_type=config.vpn_type.value,
                    action=ACTION_DELETE,
                    config_id=config.id,
                )
            )
        else:
            key_to_config.setdefault(key, config.id)

    # Конфликты: желаемое имя на узле/протоколе принадлежит другому владельцу.
    conflict_keys: set[tuple[int, str, str]] = set()
    if node_ids:
        others = (
            db.query(VpnConfig)
            .filter(VpnConfig.node_id.in_(node_ids), VpnConfig.owner_id != user.id)
            .all()
        )
        for config in others:
            if (config.client_name or "").lower() not in plan_names_lc:
                continue
            key = (config.node_id, config.vpn_type.value, (config.client_name or "").lower())
            if key in desired_keys and key not in conflict_keys:
                conflict_keys.add(key)
                plan.conflict.append(
                    PlanItem(
                        node_id=config.node_id,
                        node_label=node_label(config.node_id),
                        client_name=config.client_name,
                        vpn_type=config.vpn_type.value,
                        action=ACTION_CONFLICT,
                        reason=(
                            f"Имя «{config.client_name}» занято на этом узле и протоколе "
                            f"другим владельцем"
                        ),
                        config_id=config.id,
                    )
                )

    feature = get_feature_service()
    for node_id, protocol, name_lower in sorted(desired_keys):
        if (node_id, protocol, name_lower) in key_to_config:
            continue  # уже есть у пользователя
        if (node_id, protocol, name_lower) in conflict_keys:
            continue  # уже сообщено как конфликт

        node = nodes.get(node_id)
        skip_reason: str | None = None
        if node is None:
            skip_reason = "node_not_found"
        elif node.status != NodeStatus.online:
            skip_reason = "node_offline"
        elif protocol in _FEATURE_PROTOCOLS and not feature.is_enabled(protocol):
            skip_reason = "protocol_disabled"

        item = PlanItem(
            node_id=node_id,
            node_label=node_label(node_id),
            client_name=next(name for name in names if name.lower() == name_lower),
            vpn_type=protocol,
            action=ACTION_CREATE,
        )
        if skip_reason is not None:
            item.action = ACTION_SKIPPED
            item.reason = skip_reason
            plan.skipped.append(item)
        else:
            plan.create.append(item)

    return plan


def is_in_plan_config(db: Session, user: User, config: VpnConfig) -> bool:
    """True, если конфиг входит в актуальный план пользователя (имя × узел × протокол)."""
    if not user_has_plan(user):
        return False
    if config.owner_id != user.id:
        return False
    if (config.client_name or "").lower() not in {name.lower() for name in _plan_names(user)}:
        return False
    if config.vpn_type.value not in _desired_protocols(user):
        return False
    return (
        db.query(UserNodeAssignment)
        .filter_by(user_id=user.id, node_id=config.node_id)
        .first()
        is not None
    )


def purge_user_before_delete(db: Session, user: User, successor: User) -> None:
    """Переносит владение оставшимися (off-plan) конфигами на successeur и
    обнуляет ссылки на удаляемого пользователя в смежных таблицах."""
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(synchronize_session=False)
    db.query(UserConfigAccess).filter(UserConfigAccess.user_id == user.id).delete(synchronize_session=False)
    db.query(UserReminderLog).filter(UserReminderLog.user_id == user.id).delete(synchronize_session=False)
    db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id).delete(synchronize_session=False)
    # Обнулённый user_id сделал бы погашение клиентским и мог бы нарушить уникальность (код, клиент, узел).
    db.query(UnlockCodeRedemption).filter(UnlockCodeRedemption.user_id == user.id).delete(synchronize_session=False)
    for model in (ClientPortalToken, UnlockCode, UserPortalToken):
        db.query(model).filter(model.created_by_user_id == user.id).update(
            {model.created_by_user_id: None},
            synchronize_session=False,
        )
    db.query(VpnConfig).filter(VpnConfig.owner_id == user.id).update(
        {VpnConfig.owner_id: successor.id},
        synchronize_session=False,
    )
    db.query(QrDownloadToken).filter(QrDownloadToken.created_by_user_id == user.id).update(
        {QrDownloadToken.created_by_user_id: None},
        synchronize_session=False,
    )
    db.query(QrDownloadAuditLog).filter(QrDownloadAuditLog.actor_user_id == user.id).update(
        {QrDownloadAuditLog.actor_user_id: None},
        synchronize_session=False,
    )
    db.query(UserActionLog).filter(UserActionLog.user_id == user.id).update(
        {UserActionLog.user_id: None},
        synchronize_session=False,
    )


def recompute_provision_state(db: Session, user: User) -> str:
    """ok | partial | pending | unmanaged (+ blocked, если план не применим)."""
    if not user_has_plan(user):
        return "unmanaged"
    plan = compute_plan(db, user)
    if plan.blocked:
        return "blocked"
    if plan.create or plan.delete or plan.conflict:
        return "pending"
    if plan.skipped:
        return "partial"
    return "ok"


def enqueue_user_provision(
    db: Session,
    *,
    user_id: int,
    actor_username: str,
    confirm_deletions: bool,
) -> BackgroundTask:
    """Поставить задачу применения плана в очередь.

    Raises HTTP 409 ``access_expired`` когда план заблокирован истёкшим доступом,
    HTTP 409 ``confirm_deletions`` когда в плане есть удаления, но флага нет.
    Возвращает уже активную задачу пользователя, если она есть.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    plan = compute_plan(db, user)
    if plan.blocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "access_expired", "message": plan.block_reason},
        )
    if plan.delete and not confirm_deletions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "confirm_deletions"},
        )

    subject_key = f"user:{user_id}"
    existing = background_task_service.find_active_task(TASK_TYPE, subject_key=subject_key)
    if existing is not None:
        return existing

    message = f"Применение плана конфигов для {user.username or user_id}…"
    task_id = background_task_service.create_queued_task(
        TASK_TYPE,
        message,
        created_by_username=actor_username,
        subject_key=subject_key,
    )

    def _callable(progress_updater: Callable[..., Any] | None = None) -> dict[str, Any]:
        return run_user_provision_task(task_id, user_id)

    # Same path as enqueue_background_task after create_queued_task (keeps subject_key + known id).
    _submit_in_current_context(background_task_service.run_background_task, task_id, _callable)
    task = background_task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("Не удалось создать фоновую задачу")
    return task


def _load_actor(session: Session, actor_username: str | None, fallback: User) -> User:
    if actor_username:
        actor = session.query(User).filter(User.username == actor_username).first()
        if actor is not None:
            return actor
    return fallback


def _apply_create(
    session: Session,
    node: Node,
    item: PlanItem,
    owner: User,
    actor: User,
) -> dict[str, Any]:
    result = {
        "node_id": item.node_id,
        "node_label": node.name if node else str(item.node_id),
        "client_name": item.client_name,
        "vpn_type": item.vpn_type,
        "action": ACTION_CREATE,
        "status": "done",
        "error": None,
    }
    try:
        outcome = provision_config(
            session,
            node=node,
            client_name=item.client_name,
            vpn_type=VpnType(item.vpn_type),
            owner=owner,
            actor=actor,
            notify=False,
        )
        if isinstance(outcome, tuple) and outcome:
            result["config_id"] = outcome[0].id
    except _NODE_NETWORK_ERRORS as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    except Exception as exc:  # несетевая ошибка элемента — не гасим весь узел
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def _apply_delete(
    session: Session,
    node_label: str,
    item: PlanItem,
    actor: User,
) -> dict[str, Any]:
    result = {
        "node_id": item.node_id,
        "node_label": node_label,
        "client_name": item.client_name,
        "vpn_type": item.vpn_type,
        "action": ACTION_DELETE,
        "status": "done",
        "error": None,
    }
    try:
        config = session.get(VpnConfig, item.config_id)
        if config is not None:
            deprovision_config(session, config=config, actor=actor, notify=False)
    except _NODE_NETWORK_ERRORS as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def _apply_node(
    node_id: int,
    items: list[PlanItem],
    session: Session,
    owner: User,
    actor: User,
) -> list[dict[str, Any]]:
    """Элементы одного узла последовательно; после первой сетевой ошибки — skip остальных."""
    node = session.get(Node, node_id)
    node_label = node.name if node else str(node_id)
    results: list[dict[str, Any]] = []
    skip_rest = False
    for item in items:
        if skip_rest:
            results.append(
                {
                    "node_id": item.node_id,
                    "node_label": node_label,
                    "client_name": item.client_name,
                    "vpn_type": item.vpn_type,
                    "action": item.action,
                    "status": ACTION_SKIPPED,
                    "error": "Пропущено после сетевой ошибки на узле",
                }
            )
            continue
        if item.action == ACTION_CREATE:
            results.append(_apply_create(session, node, item, owner, actor))
        else:
            results.append(_apply_delete(session, node_label, item, actor))
        if results[-1]["status"] == "error":
            skip_rest = True
    return results


def run_user_provision_task(task_id: str, user_id: int) -> dict[str, Any]:
    """Применить план пользователя в фоне. Результат — summary по элементам."""
    forget_confirmed_node()

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"success": False, "error": "пользователь не найден", "items": []}
        task = db.get(BackgroundTask, task_id)
        actor_username = task.created_by_username if task else None
        plan = compute_plan(db, user)
        if plan.blocked:
            return {
                "success": False,
                "blocked": True,
                "block_reason": plan.block_reason,
                "items": [],
            }

        apply_items = sorted(
            (*plan.create, *plan.delete),
            key=lambda item: (item.action, item.client_name, item.node_id),
        )
        node_ids = sorted({item.node_id for item in apply_items})
        nodes = {
            node.id: node
            for node in (db.query(Node).filter(Node.id.in_(node_ids)).all() if node_ids else [])
        }
    finally:
        db.close()

    results: list[dict[str, Any]] = []
    total_items = len(apply_items)
    done = 0
    results_lock = threading.Lock()
    progress_lock = threading.Lock()
    # Detached ORM instances from the closed session must not be used across threads.
    owner_id = user_id
    node_name_by_id = {nid: (nodes[nid].name if nid in nodes else str(nid)) for nid in node_ids}

    def _progress(node_label: str, client_name: str, vpn_type: str) -> None:
        # Вызывается без удержания results_lock: update_background_task открывает
        # своё БД-соединение; с одним соединением StaticPool иначе возможен
        # deadlock между потоками разных узлов.
        nonlocal done
        with progress_lock:
            done += 1
            percent = int(done / total_items * 100) if total_items else 100
        background_task_service.update_background_task(
            task_id,
            status="running",
            progress_percent=percent,
            progress_stage=f"{node_label}: {client_name} / {vpn_type} ({done}/{total_items})",
        )

    def _run_node(node_id: int) -> None:
        session = SessionLocal()
        try:
            owner = session.get(User, owner_id)
            if owner is None:
                return
            actor = _load_actor(session, actor_username, owner)
            node_results = _apply_node(
                node_id,
                [item for item in apply_items if item.node_id == node_id],
                session,
                owner,
                actor,
            )
        finally:
            session.close()
        node_label = node_name_by_id.get(node_id, str(node_id))
        with results_lock:
            results.extend(node_results)
        # Прогресс вне блокировки результатов, чтобы не держать БД-соединение
        # под мьютексом между потоками узлов.
        for item in [i for i in apply_items if i.node_id == node_id]:
            _progress(node_label, item.client_name, item.vpn_type)

    max_workers = max(1, int(get_settings().bulk_config_op_max_workers))
    if node_ids:
        # Sequential when max_workers==1 (tests / small installs): avoids StaticPool
        # deadlocks when the caller still holds a Session on the same engine.
        if max_workers == 1 or len(node_ids) == 1:
            for node_id in node_ids:
                _run_node(node_id)
        else:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="user-provision") as pool:
                list(pool.map(_run_node, node_ids))

    created = sum(1 for r in results if r["action"] == ACTION_CREATE and r["status"] == "done")
    deleted = sum(1 for r in results if r["action"] == ACTION_DELETE and r["status"] == "done")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == ACTION_SKIPPED)

    session = SessionLocal()
    try:
        user_row = session.get(User, user_id)
        if user_row is not None:
            user_row.provision_state = recompute_provision_state(session, user_row)
            session.commit()
    finally:
        session.close()

    session = SessionLocal()
    try:
        user_row = session.get(User, user_id)
        details = (
            f"{user_row.username if user_row else user_id}: "
            f"создано {created}, удалено {deleted}, ошибок {errors}"
        )
        if skipped:
            details += f", пропущено {skipped}"
        admin_notify_service.send(
            session,
            "user_provision_applied",
            actor_username=actor_username,
            target_name=user_row.username if user_row else str(user_id),
            details=details,
        )
    finally:
        session.close()

    background_task_service.update_background_task(
        task_id,
        status="completed",
        progress_percent=100,
        progress_stage="Готово",
        message=f"Готово: создано {created}, удалено {deleted}, ошибок {errors}",
        output=json.dumps({"success": True, "items": results}, ensure_ascii=False),
    )
    return {"success": True, "items": results}


def _resolve_delete_actor(session: Session, actor_username: str | None, fallback: User) -> User:
    actor = _load_actor(session, actor_username, fallback)
    if actor.role == UserRole.admin:
        return actor
    admin = (
        session.query(User)
        .filter(User.role == UserRole.admin, User.is_active.is_(True))
        .first()
    )
    return admin or fallback


def enqueue_user_delete_cleanup(db: Session, *, user_id: int, actor_username: str) -> BackgroundTask:
    """Поставить фоновую задачу очистки при удалении пользователя с планом.

    Возвращает уже активную задачу пользователя, если она есть (повторный
    DELETE не создаёт дублей).
    """
    subject_key = f"user:{user_id}"
    existing = background_task_service.find_active_task(
        USER_DELETE_CLEANUP_TASK_TYPE, subject_key=subject_key
    )
    if existing is not None:
        return existing

    task_id = background_task_service.create_queued_task(
        USER_DELETE_CLEANUP_TASK_TYPE,
        f"Удаление пользователя {user_id}…",
        created_by_username=actor_username,
        subject_key=subject_key,
    )

    def _callable(progress_updater: Callable[..., Any] | None = None) -> dict[str, Any]:
        return run_user_delete_cleanup(task_id, user_id, actor_username)

    _submit_in_current_context(background_task_service.run_background_task, task_id, _callable)
    task = background_task_service.get_task(task_id)
    if task is None:
        raise RuntimeError("Не удалось создать фоновую задачу удаления пользователя")
    return task


def run_user_delete_cleanup(task_id: str, user_id: int, actor_username: str | None = None) -> dict[str, Any]:
    """Очистка пользователя с планом: deprovision in-plan конфигов, реassign
    off-plan конфигов администратору, удаление присваиваний и строки User.

    Любая ошибка deprovision оставляет пользователя в ``pending_deletion`` —
    удаление можно повторить.
    """
    from app.services.active_web_session import active_web_session_service
    from app.services.client_portal import revoke_creator_portal_links
    from app.services.refresh_token import invalidate_user_sessions

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"success": True, "errors": []}

        actor = _resolve_delete_actor(db, actor_username, user)

        # Доступ в панель/портал и сессии отключаем сразу.
        user.panel_login_enabled = False
        user.is_active = False
        user.token_version = (user.token_version or 0) + 1
        revoke_creator_portal_links(db, user.id, keep_accessible=False)
        invalidate_user_sessions(db, user, reason="deleted", commit=False)
        active_web_session_service.revoke_user_sessions(db, user.username, commit=False)

        configs = db.query(VpnConfig).filter(VpnConfig.owner_id == user.id).all()
        in_plan: list[VpnConfig] = []
        off_plan: list[VpnConfig] = []
        for config in configs:
            (in_plan if is_in_plan_config(db, user, config) else off_plan).append(config)

        errors: list[str] = []
        for config in in_plan:
            try:
                deprovision_config(db, config=config, actor=actor, notify=False)
            except Exception as exc:  # не гасим всё удаление из-за одного конфига
                errors.append(f"{config.client_name} (node {config.node_id}): {exc}")

        if errors:
            db.rollback()
            background_task_service.update_background_task(
                task_id,
                status="completed",
                progress_percent=100,
                progress_stage="Ошибка очистки",
                message="Очистка завершена с ошибками",
                output=json.dumps({"success": False, "errors": errors}, ensure_ascii=False),
            )
            return {"success": False, "errors": errors}

        purge_user_before_delete(db, user, actor)  # остальные (off-plan) конфиги → администратор
        db.query(UserNodeAssignment).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()

        output = {
            "success": True,
            "deprovisioned": len(in_plan),
            "reassigned": len(off_plan),
        }
        background_task_service.update_background_task(
            task_id,
            status="completed",
            progress_percent=100,
            progress_stage="Готово",
            message="Пользователь удалён",
            output=json.dumps(output, ensure_ascii=False),
        )
        return {"success": True, **output}
    finally:
        db.close()
