import json
import secrets
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_password_hash, require_admin, tg_mini_token_allowed
from app.config import get_settings
from app.database import get_db
from app.models import (
    BackgroundTask,
    ClientPortalToken,
    Node,
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
from app.schemas import (
    MessageResponse,
    ProvisionPlanItem,
    ProvisionPlanResponse,
    ProvisioningConfig,
    ProvisioningConfigNode,
    UserConfigAccessResponse,
    UserConfigAccessUpdate,
    UserCreate,
    UserProvisionSummary,
    UserProvisionedCreate,
    UserProvisionedResponse,
    UserProvisioningApply,
    UserProvisioningCard,
    UserProvisioningDesired,
    UserProvisioningSuggested,
    UserProvisioningUpdate,
    UserResponse,
    UserUpdate,
)
from app.services.action_log import log_action
from app.services.admin_notify import admin_notify_service
from app.services.active_web_session import active_web_session_service
from app.services.background_tasks import background_task_service
from app.services.client_names import (
    assert_client_base_name_valid,
    assert_name_not_reserved_by_other_user,
    names_under_base,
    parse_plan_indexes,
)
from app.services.client_portal import revoke_creator_portal_links
from app.services.config_access import get_user_config_grants, set_user_config_access
from app.services.ip_restriction import ip_restriction_service
from app.services.notify_time import get_client_timezone_from_request
from app.services.user_provisioning import (
    TASK_TYPE,
    compute_plan,
    enqueue_user_provision,
    prefill_for_unmanaged,
    recompute_provision_state,
    user_has_plan,
    validate_plan_nodes,
)
from app.services.admin_bootstrap import (
    scrub_admin_bootstrap_secret_from_env,
    should_scrub_env_after_password_change,
)
from app.services.password_policy import validate_password
from app.services.refresh_token import invalidate_user_sessions
from app.services.self_service import password_change_required_on_admin_set
from app.services.telegram_link import notify_telegram_unlinked
from app.services.user_subscription import (
    get_user_access_until,
    normalize_access_until,
    set_user_access_until,
)
from app.services.vpn_profile_visibility import normalize_policy, policy_to_json

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


def _user_summary(user: User, node_ids: list[int]) -> UserProvisionSummary:
    return UserProvisionSummary(
        id=user.id,
        username=user.username,
        role=user.role.value,
        client_base_name=user.client_base_name,
        plan_config_indexes=parse_plan_indexes(user.plan_config_indexes),
        desired_protocols=_desired_protocols_list(user.desired_protocols),
        panel_login_enabled=user.panel_login_enabled,
        provision_state=user.provision_state,
        access_until=user.access_until,
        node_ids=list(node_ids),
        config_quota=user.config_quota,
    )


def _purge_user_before_delete(db: Session, user: User, successor: User) -> None:
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


@router.get("", response_model=list[UserResponse])
@tg_mini_token_allowed
def list_users(
    role: str | None = None,
    q: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(User).filter(User.provision_state != "pending_deletion")
    if role:
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            pass  # неизвестное значение фильтра — игнорируем
    if q:
        query = query.filter(User.username.ilike(f"%{q}%"))
    if state:
        query = query.filter(User.provision_state == state)
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

    for user in users:
        node_ids = nodes_by_user.get(user.id, [])
        user.plan_node_ids = node_ids
        user.plan_protocols = _desired_protocols_list(user.desired_protocols)
        user.plan_config_count = len(parse_plan_indexes(user.plan_config_indexes))
        user.active_task_id = active_task_by_user.get(user.id)
    return users


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.query(User).filter(User.username == payload.username).first():
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
def create_provisioned_user(
    payload: UserProvisionedCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Создать абонента (role=user) с планом конфигов и сразу поставить задачу применения."""
    if db.query(User).filter(User.username == payload.username).first():
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
        telegram_id=payload.telegram_id or None,
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


@router.patch("/{user_id}", response_model=UserResponse)
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

    old_telegram_id = user.telegram_id
    access_until_updated = False
    pending_access_until = None

    if payload.role is not None:
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять роль")
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
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять статус")
        if user.is_active and not payload.is_active:
            invalidate_user_sessions(db, user, reason="disabled", commit=False)
            active_web_session_service.revoke_user_sessions(db, user.username, commit=False)
        user.is_active = payload.is_active
    if "panel_login_enabled" in payload.model_fields_set:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять вход в панель",
            )
        if payload.panel_login_enabled is False and user.panel_login_enabled:
            # Existing access/refresh sessions stop working: token_version bumps all JWTs,
            # revoke_user_sessions ends the active web sessions.
            user.token_version = (user.token_version or 0) + 1
            active_web_session_service.revoke_user_sessions(db, user.username, commit=False)
        user.panel_login_enabled = payload.panel_login_enabled
    if "access_until" in payload.model_fields_set:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять срок доступа",
            )
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
            existing = db.query(User).filter(User.telegram_id == tg_id, User.id != user.id).first()
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
        if not is_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять квоту")
        user.config_quota = payload.config_quota
    if payload.can_create_configs is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять право создания конфигов",
            )
        user.can_create_configs = payload.can_create_configs
    if payload.can_manage_configs is not None:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять право управления конфигами",
            )
        user.can_manage_configs = payload.can_manage_configs
    if "visible_vpn_profiles" in payload.model_fields_set:
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только администратор может менять видимость VPN-профилей",
            )
        if payload.visible_vpn_profiles is None:
            user.visible_vpn_profiles = None
        else:
            normalized = normalize_policy(payload.visible_vpn_profiles, strict=True)
            user.visible_vpn_profiles = policy_to_json(normalized)

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
    if payload.telegram_id is not None:
        notify_telegram_unlinked(
            db,
            old_telegram_id=old_telegram_id,
            new_telegram_id=user.telegram_id,
            username=user.username,
        )
    if payload.password and should_scrub_env_after_password_change(user.username):
        scrub_admin_bootstrap_secret_from_env()
    if settings.audit_log_enabled and (
        payload.password
        or payload.role is not None
        or payload.is_active is not None
        or access_until_updated
    ):
        log_action(
            db,
            action="user_update",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"target={user.username}",
        )
    response = UserResponse.model_validate(user)
    if cascade_warning:
        response.access_cascade_warning = cascade_warning
    return response


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
    db: Session, user: User, base: str | None, node_ids: list[int]
) -> list[ProvisioningConfig]:
    query = db.query(VpnConfig).filter(VpnConfig.owner_id == user.id)
    if node_ids:
        query = query.filter(VpnConfig.node_id.in_(node_ids))
    configs = query.all()
    namespace = names_under_base(base) if base else None
    labels = {node.id: node.name for node in db.query(Node).filter(Node.id.in_(node_ids)).all()} if node_ids else {}
    by_name: dict[str, list[dict]] = defaultdict(list)
    for config in configs:
        if namespace is not None and (config.client_name or "").lower() not in namespace:
            continue
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

    return UserProvisioningCard(
        user=_user_summary(user, node_ids),
        has_plan=has_plan,
        desired=desired,
        suggested=suggested,
        plan=serialized_plan,
        configs=_group_provision_configs(db, user, base, node_ids),
        last_task=_last_provision_task(db, user.id),
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

    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_provision_update",
            user_id=admin.id,
            username=admin.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
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


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нельзя удалить себя")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
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
    if user.role != UserRole.admin:
        revoke_creator_portal_links(db, user.id, keep_accessible=False)
        db.flush()
    _purge_user_before_delete(db, user, current_user)
    db.delete(user)
    db.commit()
    if settings.audit_log_enabled:
        log_action(
            db,
            action="user_delete",
            user_id=current_user.id,
            username=current_user.username,
            remote_addr=ip_restriction_service.get_client_ip(request),
            details=f"deleted={deleted_username}",
        )
    admin_notify_service.send_user_delete(
        db,
        actor_username=current_user.username,
        target_name=deleted_username,
        client_timezone=get_client_timezone_from_request(request),
    )
    return MessageResponse(message="Пользователь удалён")
