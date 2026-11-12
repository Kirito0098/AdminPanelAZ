import asyncio
import json
import logging
import math
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_password_hash, require_admin, tg_mini_token_allowed
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import (
    BackgroundTask,
    Node,
    TrafficSessionState,
    User,
    UserAccessRequest,
    UserActionLog,
    UserNodeAssignment,
    UserRole,
    VpnConfig,
    VpnType,
    UserTrafficSample,
    UserTrafficStatProtocol,
)
from app.schemas import (
    CooldownReleaseRequest,
    CooldownSettingsResponse,
    CooldownSettingsUpdate,
    AccessRequestResponse,
    ApproveRequest,
    BulkNodesPreviewItem,
    BulkNodesPreviewResponse,
    BulkNodesRequest,
    BulkNotifyRequest,
    BulkUsersFailure,
    BulkUsersRequest,
    BulkUsersResult,
    ConfigAccessOpRequest,
    GraceHoldView,
    MessageResponse,
    PresetCreate,
    PresetResponse,
    PresetUpdate,
    ProvisionPlanItem,
    ProvisionPlanResponse,
    ProvisioningConfig,
    RejectRequest,
    TelegramLinkCodeResponse,
    UserConfigAccessResponse,
    UserConfigAccessUpdate,
    UserCreate,
    UserProvisionSummary,
    UserFromExistingCreate,
    UserFromExistingResponse,
    UserProvisionedCreate,
    UserProvisionedResponse,
    UserProvisioningApply,
    UserProvisioningCard,
    UserProvisioningDesired,
    UserProvisioningSuggested,
    UserProvisioningUpdate,
    UserResumeRequest,
    UserExtendRequest,
    UserHistoryEntry,
    UserResponse,
    UserStatsResponse,
    UserSuspendRequest,
    UserTrafficStatRow,
    UserTrafficTotals,
    UserUpdate,
)
from app.services.action_log import log_action
from app.services.access_policy import AccessPolicyService
from app.services.admin_notify import admin_notify_service
from app.services.app_setting_store import _get_setting
from app.services.active_web_session import active_web_session_service
from app.services.background_tasks import background_task_service
from app.services.bulk_user_notify import BULK_NOTIFY_TASK_TYPE, start_bulk_user_notify
from app.services.bulk_user_nodes import (
    BulkNodesPreview,
    assert_assignable_vpn_node,
    build_bulk_nodes_preview,
    enqueue_bulk_user_nodes,
)
from app.services.client_names import (
    assert_client_base_name_valid,
    assert_name_not_reserved_by_other_user,
    names_under_base,
    parse_plan_indexes,
)
from app.services.client_portal import revoke_creator_portal_links
from app.services.config_access import get_user_config_grants, set_user_config_access
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.user_access_requests import (
    cooldown_hours,
    list_cooldown_blocked,
    release_cooldown,
    set_cooldown_hours,
    AlreadyDecided,
    TelegramAlreadyBound,
    approve_request,
    backfill_missing_request_profiles,
    delete_user_write_archive,
    reject_request,
    sync_admin_request_messages,
)
from app.services import telegram_api
from app.services.telegram import send_tg_message
from app.services.request_receipt_preview import ReceiptDecodeError, get_cached_or_build_preview
from app.services.ip_restriction import ip_restriction_service
from app.services.notify_time import get_client_timezone_from_request
from app.services.node_manager import get_adapter_for_node, node_metadata_dict
from app.services.node_sync.groups import require_ha_primary_for_client_ops
from app.services.config_provisioning import deprovision_config
from app.services.traffic.ha_aggregate import resolve_traffic_scope
from app.services.user_blocks import apply_user_block, lift_user_block
from app.services.user_config_summary import owned_configs_summaries, summarize_owned_configs
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.file_download import attachment_response
from app.services.provisioning_presets import create_preset, delete_preset, list_presets, update_preset
from app.services.qr_generator import generate_qr_png, prefers_download_link_qr
from app.services.telegram_link import create_link_code
from app.services.user_identity_conflict import pending_deletion_conflict as _pending_deletion_conflict
from app.services.user_provisioning import (
    TASK_TYPE,
    apply_users_list_filters,
    compute_plan,
    enqueue_user_delete_cleanup,
    enqueue_user_provision,
    is_in_plan_config,
    prefill_for_unmanaged,
    purge_user_before_delete,
    recompute_provision_state,
    user_has_plan,
    validate_plan_nodes,
)
from app.routers.configs import _qr_download_service, _require_profile_path_allowed
from app.services.admin_bootstrap import (
    scrub_admin_bootstrap_secret_from_env,
    should_scrub_env_after_password_change,
)
from app.services.password_policy import validate_password
from app.services.refresh_token import invalidate_user_sessions
from app.services.self_service import password_change_required_on_admin_set
from app.services.telegram_link import notify_telegram_unlinked, release_telegram_of_pending_deletion
from app.services.user_access_extend import compute_extended_access_until
from app.services.unlock_codes import revoke_user_bound_unlock_codes
from app.services.user_subscription import (
    get_user_access_until,
    normalize_access_until,
    set_user_access_until,
)
from app.services.vpn_profile_visibility import (
    normalize_policy,
    parse_user_visible_vpn_profiles,
    policy_to_json,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


def _desired_protocols_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(p) for p in data] if isinstance(data, list) else []


def _validate_protocols(protocols: list[str]) -> list[str]:
    if not protocols:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Укажите хотя бы один протокол")
    allowed = {vt.value for vt in VpnType}
    for proto in protocols:
        if proto not in allowed:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Протокол «{proto}» не поддерживается")
    return list(protocols)


def _validate_indexes(indexes: list[int]) -> list[int]:
    if not indexes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "plan_config_indexes: укажите индексы от 1 до 20"
        )
    try:
        indexes = [int(item) for item in indexes]
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "plan_config_indexes: целые числа от 1 до 20"
        )
    if (
        not indexes
        or len(set(indexes)) != len(indexes)
        or any(item < 1 or item > 20 for item in indexes)
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "plan_config_indexes: уникальные целые от 1 до 20"
        )
    return indexes


def _serialize_plan(plan) -> ProvisionPlanResponse:
    def item(it) -> ProvisionPlanItem:
        return ProvisionPlanItem(
            node_id=it.node_id,
            node_label=it.node_label,
            client_name=it.client_name,
            vpn_type=it.vpn_type,
            action=it.action,
            reason=it.reason,
            config_id=it.config_id,
        )

    return ProvisionPlanResponse(
        create=[item(it) for it in plan.create],
        delete=[item(it) for it in plan.delete],
        conflict=[item(it) for it in plan.conflict],
        skipped=[item(it) for it in plan.skipped],
        blocked=plan.blocked,
        block_reason=plan.block_reason,
    )


def _user_summary(
    user: User,
    node_ids: list[int],
    *,
    traffic_consumed_bytes: int = 0,
    online: bool = False,
    owned_base_name: str | None = None,
) -> UserProvisionSummary:
    return UserProvisionSummary(
        id=user.id,
        username=user.username,
        role=user.role.value,
        client_base_name=user.client_base_name,
        owned_config_base_name=owned_base_name,
        plan_config_indexes=parse_plan_indexes(user.plan_config_indexes),
        desired_protocols=_desired_protocols_list(user.desired_protocols),
        panel_login_enabled=user.panel_login_enabled,
        provision_state=user.provision_state,
        access_until=user.access_until,
        node_ids=list(node_ids),
        config_quota=user.config_quota,
        can_create_configs=bool(user.can_create_configs),
        can_manage_configs=bool(user.can_manage_configs),
        suspended_at=user.suspended_at,
        suspend_reason=user.suspend_reason,
        suspend_reason_visible=bool(user.suspend_reason_visible),
        traffic_limit_bytes=user.traffic_limit_bytes,
        traffic_counter_reset_at=user.traffic_counter_reset_at,
        traffic_limit_blocked=bool(user.traffic_limit_blocked),
        traffic_consumed_bytes=int(traffic_consumed_bytes),
        online=bool(online),
        telegram_id=(user.telegram_id or "").strip() or None,
        visible_vpn_profiles=parse_user_visible_vpn_profiles(user.visible_vpn_profiles),
    )


def _bulk_nodes_preview_response(preview: BulkNodesPreview) -> BulkNodesPreviewResponse:
    """Предпросмотр → ответ API (одна и та же форма для affected/skipped/без Telegram)."""

    def item(data: dict[str, Any]) -> BulkNodesPreviewItem:
        return BulkNodesPreviewItem(
            user_id=int(data.get("user_id") or 0),
            username=str(data.get("username") or ""),
            configs_create=int(data.get("configs_create") or 0),
            configs_delete=int(data.get("configs_delete") or 0),
            expired=bool(data.get("expired")),
            detail=data.get("detail"),
        )

    return BulkNodesPreviewResponse(
        action=preview.action,
        node_id=preview.node_id,
        to_node_id=preview.to_node_id,
        node_label=preview.node_label,
        to_node_label=preview.to_node_label,
        affected=[item(row) for row in preview.affected],
        skipped={
            reason: [item(row) for row in rows] for reason, rows in preview.skipped.items()
        },
        without_telegram=[item(row) for row in preview.without_telegram],
        notify_text_preview=preview.notify_text_preview,
        configs_to_create=preview.configs_to_create,
        configs_to_delete=preview.configs_to_delete,
    )


def _get_owned_config(db: Session, user_id: int, config_id: int) -> VpnConfig:
    """Конфиг пользователя; несоответствие владельца → 404 «не найдено»
    (без утечки чужих id)."""
    config = db.get(VpnConfig, config_id)
    if config is None or config.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    return config


def _resolve_op_config_and_node(db: Session, config: VpnConfig) -> tuple[VpnConfig, Node]:
    """D2-операции ведутся на узле конфига (не активном). Теневая (HA-реплика)
    конфигурация — через первичный конфиг/первичный узел."""
    node = db.get(Node, config.node_id)
    if config.ha_primary_config_id is not None:
        primary = db.get(VpnConfig, config.ha_primary_config_id)
        if primary is not None:
            config = primary
            node = db.get(Node, config.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    return config, node


def _antizapret_path_for_node(db: Session, node: Node) -> Path:
    meta = node_metadata_dict(node)
    raw = meta.get("antizapret_path")
    if raw:
        return Path(str(raw))
    return settings.antizapret_path


def _set_user_traffic_limit(
    db: Session, user: User, value: int | None, *, actor: str
) -> None:
    """Задать/снять лимит трафика пользователя.

    ``None`` — снять лимит и поднять sticky-блок ``user_traffic_limit``.
    Первое назначение лимита стартует новое окно отсчёта (``traffic_counter_reset_at``).
    """
    if value is None:
        user.traffic_limit_bytes = None
        user.traffic_limit_blocked = False
        db.add(user)
        db.flush()
        # Снятие блока не трогает остальные причины (user_suspended и др.).
        lift_user_block(db, user, "user_traffic_limit", actor=actor)
        return
    if user.traffic_limit_bytes is None:
        user.traffic_counter_reset_at = datetime.now(timezone.utc).replace(tzinfo=None)
    user.traffic_limit_bytes = int(value)
    db.add(user)
    db.commit()


@router.get("", response_model=list[UserResponse])
@tg_mini_token_allowed
def list_users(
    role: str | None = None,
    q: str | None = None,
    state: str | None = None,
    include_deleting: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    # Абоненты в pending_deletion не попадают в обычный список: их видно только
    # отдельным фильтром «Удаляется» (state=pending_deletion) или явным флагом.
    wants_deleting = include_deleting or (state or "").strip().lower() == "pending_deletion"
    query = db.query(User)
    if not wants_deleting:
        query = query.filter(User.provision_state != "pending_deletion")
    query = apply_users_list_filters(query, role=role, q=q, state=state)
    users = query.order_by(User.id).all()

    assignment_rows: list[UserNodeAssignment] = []
    if users:
        assignment_rows = (
            db.query(UserNodeAssignment)
            .filter(UserNodeAssignment.user_id.in_([user.id for user in users]))
            .all()
        )
    nodes_by_user: dict[int, list[int]] = defaultdict(list)
    for row in assignment_rows:
        nodes_by_user[row.user_id].append(row.node_id)

    active_tasks = (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.task_type == TASK_TYPE,
            BackgroundTask.status.in_(["queued", "running"]),
        )
        .all()
    )
    active_task_by_user: dict[int, str] = {}
    for task in active_tasks:
        if task.subject_key and task.subject_key.startswith("user:"):
            try:
                active_task_by_user[int(task.subject_key[len("user:") :])] = task.id
            except ValueError:
                continue

    # Абоненты без плана (созданные «из существующих») показывают фактические
    # конфиги владельца: иначе узлы, протоколы и имена в карточке списка пустые.
    summaries = owned_configs_summaries(
        db, [user.id for user in users if not user.client_base_name]
    )
    for user in users:
        node_ids = nodes_by_user.get(user.id, [])
        protocols = _desired_protocols_list(user.desired_protocols)
        config_count = len(parse_plan_indexes(user.plan_config_indexes))
        owned = summaries.get(user.id)
        if owned is not None and not user.client_base_name:
            node_ids = owned.node_ids
            protocols = owned.protocols
            config_count = owned.name_count
            user.owned_config_base_name = owned.base_name
        user.plan_node_ids = node_ids
        user.plan_protocols = protocols
        user.plan_config_count = config_count
        user.active_task_id = active_task_by_user.get(user.id)
    consumed, last_seen = _user_list_traffic(db, users)
    for user in users:
        user.traffic_consumed_bytes = int(consumed.get(user.id, 0))
        user.last_seen_at = last_seen.get(user.id)
    online = _user_list_online(db, users)
    for user in users:
        user.online = bool(online.get(user.id, False))
    return users


def _user_list_traffic(
    db: Session, users: list[User]
) -> tuple[dict[int, int], dict[int, datetime | None]]:
    """Потреблённый трафик и последняя активность для списка (только при traffic_sync)."""
    from sqlalchemy import func

    from app.services.user_traffic_limit import user_consumed_bytes

    consumed: dict[int, int] = {}
    last_seen: dict[int, datetime | None] = {}
    if not get_feature_service().is_enabled("traffic_sync"):
        return consumed, last_seen
    ids = [u.id for u in users]
    owned = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id.in_(ids), VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    names_by_user: dict[int, set[str]] = {}
    for c in owned:
        names_by_user.setdefault(c.owner_id, set()).add(c.client_name.strip())
    all_names = {n for names in names_by_user.values() for n in names if n}
    name_seen: dict[str, datetime | None] = {}
    if all_names:
        rows = (
            db.query(
                UserTrafficStatProtocol.common_name,
                func.max(UserTrafficStatProtocol.last_seen_at),
            )
            .filter(UserTrafficStatProtocol.common_name.in_(all_names))
            .group_by(UserTrafficStatProtocol.common_name)
            .all()
        )
        name_seen = {r[0]: r[1] for r in rows}
    for u in users:
        names = names_by_user.get(u.id, set())
        if not names:
            continue
        if u.traffic_limit_bytes and u.traffic_counter_reset_at:
            consumed[u.id] = user_consumed_bytes(db, u)
        seen = [name_seen[n] for n in names if name_seen.get(n)]
        last_seen[u.id] = max(seen) if seen else None
    return consumed, last_seen


def _user_list_online(db: Session, users: list[User]) -> dict[int, bool]:
    """Есть ли у абонента активная VPN-сессия (по owned-конфигам)."""
    if not get_feature_service().is_enabled("traffic_sync"):
        return {}
    ids = [u.id for u in users]
    if not ids:
        return {}
    owned = (
        db.query(VpnConfig.owner_id, VpnConfig.client_name)
        .filter(VpnConfig.owner_id.in_(ids), VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    names_by_user: dict[int, set[str]] = {}
    for owner_id, client_name in owned:
        name = (client_name or "").strip()
        if name:
            names_by_user.setdefault(owner_id, set()).add(name)
    all_names = {n for names in names_by_user.values() for n in names}
    if not all_names:
        return {}
    threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    rows = (
        db.query(TrafficSessionState.common_name)
        .filter(
            TrafficSessionState.common_name.in_(all_names),
            TrafficSessionState.is_active.is_(True),
            TrafficSessionState.last_seen_at.isnot(None),
            TrafficSessionState.last_seen_at >= threshold,
        )
        .distinct()
        .all()
    )
    active_names = {row[0] for row in rows}
    return {u.id: bool(names_by_user.get(u.id, set()) & active_names) for u in users}


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing is not None:
        if existing.provision_state == "pending_deletion":
            raise _pending_deletion_conflict(db, existing, admin, what="Имя пользователя")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пользователь уже существует")
    validate_password(payload.password, username=payload.username)
    user = User(
        username=payload.username,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        theme=payload.theme,
        is_active=payload.is_active,
        must_change_password=password_change_required_on_admin_set(db),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_create",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"created={payload.username}, role={payload.role.value}",
        )
    admin_notify_service.send_user_create(
        db,
        actor_username=admin.username,
        target_name=user.username,
        details=f"role={payload.role.value}",
        client_timezone=get_client_timezone_from_request(request),
    )
    return user


@router.post(
    "/provisioned",
    response_model=UserProvisionedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@tg_mini_token_allowed
def create_provisioned_user(
    payload: UserProvisionedCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Создать абонента (role=user) с планом конфигов и сразу поставить задачу применения."""
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing is not None:
        if existing.provision_state == "pending_deletion":
            raise _pending_deletion_conflict(db, existing, admin, what="Имя пользователя")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Пользователь уже существует")
    if not payload.client_base_name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Укажите базовое имя конфигов (client_base_name)"
        )
    try:
        base = assert_client_base_name_valid(payload.client_base_name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    taken = db.query(User).filter(func.lower(User.client_base_name) == base.lower()).first()
    if taken is not None:
        if taken.provision_state == "pending_deletion":
            raise _pending_deletion_conflict(db, taken, admin, what="Базовое имя")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Базовое имя уже используется пользователем {taken.username}",
        )
    try:
        assert_name_not_reserved_by_other_user(db, base, owner_id=None)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    nodes = validate_plan_nodes(db, payload.node_ids)
    protocols = _validate_protocols(payload.protocols)
    indexes = list(range(1, payload.config_count + 1))

    if "amneziawg2" in protocols:
        from app.services.awg2 import assert_awg2_available_on_nodes

        assert_awg2_available_on_nodes(nodes)

    if not payload.panel_login_enabled:
        password = payload.password or secrets.token_urlsafe(24)
    else:
        if not payload.password:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Пароль обязателен, когда вход в панель включён",
            )
        password = payload.password
    validate_password(password, username=payload.username)

    user = User(
        username=payload.username,
        password_hash=get_password_hash(password),
        role=UserRole.user,
        panel_login_enabled=payload.panel_login_enabled,
        client_base_name=base,
        plan_config_indexes=json.dumps(indexes),
        desired_protocols=json.dumps(protocols),
        access_until=payload.access_until,
        config_quota=payload.config_quota,
        telegram_id=(payload.telegram_id or "").strip() or None,
        provision_state="unmanaged",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    for node in nodes:
        db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    user.provision_state = recompute_provision_state(db, user)
    db.commit()

    task = enqueue_user_provision(
        db, user_id=user.id, actor_username=admin.username, confirm_deletions=False
    )
    db.refresh(user)

    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_provision_create",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=(
                f"created={user.username}, base={base}, indexes={indexes}, "
                f"protocols={protocols}, nodes={[n.id for n in nodes]}"
            ),
        )
    return UserProvisionedResponse(user=_user_summary(user, [n.id for n in nodes]), task_id=task.id)


@router.post(
    "/from-existing",
    response_model=UserFromExistingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_from_existing_endpoint(
    payload: UserFromExistingCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Создать абонента без VPN-провижининга, опционально привязав существующие primary-конфиги."""
    from app.services.config_ownership import create_user_from_existing as _create

    assigned_ids = list(dict.fromkeys(payload.config_ids))
    user = _create(db, payload=payload, actor=admin)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_create",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=(
                f"created={user.username}, from_existing=true, "
                f"assigned_config_ids={assigned_ids}"
            ),
        )
    admin_notify_service.send_user_create(
        db,
        actor_username=admin.username,
        target_name=user.username,
        details=f"from_existing, configs={assigned_ids}",
        client_timezone=get_client_timezone_from_request(request),
    )
    return UserFromExistingResponse(
        user=_user_summary(user, []),
        assigned_config_ids=assigned_ids,
    )


@router.get("/presets", response_model=list[PresetResponse])
@tg_mini_token_allowed
def list_presets_endpoint(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Список шаблонов предоставления доступа (только если модуль включён)."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Раздел «Предоставление доступа» отключён администратором.",
        )
    return list_presets(db)


@router.post(
    "/presets",
    response_model=PresetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_preset_endpoint(
    payload: PresetCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Создать шаблон. При is_default флаг снимается со всех остальных."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Раздел «Предоставление доступа» отключён администратором.",
        )
    return create_preset(
        db,
        name=payload.name,
        node_ids=payload.node_ids,
        protocols=payload.protocols,
        config_count=payload.config_count,
        config_quota=payload.config_quota,
        traffic_limit_bytes=payload.traffic_limit_bytes,
        access_days=payload.access_days,
        is_default=payload.is_default,
    )


@router.put("/presets/{preset_id}", response_model=PresetResponse)
def update_preset_endpoint(
    preset_id: int,
    payload: PresetUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Обновить шаблон."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Раздел «Предоставление доступа» отключён администратором.",
        )
    row = update_preset(
        db,
        preset_id,
        name=payload.name,
        node_ids=payload.node_ids,
        protocols=payload.protocols,
        config_count=payload.config_count,
        config_quota=payload.config_quota,
        traffic_limit_bytes=payload.traffic_limit_bytes,
        access_days=payload.access_days,
        is_default=payload.is_default,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    return row


@router.delete("/presets/{preset_id}", response_model=MessageResponse)
def delete_preset_endpoint(
    preset_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Удалить шаблон."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Раздел «Предоставление доступа» отключён администратором.",
        )
    if not delete_preset(db, preset_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Шаблон не найден")
    return MessageResponse(message="Шаблон удалён")


def _require_provisioning() -> None:
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Раздел «Предоставление доступа» отключён администратором.",
        )


def _sync_request_messages_after_decide(
    request: UserAccessRequest, *, admin_username: str, approved: bool
) -> None:
    """Task 11: после решения в веб-панели обновить карточки заявки в чатах админов.

    В фоне: решение не должно ждать релей. Мёртвый узел в цепочке держал бы
    HTTP-ответ и соединение с БД десятками секунд, а панель выглядела бы зависшей.
    """
    text = (
        f"✅ Одобрено в веб-панели: {admin_username}"
        if approved
        else f"❌ Отклонено в веб-панели: {admin_username}"
    )
    request_id = request.id
    try:
        background_task_service.enqueue_background_task(
            "access_request_card_sync",
            lambda: _run_request_card_sync(request_id, text),
            queued_message="Обновление карточки заявки…",
        )
    except Exception as exc:  # never fail a panel decision because of Telegram
        logging.warning("telegram request cards sync enqueue failed: %s", exc)


def _run_request_card_sync(request_id: int, text: str) -> dict[str, Any]:
    """Фоновое обновление карточек заявки: своя сессия, свой event loop."""
    db = SessionLocal()
    try:
        request = db.get(UserAccessRequest, request_id)
        if request is None:
            return {"skipped": "request_not_found"}
        telegram_api.reset_bot_api_client_for_tests()
        try:
            asyncio.run(sync_admin_request_messages(db, request, text=text))
        finally:
            # Клиент httpx остался в уже закрытом цикле — без сброса следующий
            # вызов Telegram падает с «Event loop is closed».
            telegram_api.reset_bot_api_client_for_tests()
        return {"ok": True}
    except Exception as exc:  # never fail a panel decision because of Telegram
        logging.warning("telegram request cards sync failed: %s", exc)
        return {"error": str(exc)}
    finally:
        db.close()


@router.get("/requests", response_model=list[AccessRequestResponse])
@tg_mini_token_allowed
def list_access_requests(
    status: str | None = None,
    type: str | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None, max_length=100, description="Поиск по TG ID, нику и имени"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Список заявок на предоставление доступа: фильтры, поиск и страницы."""
    _require_provisioning()
    query = db.query(UserAccessRequest)
    if status:
        query = query.filter(UserAccessRequest.status == status)
    if type:
        query = query.filter(UserAccessRequest.request_type == type)
    needle = (q or "").strip().lower()
    if needle:
        pattern = f"%{needle}%"
        query = query.filter(
            or_(
                func.lower(UserAccessRequest.telegram_id).like(pattern),
                func.lower(func.coalesce(UserAccessRequest.telegram_username, "")).like(pattern),
                func.lower(func.coalesce(UserAccessRequest.telegram_name, "")).like(pattern),
            )
        )
    rows = (
        query.order_by(UserAccessRequest.id.desc()).offset(offset).limit(limit).all()
    )
    # Старые заявки создавались без имени/@ника — дозаполняем из Telegram
    # (best-effort, не чаще одного getChat на telegram_id в 10 минут).
    backfill_missing_request_profiles(
        db,
        [row for row in rows if not row.telegram_name and not row.telegram_username],
    )
    return [AccessRequestResponse.model_validate(row) for row in rows]


@router.get("/requests/count")
@tg_mini_token_allowed
def count_access_requests(
    status: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Сколько заявок с таким статусом — для бейджа и подписи кнопки."""
    query = db.query(func.count(UserAccessRequest.id))
    if status:
        query = query.filter(UserAccessRequest.status == status)
    return {"count": int(query.scalar() or 0)}


@router.get("/requests/cooldown", response_model=CooldownSettingsResponse)
def get_requests_cooldown(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=100, description="Поиск по TG ID или нику"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Настройка кулдауна после отказа и страница тех, кто сейчас в нём."""
    blocked, total = list_cooldown_blocked(db, limit=limit, offset=offset, q=q)
    return {"hours": cooldown_hours(db), "total": total, "blocked": blocked}


@router.put("/requests/cooldown", response_model=CooldownSettingsResponse)
def put_requests_cooldown(
    body: CooldownSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    set_cooldown_hours(db, body.hours)
    blocked, total = list_cooldown_blocked(db, limit=50, offset=0)
    return {"hours": cooldown_hours(db), "total": total, "blocked": blocked}


@router.post("/requests/cooldown/release", response_model=MessageResponse)
def release_requests_cooldown(
    body: CooldownReleaseRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Снять кулдаун с конкретного Telegram ID (отклонили случайно)."""
    released = release_cooldown(db, body.telegram_id)
    if settings.audit_log_enabled:
        log_action(
            db,
            action="access_request_cooldown_release",
            user_id=admin.id,
            username=admin.username,
            details=f"telegram_id={body.telegram_id}, requests={released}",
        )
    return MessageResponse(
        message=(
            f"Кулдаун снят ({released})" if released else "Этот Telegram ID не в кулдауне"
        )
    )


@router.post("/requests/{request_id}/approve", response_model=AccessRequestResponse)
@tg_mini_token_allowed
def approve_access_request(
    request_id: int,
    payload: ApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Одобрить заявку (с шаблоном или ad-hoc планом). Условие pending→approved."""
    _require_provisioning()
    row = db.get(UserAccessRequest, request_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    ad_hoc: dict[str, Any] | None = None
    if row.request_type == "new_user":
        if payload.preset_id is None:
            ad_hoc = {
                "node_ids": payload.node_ids or [],
                "protocols": payload.protocols or [],
                "config_count": payload.config_count,
                "access_until": payload.access_until,
                "traffic_limit_bytes": payload.traffic_limit_bytes,
                "username": payload.username,
            }
        elif payload.username or payload.access_until is not None:
            # Поверх шаблона: логин и/или срок из формы одобрения.
            ad_hoc = {}
            if payload.username:
                ad_hoc["username"] = payload.username
            if payload.access_until is not None:
                ad_hoc["access_until"] = payload.access_until
    elif row.request_type == "add_config":
        ad_hoc = {"count": payload.count}
    elif row.request_type == "extend_access":
        if payload.access_until is not None:
            target_user = db.get(User, row.user_id) if row.user_id else None
            if target_user is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, detail="Пользователь заявки не найден"
                )
            base = datetime.utcnow()
            if target_user.access_until is not None and target_user.access_until > base:
                base = target_user.access_until
            target = payload.access_until
            if target.tzinfo is not None:
                target = target.astimezone(timezone.utc).replace(tzinfo=None)
            delta = (target - base).total_seconds()
            if delta < 3600:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Дата продления должна быть позже текущего срока доступа",
                )
            # Сервис продлевает на целое число дней от max(сейчас, текущий срок).
            ad_hoc = {"days": max(1, math.ceil(delta / 86400))}
        else:
            ad_hoc = {"days": payload.days}
    try:
        decided = approve_request(
            db, request_id=request_id, admin=admin, preset_id=payload.preset_id, ad_hoc=ad_hoc
        )
    except AlreadyDecided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "already_decided", "message": "Заявка уже обработана"},
        )
    except TelegramAlreadyBound as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "telegram_already_bound",
                "message": exc.admin_detail,
                "actions": ["extend_user", "open_card"],
                "user_id": exc.user_id,
                "username": exc.username,
            },
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if decided is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    if settings.audit_log_enabled:
        log_action(
            db,
            action="access_request_approve",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"request_id={request_id}, type={row.request_type}",
        )
    _sync_request_messages_after_decide(decided, admin_username=admin.username, approved=True)
    from app.services.telegram_widgets import refresh_access_request_cards_sync

    refresh_access_request_cards_sync(decided.id)
    return AccessRequestResponse.model_validate(decided)


@router.post("/requests/{request_id}/reject", response_model=AccessRequestResponse)
@tg_mini_token_allowed
def reject_access_request(
    request_id: int,
    payload: RejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Отклонить заявку с опциональной блокировкой telegram_id."""
    _require_provisioning()
    row = db.get(UserAccessRequest, request_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    try:
        decided = reject_request(
            db, request_id=request_id, admin=admin, reason=payload.reason, ban=payload.ban
        )
    except AlreadyDecided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "already_decided", "message": "Заявка уже обработана"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if decided is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Заявка не найдена")
    if settings.audit_log_enabled:
        log_action(
            db,
            action="access_request_reject",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"request_id={request_id}, ban={payload.ban}",
        )
    _sync_request_messages_after_decide(decided, admin_username=admin.username, approved=False)
    from app.services.telegram_widgets import refresh_access_request_cards_sync

    refresh_access_request_cards_sync(decided.id)
    return AccessRequestResponse.model_validate(decided)


@router.get("/requests/{request_id}/receipt")
@tg_mini_token_allowed
def get_request_receipt(
    request_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Превью чека оплаты заявки (только админ). Перекодировка Pillow в памяти, без диска."""
    req = db.get(UserAccessRequest, request_id)
    if not req or not req.receipt_file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Чек не найден")
    try:
        data = get_cached_or_build_preview(db, req)
    except ReceiptDecodeError:
        from app.services.telegram_transport import relay_node_ids

        detail = "Не удалось открыть чек"
        if relay_node_ids():
            detail = (
                "Чек не скачивается: Telegram работает через узел-релей. "
                "Откройте фото в Telegram — карточка заявки с чеком."
            )
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/bulk/nodes/preview", response_model=BulkNodesPreviewResponse)
def bulk_nodes_preview(
    body: BulkNodesRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Предпросмотр массовой операции с серверами: что изменится и кто пропущен."""
    _require_provisioning()
    preview = build_bulk_nodes_preview(
        db,
        action=body.action,
        node_id=body.node_id,
        to_node_id=body.to_node_id,
        scope=body.scope,
        notify_telegram=body.notify_telegram,
        note=body.note,
    )
    return _bulk_nodes_preview_response(preview)


@router.post("/bulk/nodes", status_code=status.HTTP_202_ACCEPTED)
def bulk_nodes_start(
    body: BulkNodesRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Запустить массовую операцию с серверами (одна фоновая задача за раз)."""
    _require_provisioning()
    if body.action in ("remove", "replace"):
        # Удаляет конфиги у многих пользователей — подтверждаем именем сервера.
        node = assert_assignable_vpn_node(db, body.node_id)
        if (body.confirm_node_name or "").strip() != node.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Введите имя сервера «{node.name}» для подтверждения",
            )
    task = enqueue_bulk_user_nodes(db, body=body, actor=admin)
    return {"task_id": task.id}


@router.get("/bulk/nodes/tasks/{task_id}/report")
def bulk_nodes_report(
    task_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Скачать JSON-отчёт по массовой операции с серверами."""
    _require_provisioning()
    task = db.get(BackgroundTask, task_id)
    if task is None or task.task_type != "bulk_user_nodes":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")
    if task.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Задача ещё выполняется"
        )
    try:
        data = json.loads(task.output or "{}")
    except (TypeError, ValueError):
        data = {}
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="bulk-nodes-{task_id}.json"'
        },
    )


def _telegram_bot_token(db: Session) -> str:
    return _get_setting(db, "telegram_bot_token", "").strip()


@router.post("/bulk/notify", status_code=status.HTTP_202_ACCEPTED)
def bulk_notify_start(
    body: BulkNotifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Запустить массовое сообщение выбранным абонентам в Telegram."""
    _require_provisioning()
    if not get_feature_service().is_enabled("telegram"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Модуль Telegram выключен"
        )
    bot_token = _telegram_bot_token(db)
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Telegram-бот не настроен"
        )
    users = db.query(User).filter(User.id.in_(body.user_ids)).all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Абоненты не найдены"
        )
    recipients = [u for u in users if (u.telegram_id or "").strip()]
    if not recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нет абонентов с привязанным Telegram",
        )
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Текст сообщения пуст"
        )
    task_id = start_bulk_user_notify(
        user_ids=[u.id for u in recipients],
        text=text,
        bot_token=bot_token,
        actor_username=admin.username,
    )
    log_action(
        db,
        action="user_bulk_notify",
        user_id=admin.id,
        username=admin.username,
        remote_addr=ip_restriction_service.get_client_ip(request),
        details=f"recipients={len(recipients)}",
    )
    return {"task_id": task_id}


@router.get("/bulk/notify/tasks/{task_id}/report")
def bulk_notify_report(
    task_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Скачать JSON-отчёт по массовому уведомлению."""
    _require_provisioning()
    task = db.get(BackgroundTask, task_id)
    if task is None or task.task_type != BULK_NOTIFY_TASK_TYPE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отчёт не найден")
    if task.status not in ("completed", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Задача ещё выполняется"
        )
    try:
        data = json.loads(task.output or "{}")
    except (TypeError, ValueError):
        data = {}
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="bulk-notify-{task_id}.json"'
        },
    )


def _client_ip(request):
    """IP клиента строкой или None (устойчиво к мок-request в тестах)."""
    if request is None:
        return None
    ip = ip_restriction_service.get_client_ip(request)
    return ip if isinstance(ip, str) else None


def _record_user_history(db, *, action, current_user, user, request, details=None):
    """Безусловная запись действия по абоненту (не зависит от audit_log_enabled)."""
    log_action(
        db,
        action=action,
        user_id=current_user.id,
        username=current_user.username,
        remote_addr=_client_ip(request),
        details=details or f"target={user.username}",
        target_user_id=user.id,
    )


@router.get("/{user_id}/history", response_model=list[UserHistoryEntry])
@tg_mini_token_allowed
def user_history(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    rows = (
        db.query(UserActionLog)
        .filter(UserActionLog.target_user_id == user_id)
        .order_by(UserActionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        UserHistoryEntry(
            id=r.id,
            actor_username=r.username,
            action=r.action,
            details=r.details,
            created_at=r.created_at,
        )
        for r in rows
    ]


_ADMIN_ONLY_FIELD_RULES: tuple[tuple[str, bool, str], ...] = (
    ("traffic_limit_bytes", True, "лимит трафика"),
    ("role", False, "роль"),
    ("is_active", False, "статус"),
    ("panel_login_enabled", True, "вход в панель"),
    ("access_until", True, "срок доступа"),
    ("config_quota", False, "квоту"),
    ("can_create_configs", False, "право создания конфигов"),
    ("can_manage_configs", False, "право управления конфигами"),
    ("visible_vpn_profiles", True, "видимость VPN-профилей"),
    ("note", True, "заметку"),
)


def _reject_non_admin_field_changes(payload: UserUpdate, *, is_admin: bool) -> None:
    """403 on admin-only fields; predicates match how each block below decides it was sent."""
    if is_admin:
        return
    for field, by_presence, label in _ADMIN_ONLY_FIELD_RULES:
        changed = field in payload.model_fields_set if by_presence else getattr(payload, field) is not None
        if changed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Только администратор может менять {label}",
            )


@router.patch("/{user_id}", response_model=UserResponse)
@tg_mini_token_allowed
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    is_admin = current_user.role == UserRole.admin
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    if payload.password and current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Свой пароль меняется в настройках профиля с вводом текущего пароля",
        )

    _reject_non_admin_field_changes(payload, is_admin=is_admin)

    old_telegram_id = user.telegram_id
    access_until_updated = False
    pending_access_until = None
    traffic_limit_requested = "traffic_limit_bytes" in payload.model_fields_set

    if traffic_limit_requested:
        if payload.traffic_limit_bytes is not None and not get_feature_service().is_enabled(
            "traffic_sync"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Для лимита трафика включите модуль «Синхронизация трафика» "
                    "в Настройках → Модули"
                ),
            )

    if payload.role is not None:
        if user.role == UserRole.admin and payload.role != UserRole.admin:
            other_admins = (
                db.query(User)
                .filter(User.role == UserRole.admin, User.id != user.id, User.is_active.is_(True))
                .count()
            )
            if other_admins == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Нельзя снять роль у последнего администратора",
                )
        old_role = user.role
        user.role = payload.role
        revoke_creator_portal_links(db, user.id)
        if (
            old_role == UserRole.admin
            and payload.role == UserRole.user
            and "can_manage_configs" not in payload.model_fields_set
        ):
            user.can_manage_configs = False
    if payload.theme is not None:
        user.theme = payload.theme
    if payload.is_active is not None:
        if user.is_active and not payload.is_active:
            invalidate_user_sessions(db, user, reason="disabled", commit=False)
            active_web_session_service.revoke_user_sessions(db, user.username, commit=False)
        user.is_active = payload.is_active
    if "panel_login_enabled" in payload.model_fields_set:
        if payload.panel_login_enabled is False and user.panel_login_enabled:
            # Existing access/refresh sessions stop working: token_version bumps all JWTs,
            # revoke_user_sessions ends the active web sessions.
            user.token_version = (user.token_version or 0) + 1
            active_web_session_service.revoke_user_sessions(db, user.username, commit=False)
        user.panel_login_enabled = payload.panel_login_enabled
    if "access_until" in payload.model_fields_set:
        access_until_updated = True
        pending_access_until = payload.access_until
    if payload.password:
        validate_password(payload.password, username=user.username)
        user.password_hash = get_password_hash(payload.password)
        invalidate_user_sessions(db, user, reason="password", commit=False)
        if password_change_required_on_admin_set(db):
            user.must_change_password = True
    if payload.telegram_id is not None:
        tg_id = payload.telegram_id.strip()
        # Non-admins may only clear their own telegram_id (self-unlink).
        if not is_admin and (current_user.id != user_id or tg_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять Telegram ID",
            )
        had_tg = bool((user.telegram_id or "").strip())
        if tg_id:
            release_telegram_of_pending_deletion(db, tg_id, keep_user_id=user.id)
            existing = (
                db.query(User)
                .filter(
                    User.telegram_id == tg_id,
                    User.id != user.id,
                    User.provision_state != "pending_deletion",
                )
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Этот Telegram ID уже привязан к другому пользователю",
                )
            user.telegram_id = tg_id
        else:
            user.telegram_id = None
        if settings.audit_log_enabled and had_tg and not user.telegram_id:
            log_action(
                db,
                action="telegram_unlink",
                user_id=current_user.id,
                username=current_user.username,
                remote_addr=ip_restriction_service.get_client_ip(request),
                details=f"target={user.username}",
            )
    if payload.config_quota is not None:
        user.config_quota = payload.config_quota
    if payload.can_create_configs is not None:
        user.can_create_configs = payload.can_create_configs
    if payload.can_manage_configs is not None:
        user.can_manage_configs = payload.can_manage_configs
    if "visible_vpn_profiles" in payload.model_fields_set:
        if payload.visible_vpn_profiles is None:
            user.visible_vpn_profiles = None
        else:
            normalized = normalize_policy(payload.visible_vpn_profiles, strict=True)
            user.visible_vpn_profiles = policy_to_json(normalized)
    if "note" in payload.model_fields_set:
        user.note = (payload.note or "").strip() or None

    cascade_warning: str | None = None
    if access_until_updated:
        # Cascade only on a real change — otherwise every unrelated save
        # (telegram_id, quota, visibility) would wipe confirmed per-client overrides.
        access_until_changed = normalize_access_until(pending_access_until) != get_user_access_until(user)
        user, cascade = set_user_access_until(
            db,
            user,
            pending_access_until,
            actor=current_user.username,
            sync_clients=access_until_changed,
            commit=True,
        )
        if cascade:
            cascade_warning = cascade.get("warning")
    else:
        db.commit()
        db.refresh(user)
    if traffic_limit_requested:
        _set_user_traffic_limit(
            db, user, payload.traffic_limit_bytes, actor=current_user.username
        )
        db.refresh(user)
    if payload.telegram_id is not None:
        notify_telegram_unlinked(
            db,
            old_telegram_id=old_telegram_id,
            new_telegram_id=user.telegram_id,
            username=user.username,
        )
    if payload.password and should_scrub_env_after_password_change(user.username):
        scrub_admin_bootstrap_secret_from_env()
    if (
        payload.password
        or payload.role is not None
        or payload.is_active is not None
        or access_until_updated
        or "note" in payload.model_fields_set
    ):
        _record_user_history(
            db, action="user_update", current_user=current_user, user=user, request=request
        )
    response = UserResponse.model_validate(user)
    if cascade_warning:
        response.access_cascade_warning = cascade_warning
    return response


@router.post("/{user_id}/suspend")
@tg_mini_token_allowed
def suspend_user(
    user_id: int,
    payload: UserSuspendRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Приостановить доступ пользователя: sticky user_suspended блок на все его конфиги."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.role == UserRole.admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Нельзя приостановить администратора"
        )
    user.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
    user.suspend_reason = (payload.reason or "").strip() or None
    user.suspend_reason_visible = bool(payload.show_reason)
    db.commit()
    apply_user_block(db, user, "user_suspended", actor=current_user.username)
    if payload.notify_telegram and user.telegram_id:
        bot_token = _get_setting(db, "telegram_bot_token")
        if bot_token:
            send_tg_message(bot_token, user.telegram_id, _suspend_notify_text(user))
    _record_user_history(
        db, action="user_suspend", current_user=current_user, user=user, request=request
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/resume")
@tg_mini_token_allowed
def resume_user(
    user_id: int,
    payload: UserResumeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Возобновить доступ пользователя: снять user_suspended, при 필요 вернуть user_traffic_limit."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    user.suspended_at = None
    user.suspend_reason = None
    user.suspend_reason_visible = False
    db.commit()
    lift_user_block(db, user, "user_suspended", actor=current_user.username)
    if payload.notify_telegram and user.telegram_id:
        bot_token = _get_setting(db, "telegram_bot_token")
        if bot_token:
            send_tg_message(bot_token, user.telegram_id, "Доступ возобновлён.")
    _record_user_history(
        db, action="user_resume", current_user=current_user, user=user, request=request
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/extend")
@tg_mini_token_allowed
def extend_user_access(
    user_id: int,
    payload: UserExtendRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Продлить доступ на N дней (max(now, access_until) + days) и сбросить счётчик трафика."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    new_until = compute_extended_access_until(get_user_access_until(user), payload.days)
    set_user_access_until(db, user, new_until, actor=current_user.username)
    _record_user_history(
        db, action="user_extend", current_user=current_user, user=user, request=request
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/traffic-counter/reset")
@tg_mini_token_allowed
def reset_user_traffic_counter_endpoint(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Сбросить счётчик трафика пользователя и снять блок user_traffic_limit."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    from app.services.user_traffic_limit import reset_user_traffic_counter

    reset_user_traffic_counter(db, user, actor=current_user.username)
    db.refresh(user)
    _record_user_history(
        db,
        action="user_traffic_counter_reset",
        current_user=current_user,
        user=user,
        request=request,
    )
    return UserResponse.model_validate(user)


@router.post("/{user_id}/grace-cleanup")
def grace_cleanup_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Удалить все конфиги пользователя после grace; план (base/indexes) сохранить → pending."""
    if not get_feature_service().is_enabled("user_provisioning"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    from app.services.user_grace import run_grace_cleanup

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    result = run_grace_cleanup(db, user, actor=current_user)
    _record_user_history(
        db, action="user_grace_cleanup", current_user=current_user, user=user, request=None
    )
    return {"ok": True, **result}


def _last_provision_task(db: Session, user_id: int) -> dict | None:
    task = (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.task_type == TASK_TYPE,
            BackgroundTask.subject_key == f"user:{user_id}",
        )
        .order_by(BackgroundTask.created_at.desc())
        .first()
    )
    return background_task_service.serialize_background_task(task) if task is not None else None


def _group_provision_configs(
    db: Session, user: User, configs: list[VpnConfig] | None = None
) -> list[ProvisioningConfig]:
    """Все конфиги владельца — и плановые, и оставшиеся вне плана.

    Раньше фильтр по namespace ``client_base_name`` и по узлам плана прятал конфиг,
    переназначенный пользователю с другим базовым именем: он исчезал и у прежнего
    владельца (сменился ``owner_id``), и у нового (имя вне namespace).
    """
    if configs is None:
        configs = (
            db.query(VpnConfig)
            .filter(VpnConfig.owner_id == user.id, VpnConfig.ha_primary_config_id.is_(None))
            .all()
        )
    node_ids = {config.node_id for config in configs}
    labels = (
        {node.id: node.name for node in db.query(Node).filter(Node.id.in_(node_ids)).all()}
        if node_ids
        else {}
    )
    by_name: dict[str, list[dict]] = defaultdict(list)
    for config in configs:
        by_name[config.client_name].append(
            {
                "node_id": config.node_id,
                "node_label": labels.get(config.node_id, str(config.node_id)),
                "vpn_type": config.vpn_type.value,
                "config_id": config.id,
            }
        )
    return [
        ProvisioningConfig(
            name=name,
            nodes=sorted(entries, key=lambda entry: (entry["node_label"], entry["vpn_type"])),
        )
        for name, entries in sorted(by_name.items())
    ]


@router.get("/{user_id}/provisioning", response_model=UserProvisioningCard)
def get_provisioning(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    assignments = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    node_ids = [row.node_id for row in assignments]
    base = user.client_base_name
    has_plan = user_has_plan(user)

    desired = UserProvisioningDesired(
        client_base_name=base,
        plan_config_indexes=parse_plan_indexes(user.plan_config_indexes),
        desired_protocols=_desired_protocols_list(user.desired_protocols),
        node_ids=node_ids,
    )
    suggested: UserProvisioningSuggested | None = None
    if not has_plan:
        prefill = prefill_for_unmanaged(db, user)
        suggested = UserProvisioningSuggested(**prefill) if prefill else None

    plan = compute_plan(db, user) if has_plan else None
    serialized_plan = _serialize_plan(plan) if plan is not None else ProvisionPlanResponse()

    # Без плана сводку шапки и вкладки «Конфиги» строим по фактическим конфигам
    # владельца (абонент создан «из существующих» или конфиг привязан позже).
    owned_configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user.id, VpnConfig.ha_primary_config_id.is_(None))
        .all()
    )
    owned = summarize_owned_configs(owned_configs) if owned_configs else None
    summary_node_ids = owned.node_ids if (owned is not None and not has_plan) else node_ids

    from app.services.user_closed_access import grace_hold_view
    from app.services.user_grace import get_grace_months
    from app.services.user_traffic_limit import user_consumed_bytes

    grace_hold = grace_hold_view(user, get_grace_months(db))
    consumed = user_consumed_bytes(db, user)
    online = bool(_user_list_online(db, [user]).get(user.id, False))

    return UserProvisioningCard(
        user=_user_summary(
            user,
            summary_node_ids,
            traffic_consumed_bytes=consumed,
            online=online,
            owned_base_name=owned.base_name if (owned is not None and not has_plan) else None,
        ),
        has_plan=has_plan,
        desired=desired,
        suggested=suggested,
        plan=serialized_plan,
        configs=_group_provision_configs(db, user, owned_configs),
        last_task=_last_provision_task(db, user.id),
        grace_hold=GraceHoldView(**grace_hold) if grace_hold else None,
    )


@router.put("/{user_id}/provisioning", response_model=UserProvisionedResponse)
def update_provisioning(
    user_id: int,
    payload: UserProvisioningUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

    new_base = payload.client_base_name
    if new_base is None:
        if not user.client_base_name:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="У пользователя нет базового имени конфигов",
            )
        new_base = user.client_base_name
    if new_base != user.client_base_name:
        try:
            new_base = assert_client_base_name_valid(new_base)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if user.client_base_name:
            in_plan = db.query(VpnConfig).filter(VpnConfig.owner_id == user.id).all()
            if any((c.client_name or "").lower() in names_under_base(user.client_base_name) for c in in_plan):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Нельзя сменить базовое имя: у пользователя уже есть конфиги в плане",
                )
        taken = (
            db.query(User)
            .filter(func.lower(User.client_base_name) == new_base.lower(), User.id != user.id)
            .first()
        )
        if taken is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Базовое имя уже используется пользователем {taken.username}",
            )
        try:
            assert_name_not_reserved_by_other_user(db, new_base, owner_id=user.id)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))

    indexes = _validate_indexes(payload.plan_config_indexes)
    protocols = _validate_protocols(payload.protocols)
    nodes = validate_plan_nodes(db, payload.node_ids)

    if "amneziawg2" in protocols:
        from app.services.awg2 import assert_awg2_available_on_nodes

        assert_awg2_available_on_nodes(nodes)

    user.client_base_name = new_base
    user.plan_config_indexes = json.dumps(indexes)
    user.desired_protocols = json.dumps(protocols)
    db.query(UserNodeAssignment).filter_by(user_id=user.id).delete(synchronize_session=False)
    for node in nodes:
        db.add(UserNodeAssignment(user_id=user.id, node_id=node.id))
    user.provision_state = recompute_provision_state(db, user)
    db.commit()

    task = enqueue_user_provision(
        db,
        user_id=user.id,
        actor_username=admin.username,
        confirm_deletions=payload.confirm_deletions,
    )
    db.refresh(user)

    _record_user_history(
        db,
        action="user_provision_update",
        current_user=admin,
        user=user,
        request=request,
        details=f"target={user.username}, indexes={indexes}, protocols={protocols}",
    )
    return UserProvisionedResponse(user=_user_summary(user, [n.id for n in nodes]), task_id=task.id)


@router.post("/{user_id}/provisioning/apply", status_code=status.HTTP_202_ACCEPTED)
def apply_provisioning(
    user_id: int,
    payload: UserProvisioningApply,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    task = enqueue_user_provision(
        db, user_id=user.id, actor_username=admin.username, confirm_deletions=payload.confirm_deletions
    )
    return {"task_id": task.id}


@router.post("/{user_id}/provisioning/configs")
def add_provisioning_config(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if not user.client_base_name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="У пользователя нет плана конфигов"
        )
    indexes = _validate_indexes(parse_plan_indexes(user.plan_config_indexes))
    used = set(indexes)
    free = next((item for item in range(1, 21) if item not in used), None)
    if free is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Нет свободных индексов имён (1..20)")
    indexes.append(free)
    user.plan_config_indexes = json.dumps(sorted(indexes))
    user.provision_state = recompute_provision_state(db, user)
    db.commit()

    task = enqueue_user_provision(
        db, user_id=user.id, actor_username=admin.username, confirm_deletions=False
    )
    db.refresh(user)
    assignments = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    return {
        "index": free,
        "task_id": task.id,
        "user": _user_summary(user, [row.node_id for row in assignments]),
    }


@router.delete("/{user_id}/provisioning/configs/{index}")
def remove_provisioning_config(
    user_id: int,
    index: int,
    confirm_deletions: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Удалить имя плана по индексу. `confirm_deletions` передаётся query-параметром.

    Последнее имя удалить нельзя (409 `last_config_name`); если при удалении
    получаются удаления конфигов без флага confirm_deletions — 409 `confirm_deletions`.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if not user.client_base_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="У пользователя нет плана конфигов")
    if index < 1 or index > 20:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Индекс должен быть от 1 до 20")

    indexes = _validate_indexes(parse_plan_indexes(user.plan_config_indexes))
    if index not in indexes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Индекс не в плане пользователя")
    if len(indexes) == 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "last_config_name",
                "message": "Последнее имя плана нельзя удалить — удалите пользователя или очистите план",
            },
        )

    original = user.plan_config_indexes
    user.plan_config_indexes = json.dumps([item for item in indexes if item != index])
    plan = compute_plan(db, user)
    user.plan_config_indexes = original
    if plan.delete and not confirm_deletions:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "confirm_deletions",
                "configs": [
                    {
                        "node_id": item.node_id,
                        "node_label": item.node_label,
                        "client_name": item.client_name,
                        "vpn_type": item.vpn_type,
                        "config_id": item.config_id,
                        "reason": item.reason,
                    }
                    for item in plan.delete
                ],
            },
        )

    user.plan_config_indexes = json.dumps(sorted(item for item in indexes if item != index))
    user.provision_state = recompute_provision_state(db, user)
    db.commit()
    task = enqueue_user_provision(
        db,
        user_id=user.id,
        actor_username=admin.username,
        confirm_deletions=confirm_deletions,
    )
    db.refresh(user)
    assignments = db.query(UserNodeAssignment).filter_by(user_id=user.id).all()
    return UserProvisionedResponse(
        user=_user_summary(user, [row.node_id for row in assignments]), task_id=task.id
    )


@router.get("/{user_id}/configs/{config_id}/files")
def config_files(
    user_id: int,
    config_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """D2: список файлов профиля с узла конфига."""
    config = _get_owned_config(db, user_id, config_id)
    op_config, node = _resolve_op_config_and_node(db, config)
    require_ha_primary_for_client_ops(db, node=node)
    adapter = get_adapter_for_node(node)
    files = adapter.get_profile_files(op_config.client_name, op_config.vpn_type)
    return {"files": enrich_profile_files(op_config.client_name, files)}


@router.get("/{user_id}/configs/{config_id}/download")
def config_download(
    user_id: int,
    config_id: int,
    path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """D2: скачать файл профиля с узла конфига."""
    config = _get_owned_config(db, user_id, config_id)
    op_config, node = _resolve_op_config_and_node(db, config)
    require_ha_primary_for_client_ops(db, node=node)
    adapter = get_adapter_for_node(node)
    _require_profile_path_allowed(db, current_user, op_config, path, adapter=adapter)
    hosts = load_node_remote_hosts(db, node.id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    filename = build_profile_download_filename(op_config.client_name, path=path)
    return attachment_response(content, filename)


@router.get("/{user_id}/configs/{config_id}/qr")
def config_qr(
    user_id: int,
    config_id: int,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """D2: QR-код профиля с узла конфига."""
    config = _get_owned_config(db, user_id, config_id)
    op_config, node = _resolve_op_config_and_node(db, config)
    require_ha_primary_for_client_ops(db, node=node)
    adapter = get_adapter_for_node(node)
    _require_profile_path_allowed(db, current_user, op_config, path, adapter=adapter)
    hosts = load_node_remote_hosts(db, node.id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    if prefers_download_link_qr(path=path, content=content):
        link = _qr_download_service(db, request).create_token(
            file_path=path,
            config_type=op_config.vpn_type.value,
            config_name=build_profile_download_filename(op_config.client_name, path=path),
            node_id=node.id,
            creator_id=current_user.id,
            creator_username=current_user.username,
            remote_addr=request.client.host if request.client else None,
        )
        png = generate_qr_png(link["url"])
        headers = {
            "X-Qr-Content": "download-link",
            "X-Qr-Download-Url": link["url"],
            "Access-Control-Expose-Headers": "X-Qr-Content, X-Qr-Download-Url",
        }
        return Response(content=png, media_type="image/png", headers=headers)
    png = generate_qr_png(content)
    headers = {
        "X-Qr-Content": "profile",
        "Access-Control-Expose-Headers": "X-Qr-Content, X-Qr-Download-Url",
    }
    return Response(content=png, media_type="image/png", headers=headers)


@router.post("/{user_id}/configs/{config_id}/access")
def config_access(
    user_id: int,
    config_id: int,
    payload: ConfigAccessOpRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """D2: block_temp / block_perm / unblock на узле конфига (сервис client_access)."""
    config = _get_owned_config(db, user_id, config_id)
    op_config, node = _resolve_op_config_and_node(db, config)
    require_ha_primary_for_client_ops(db, node=node)
    adapter = get_adapter_for_node(node)
    service = AccessPolicyService(
        db,
        antizapret_path=_antizapret_path_for_node(db, node),
        node_id=node.id,
        node_name=node.name,
        adapter=adapter,
    )
    client_name = op_config.client_name
    actor = current_user.username
    if payload.op == "block_temp":
        if not payload.days:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите срок блокировки")
        if op_config.vpn_type == VpnType.openvpn:
            result = service.openvpn_temp_block(client_name, payload.days, actor=actor)
        elif op_config.vpn_type == VpnType.wireguard:
            result = service.wg_temp_block(client_name, payload.days, actor=actor)
        else:
            result = service.awg2_temp_block(client_name, payload.days, actor=actor)
    elif payload.op == "block_perm":
        if op_config.vpn_type == VpnType.openvpn:
            result = service.openvpn_permanent_block(client_name, actor=actor)
        elif op_config.vpn_type == VpnType.wireguard:
            result = service.wg_permanent_block(client_name, actor=actor)
        else:
            result = service.awg2_permanent_block(client_name, actor=actor)
    elif payload.op == "unblock":
        if op_config.vpn_type == VpnType.openvpn:
            result = service.openvpn_unblock(client_name, actor=actor)
        elif op_config.vpn_type == VpnType.wireguard:
            result = service.wg_unblock(client_name, actor=actor)
        else:
            result = service.awg2_unblock(client_name, actor=actor)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестная операция доступа")
    log_action(
        db,
        action=f"config_access_{payload.op}",
        user_id=current_user.id,
        username=current_user.username,
        remote_addr=request.client.host if request.client else None,
        details=f"config={config.id} client={client_name} op={payload.op}",
    )
    return result


@router.delete("/{user_id}/configs/{config_id}", response_model=MessageResponse)
def config_delete(
    user_id: int,
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """D2: deprovision конфига; если в плане — provision_state = pending."""
    config = _get_owned_config(db, user_id, config_id)
    op_config, node = _resolve_op_config_and_node(db, config)
    require_ha_primary_for_client_ops(db, node=node)
    user = db.get(User, user_id)
    plan_delete = is_in_plan_config(db, user, op_config)
    deprovision_config(db, config=op_config, actor=current_user, notify=True, request=request)
    if plan_delete:
        user.provision_state = "pending"
        db.commit()
    return MessageResponse(message=f"Клиент '{op_config.client_name}' удалён")


@router.get("/{user_id}/stats", response_model=UserStatsResponse)
@tg_mini_token_allowed
def user_stats(
    user_id: int,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """D13: трафик пользователя по его конфигам (тень HA складывается в primary-узел)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    retention_days = int(get_settings().traffic_sample_retention_days or 90)
    days = min(days, retention_days)
    until_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    since_utc = until_utc - timedelta(days=days)

    totals = UserTrafficTotals()
    rows: list[UserTrafficStatRow] = []
    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.owner_id == user_id, VpnConfig.ha_primary_config_id.is_(None))
        .order_by(VpnConfig.client_name, VpnConfig.node_id)
        .all()
    )
    for config in configs:
        scope = resolve_traffic_scope(db, config.node_id)
        scope_ids = scope.node_ids
        stats = (
            db.query(UserTrafficStatProtocol)
            .filter(
                UserTrafficStatProtocol.node_id.in_(scope_ids),
                UserTrafficStatProtocol.common_name == config.client_name,
            )
            .all()
        )
        rx = tx = rx_vpn = tx_vpn = rx_az = tx_az = sessions = 0
        first_seen: datetime | None = None
        last_seen: datetime | None = None
        for row in stats:
            rx += int(row.total_received or 0)
            tx += int(row.total_sent or 0)
            rx_vpn += int(row.total_received_vpn or 0)
            tx_vpn += int(row.total_sent_vpn or 0)
            rx_az += int(row.total_received_antizapret or 0)
            tx_az += int(row.total_sent_antizapret or 0)
            sessions += int(row.total_sessions or 0)
            if row.first_seen_at is not None and (first_seen is None or row.first_seen_at < first_seen):
                first_seen = row.first_seen_at
            if row.last_seen_at is not None and (last_seen is None or row.last_seen_at > last_seen):
                last_seen = row.last_seen_at
        samples = (
            db.query(UserTrafficSample)
            .filter(
                UserTrafficSample.node_id.in_(scope_ids),
                UserTrafficSample.common_name == config.client_name,
                UserTrafficSample.created_at >= since_utc,
                UserTrafficSample.created_at < until_utc,
            )
            .all()
        )
        period_bytes = 0
        daily: dict[str, int] = {}
        for sample in samples:
            period_bytes += int(sample.delta_received or 0) + int(sample.delta_sent or 0)
            day = sample.created_at.date().isoformat()
            daily[day] = daily.get(day, 0) + int(sample.delta_received or 0) + int(sample.delta_sent or 0)
        rows.append(
            UserTrafficStatRow(
                node_id=config.node_id,
                client_name=config.client_name,
                vpn_type=config.vpn_type.value,
                total_received=rx,
                total_sent=tx,
                total_bytes=rx + tx,
                total_received_vpn=rx_vpn,
                total_sent_vpn=tx_vpn,
                total_received_antizapret=rx_az,
                total_sent_antizapret=tx_az,
                total_sessions=sessions,
                period_bytes=period_bytes,
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                daily=[{"date": d, "bytes": b} for d, b in sorted(daily.items())],
            )
        )
        totals.received += rx
        totals.sent += tx
        totals.received_vpn += rx_vpn
        totals.sent_vpn += tx_vpn
        totals.received_antizapret += rx_az
        totals.sent_antizapret += tx_az
        totals.sessions += sessions
        totals.period_bytes += period_bytes
    totals.bytes = totals.received + totals.sent
    return UserStatsResponse(user_id=user_id, period_days=days, rows=rows, totals=totals)


@router.post("/{user_id}/telegram-link-code", response_model=TelegramLinkCodeResponse)
def telegram_link_code_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Админ выдаёт код привязки Telegram другому пользователю."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    code, ttl = create_link_code(db, target)
    return TelegramLinkCodeResponse(code=code, expires_in_seconds=ttl)


@router.get("/{user_id}/config-access", response_model=UserConfigAccessResponse)
def get_user_config_access_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    return UserConfigAccessResponse(user_id=user_id, config_groups=get_user_config_grants(db, user_id))


@router.put("/{user_id}/config-access", response_model=MessageResponse)
def put_user_config_access_endpoint(
    user_id: int,
    payload: UserConfigAccessUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    if user.role != UserRole.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Доп. доступ к клиентам доступен только для роли «Пользователь»",
        )
    set_user_config_access(db, user_id, payload.config_groups)
    return MessageResponse(message="Доступ к клиентам обновлён")


def _delete_user_core(db, user, current_user, request) -> tuple[str, bool]:
    """Удалить абонента (без плана) или запустить фоновую очистку (с планом).

    Возвращает (username, pending). История пишется с target_user_id.
    """
    if current_user.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить себя")
    if user.role == UserRole.admin:
        other_admins = (
            db.query(User)
            .filter(User.role == UserRole.admin, User.id != user.id, User.is_active.is_(True))
            .count()
        )
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить последнего администратора",
            )
    deleted_username = user.username
    target_id = user.id
    delete_user_write_archive(db, user)
    revoke_user_bound_unlock_codes(db, user.id)
    active_provision = (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.task_type == TASK_TYPE,
            BackgroundTask.subject_key == f"user:{target_id}",
            BackgroundTask.status.in_(["queued", "running"]),
        )
        .first()
    )
    if active_provision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "user_provision_in_progress",
                "message": "У пользователя выполняется задача предоставления конфигов",
            },
        )
    has_plan = user_has_plan(user)
    if user.role != UserRole.admin:
        revoke_creator_portal_links(db, user.id, keep_accessible=False)
        db.flush()
    remote_addr = _client_ip(request)
    if not has_plan:
        purge_user_before_delete(db, user, current_user)
        db.delete(user)
        db.commit()
        log_action(
            db,
            action="user_delete",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=remote_addr,
            details=f"deleted={deleted_username}",
            target_user_id=target_id,
        )
        admin_notify_service.send_user_delete(
            db,
            actor_username=current_user.username,
            target_name=deleted_username,
            client_timezone=get_client_timezone_from_request(request),
        )
        return deleted_username, False
    user.provision_state = "pending_deletion"
    user.panel_login_enabled = False
    user.is_active = False
    user.telegram_id = None
    user.token_version = (user.token_version or 0) + 1
    invalidate_user_sessions(db, user, reason="deleted", commit=False)
    active_web_session_service.revoke_user_sessions(db, user.username, commit=False)
    db.commit()
    enqueue_user_delete_cleanup(db, user_id=user.id, actor_username=current_user.username)
    log_action(
        db,
        action="user_delete",
        user_id=current_user.id,
        username=current_user.username,
        remote_addr=remote_addr,
        details=f"deleted={deleted_username}, pending_deletion",
        target_user_id=target_id,
    )
    admin_notify_service.send_user_delete(
        db,
        actor_username=current_user.username,
        target_name=deleted_username,
        client_timezone=get_client_timezone_from_request(request),
    )
    return deleted_username, True


def _suspend_notify_text(user: User) -> str:
    """Уведомление абоненту о приостановке: причина (если её можно показывать) и что делать."""
    lines = ["Доступ приостановлен администратором."]
    if user.suspend_reason_visible and user.suspend_reason:
        lines.append(f"Причина: {user.suspend_reason}")
    lines.append("Если это ошибка — напишите администратору.")
    return "\n".join(lines)


def _apply_bulk_action(db, user, payload, current_user, request) -> None:
    action = payload.action
    if action == "extend":
        new_until = compute_extended_access_until(get_user_access_until(user), payload.days or 0)
        set_user_access_until(db, user, new_until, actor=current_user.username)
    elif action == "suspend":
        if user.role == UserRole.admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя приостановить администратора"
            )
        user.suspended_at = datetime.now(timezone.utc).replace(tzinfo=None)
        user.suspend_reason = (payload.reason or "").strip() or None
        user.suspend_reason_visible = bool(payload.show_reason)
        db.commit()
        apply_user_block(db, user, "user_suspended", actor=current_user.username)
        if payload.notify_telegram and user.telegram_id:
            bot_token = _get_setting(db, "telegram_bot_token")
            if bot_token:
                send_tg_message(bot_token, user.telegram_id, _suspend_notify_text(user))
    elif action == "resume":
        user.suspended_at = None
        user.suspend_reason = None
        user.suspend_reason_visible = False
        db.commit()
        lift_user_block(db, user, "user_suspended", actor=current_user.username)
        if payload.notify_telegram and user.telegram_id:
            bot_token = _get_setting(db, "telegram_bot_token")
            if bot_token:
                send_tg_message(bot_token, user.telegram_id, "Доступ возобновлён.")
    elif action == "set_traffic_limit":
        if not get_feature_service().is_enabled("traffic_sync"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Для лимита трафика включите модуль «Синхронизация трафика» "
                    "в Настройках → Модули"
                ),
            )
        if "traffic_limit_bytes" not in payload.model_fields_set:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Укажите traffic_limit_bytes (или null)",
            )
        _set_user_traffic_limit(db, user, payload.traffic_limit_bytes, actor=current_user.username)
    elif action == "delete":
        _delete_user_core(db, user, current_user, request)
        return  # удаление само пишет историю с target_user_id
    _record_user_history(
        db, action=f"user_bulk_{action}", current_user=current_user, user=user, request=request
    )


@router.post("/bulk", response_model=BulkUsersResult)
def bulk_users(
    payload: BulkUsersRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if payload.action in ("extend", "suspend", "resume") and not get_feature_service().is_enabled(
        "user_provisioning"
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=module_disabled_message("user_provisioning")
        )
    failed: list[BulkUsersFailure] = []
    succeeded = 0
    for uid in payload.user_ids:
        user = db.get(User, uid)
        if user is None:
            failed.append(BulkUsersFailure(user_id=uid, username="", error="Пользователь не найден"))
            continue
        try:
            _apply_bulk_action(db, user, payload, current_user, request)
            succeeded += 1
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            failed.append(BulkUsersFailure(user_id=uid, username=user.username, error=detail))
        except Exception as exc:  # noqa: BLE001 — не прерывать остальных
            logger.exception("bulk users action=%s user=%s failed", payload.action, user.id)
            failed.append(BulkUsersFailure(user_id=uid, username=user.username, error=str(exc)))
    return BulkUsersResult(total=len(payload.user_ids), succeeded=succeeded, failed=failed)


@router.delete("/{user_id}", response_model=MessageResponse)
@tg_mini_token_allowed
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
    _name, pending = _delete_user_core(db, user, current_user, request)
    if pending:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "Удаление запущено"},
        )
    return MessageResponse(message="Пользователь удалён")
