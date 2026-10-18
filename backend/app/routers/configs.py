from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, tg_mini_token_allowed
from app.database import get_db
from app.models import AppSetting, User, UserRole, VpnConfig, VpnType
from app.schemas import (
    ConfigTagResponse,
    EffectiveVisibleVpnProfilesResponse,
    MessageResponse,
    SelfServiceQuotaResponse,
    VisibleVpnProfilesPolicy,
    VpnConfigCreate,
    VpnConfigHaInfo,
    VpnConfigResponse,
    VpnConfigUpdate,
)
from app.services.self_service import (
    awg2_ttl_for_actor,
    build_quota_payload,
    enforce_user_can_create_config,
    openvpn_cert_days_for_actor,
)
from app.services.client_portal import revoke_client_portal_links
from app.services.config_access import can_mutate_config, can_view_config, list_accessible_configs
from app.services.client_names import validate_new_client_name
from app.services.config_provisioning import deprovision_config, provision_config
from app.services.user_provisioning import is_in_plan_config, user_has_plan
from app.services.background_tasks import background_task_service
from app.services.config_csv_ops import (
    enqueue_config_csv_import,
    iter_config_export_csv,
    parse_import_csv,
    run_config_csv_import,
    should_import_async,
)
from app.services.config_tags import get_tags_for_configs, resolve_config_ids_by_tags
from app.services.feature_guards import get_feature_service, require_vpn_type
from app.services.node_adapter import NodeAdapter
from app.services.client_local_ip import build_client_local_ip_map
from app.services.config_import import format_config_disk_sync_message, import_clients_from_disk
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.client_sync import (
    maybe_replicate_cert_renew,
    maybe_replicate_config_metadata,
)
from app.services.node_sync.groups import (
    build_ha_metadata,
    find_sync_group_containing_node,
    find_sync_group_for_primary,
    require_ha_primary_for_client_ops,
)
from app.services.openvpn_cert import days_remaining_until, refresh_config_cert_expiry
from app.services.openvpn_profile_repair import recreate_openvpn_profiles_after_admin_change
from app.services.openvpn_group import (
    filter_openvpn_profile_files,
    list_openvpn_groups,
    set_user_openvpn_group,
)
from app.services.profile_delivery import load_node_remote_hosts, read_profile_file_for_delivery
from app.services.file_download import attachment_response
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.profile_files import profile_files_batch_key
from app.services.panel_publish_info import resolve_public_base_url
from app.services.qr_download import QrDownloadService
from app.services.qr_generator import generate_qr_png, prefers_download_link_qr
from app.services.security import SecurityService
from app.services.vpn_profile_visibility import (
    POLICY_GROUP_TO_SETTING,
    allowed_openvpn_group_options,
    allowed_openvpn_groups,
    enforce_can_create_vpn_type,
    filter_profile_files,
    parse_user_visible_vpn_profiles,
    profile_file_allowed,
    resolve_effective_visible_vpn_profiles,
    resolve_openvpn_group_for_user,
)

router = APIRouter(prefix="/configs", tags=["configs"])

PROFILE_FILES_MAX_WORKERS = 12


def _local_ip_for_config(db: Session, config: VpnConfig, adapter: NodeAdapter | None = None) -> str | None:
    try:
        node_adapter = adapter or get_active_adapter(db)
        active = get_active_node(db)
        mapping = build_client_local_ip_map(
            node_adapter,
            db,
            node_id=active.id,
            configs=[config],
        )
        return mapping.get(config.client_name.strip().lower())
    except Exception:
        return None


def _qr_download_service(db: Session, request: Request) -> QrDownloadService:
    sec = SecurityService().get_settings(db)
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    from app.services.client_portal import resolve_portal_base_url

    base_url = resolve_portal_base_url(db) or resolve_public_base_url(request)
    return QrDownloadService(
        db,
        base_url=base_url,
        ttl_seconds=sec["qr_download_ttl_seconds"],
        max_downloads=sec["qr_download_max_downloads"],
        pin=pin_row.value if pin_row else "",
    )


def _active_node_id(db: Session) -> int:
    return get_active_node(db).id


def _scoped_config_query(db: Session, query=None):
    active_node = get_active_node(db)
    group, _role = find_sync_group_containing_node(db, active_node.id)
    base = query if query is not None else db.query(VpnConfig)
    if group:
        return base.filter(
            VpnConfig.node_id == group.primary_node_id,
            VpnConfig.ha_primary_config_id.is_(None),
        )
    return base.filter(
        VpnConfig.node_id == active_node.id,
        VpnConfig.ha_primary_config_id.is_(None),
    )


def _get_config_for_active_node(db: Session, config_id: int) -> VpnConfig | None:
    config = db.get(VpnConfig, config_id)
    if not config or config.ha_primary_config_id is not None:
        return None
    active_node = get_active_node(db)
    group, _role = find_sync_group_containing_node(db, active_node.id)
    if group:
        if config.node_id == group.primary_node_id:
            return config
        return None
    if config.node_id == active_node.id:
        return config
    return None


def _ha_info_for_config(db: Session, config: VpnConfig) -> VpnConfigHaInfo | None:
    if not config.sync_group_id:
        return None
    from app.models import NodeSyncGroup

    group = db.get(NodeSyncGroup, config.sync_group_id)
    meta = build_ha_metadata(group)
    if not meta:
        return None
    return VpnConfigHaInfo(**meta)


def _can_access_config(user: User, config: VpnConfig, db: Session | None = None) -> bool:
    """View access: owned ∪ whitelist (admin unrestricted)."""
    if db is None:
        if user.role == UserRole.admin:
            return True
        return config.owner_id == user.id
    return can_view_config(user, config, db)


def _can_mutate_config(user: User, config: VpnConfig) -> bool:
    return can_mutate_config(user, config)


def _raise_if_cannot_mutate(user: User, config: VpnConfig) -> None:
    if _can_mutate_config(user, config):
        return
    if (
        user.role == UserRole.user
        and config.owner_id == user.id
        and not bool(getattr(user, "can_manage_configs", False))
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Управление конфигурациями отключено администратором",
        )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


def _to_response(
    config: VpnConfig,
    db: Session,
    include_files: bool = False,
    *,
    openvpn_group: str | None = None,
    adapter: NodeAdapter | None = None,
    profile_files: list[dict[str, str]] | None = None,
    tags: list[ConfigTagResponse] | None = None,
    ha_replicate_warning: str | None = None,
    visibility_policy: dict | None = None,
    local_ip: str | None = None,
    viewer: User | None = None,
) -> VpnConfigResponse:
    owner = db.query(User).filter(User.id == config.owner_id).first()
    # C7: owner id/username only for admin or the owner (grantee sees neither).
    # No viewer (internal callers) → keep fields; API paths always pass current_user.
    show_owner = viewer is None or (
        viewer.role == UserRole.admin or (owner is not None and owner.id == viewer.id)
    )
    files: list[dict[str, str]] = []
    if include_files:
        if profile_files is not None:
            files = profile_files
        else:
            node_adapter = adapter or get_active_adapter(db)
            files = node_adapter.get_profile_files(config.client_name, config.vpn_type)
        if config.vpn_type == VpnType.openvpn and openvpn_group:
            files = filter_openvpn_profile_files(files, openvpn_group)
        if visibility_policy is not None:
            files = filter_profile_files(files, visibility_policy)
        if files:
            files = enrich_profile_files(config.client_name, files)
    return VpnConfigResponse(
        id=config.id,
        client_name=config.client_name,
        vpn_type=config.vpn_type,
        owner_id=config.owner_id if show_owner else None,
        owner_username=(owner.username if owner else None) if show_owner else None,
        cert_expire_days=config.cert_expire_days,
        cert_expires_at=config.cert_expires_at,
        expires_at=config.expires_at,
        cert_days_left=days_remaining_until(config.cert_expires_at),
        description=config.description,
        created_at=config.created_at,
        updated_at=config.updated_at,
        profile_files=files,
        tags=tags or [],
        ha=_ha_info_for_config(db, config),
        ha_replicate_warning=ha_replicate_warning,
        local_ip=local_ip,
    )


def _list_accessible_configs(db: Session, current_user: User) -> list[VpnConfig]:
    query = _scoped_config_query(db)
    return list_accessible_configs(db, current_user, query)


def _fetch_profile_files_map(
    adapter: NodeAdapter,
    configs: list[VpnConfig],
    *,
    openvpn_group: str | None = None,
    visibility_policy: dict | None = None,
) -> dict[int, list[dict[str, str]]]:
    if not configs:
        return {}

    clients = [(c.client_name, c.vpn_type) for c in configs]
    files_by_key: dict[str, list[dict[str, str]]] = {}
    try:
        files_by_key = adapter.get_profile_files_batch(clients)
    except Exception:
        files_by_key = {}

    missing = [
        c
        for c in configs
        if profile_files_batch_key(c.client_name, c.vpn_type) not in files_by_key
    ]
    if missing:
        with ThreadPoolExecutor(max_workers=PROFILE_FILES_MAX_WORKERS) as pool:
            futures = {
                pool.submit(adapter.get_profile_files, c.client_name, c.vpn_type): c
                for c in missing
            }
            for future in as_completed(futures):
                config = futures[future]
                key = profile_files_batch_key(config.client_name, config.vpn_type)
                try:
                    files_by_key[key] = future.result()
                except Exception:
                    files_by_key[key] = []

    result: dict[int, list[dict[str, str]]] = {}
    for config in configs:
        key = profile_files_batch_key(config.client_name, config.vpn_type)
        files = list(files_by_key.get(key, []))
        if config.vpn_type == VpnType.openvpn and openvpn_group:
            files = filter_openvpn_profile_files(files, openvpn_group)
        if visibility_policy is not None:
            files = filter_profile_files(files, visibility_policy)
        result[config.id] = enrich_profile_files(config.client_name, files)
    return result


def _viewer_visibility_policy(db: Session, current_user: User) -> dict:
    return resolve_effective_visible_vpn_profiles(db, current_user)


def _require_profile_path_allowed(
    db: Session,
    current_user: User,
    config: VpnConfig,
    path: str,
    *,
    adapter: NodeAdapter | None = None,
) -> None:
    if current_user.role == UserRole.admin:
        return
    node_adapter = adapter or get_active_adapter(db)
    files = node_adapter.get_profile_files(config.client_name, config.vpn_type)
    match = next((item for item in files if item.get("path") == path), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Файл профиля недоступен")
    policy = _viewer_visibility_policy(db, current_user)
    if not profile_file_allowed(
        policy,
        protocol=match.get("protocol", ""),
        variant=match.get("variant", ""),
        path=match.get("path", path),
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Файл профиля недоступен")


@router.get("/quota", response_model=SelfServiceQuotaResponse)
@tg_mini_token_allowed
def get_config_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfServiceQuotaResponse(**build_quota_payload(db, current_user))


@router.get("/visible-vpn-profiles", response_model=EffectiveVisibleVpnProfilesResponse)
def get_visible_vpn_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    inherited = (
        current_user.role == UserRole.admin
        or parse_user_visible_vpn_profiles(getattr(current_user, "visible_vpn_profiles", None)) is None
    )
    return EffectiveVisibleVpnProfilesResponse(
        policy=VisibleVpnProfilesPolicy(**policy),
        inherited=inherited,
    )


@router.get("", response_model=list[VpnConfigResponse])
def list_configs(
    include_files: bool = Query(False, description="Загружать список файлов профилей с узла"),
    tag_ids: list[int] = Query(default=[], description="Фильтр по тегам (OR)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visibility_policy = _viewer_visibility_policy(db, current_user)
    openvpn_group = resolve_openvpn_group_for_user(db, current_user)
    configs = _list_accessible_configs(db, current_user)
    if tag_ids:
        node_id = _active_node_id(db)
        allowed_ids = {c.id for c in configs}
        matched = set(resolve_config_ids_by_tags(db, node_id, tag_ids))
        configs = [c for c in configs if c.id in matched and c.id in allowed_ids]
    adapter = get_active_adapter(db) if include_files else None
    files_map: dict[int, list[dict[str, str]]] = {}
    if include_files and adapter is not None and configs:
        files_map = _fetch_profile_files_map(
            adapter,
            configs,
            openvpn_group=openvpn_group,
            visibility_policy=visibility_policy,
        )
    tags_map = get_tags_for_configs(db, [c.id for c in configs]) if configs else {}
    local_ip_map: dict[str, str] = {}
    if configs:
        try:
            ip_adapter = adapter or get_active_adapter(db)
            active = get_active_node(db)
            local_ip_map = build_client_local_ip_map(
                ip_adapter,
                db,
                node_id=active.id,
                configs=configs,
            )
        except Exception:
            local_ip_map = {}
    return [
        _to_response(
            c,
            db,
            include_files=include_files,
            openvpn_group=openvpn_group,
            adapter=adapter,
            profile_files=files_map.get(c.id) if include_files else None,
            visibility_policy=visibility_policy,
            tags=[
                ConfigTagResponse(id=t.id, name=t.name, color=t.color)
                for t in tags_map.get(c.id, [])
            ],
            local_ip=local_ip_map.get(c.client_name.strip().lower()),
            viewer=current_user,
        )
        for c in configs
    ]


@router.get("/profile-files")
def list_profile_files(
    ids: str = Query("", description="ID конфигураций через запятую; пусто — все доступные"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    visibility_policy = _viewer_visibility_policy(db, current_user)
    openvpn_group = resolve_openvpn_group_for_user(db, current_user)
    configs = _list_accessible_configs(db, current_user)
    if ids.strip():
        try:
            id_set = {int(part.strip()) for part in ids.split(",") if part.strip()}
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ids должен содержать целые числа через запятую",
            ) from exc
        configs = [c for c in configs if c.id in id_set]

    adapter = get_active_adapter(db)
    files_map = _fetch_profile_files_map(
        adapter,
        configs,
        openvpn_group=openvpn_group,
        visibility_policy=visibility_policy,
    )
    return {str(config_id): files for config_id, files in files_map.items()}


class OpenVpnGroupUpdate(BaseModel):
    group: str


@router.get("/openvpn-group")
def get_openvpn_group(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    group = resolve_openvpn_group_for_user(db, current_user)
    if current_user.role == UserRole.admin:
        options = list_openvpn_groups()
    else:
        options = [{"key": o["key"], "label": o["label"]} for o in allowed_openvpn_group_options(policy)]
    return {
        "group": group,
        "options": options,
    }


@router.put("/openvpn-group")
def put_openvpn_group(
    payload: OpenVpnGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    policy = resolve_effective_visible_vpn_profiles(db, current_user)
    if current_user.role != UserRole.admin:
        allowed = {POLICY_GROUP_TO_SETTING[k] for k in allowed_openvpn_groups(policy)}
        if payload.group not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Выбранная группа OpenVPN недоступна по политике видимости",
            )
    group = set_user_openvpn_group(db, current_user.id, payload.group)
    if current_user.role == UserRole.admin:
        options = list_openvpn_groups()
    else:
        options = [{"key": o["key"], "label": o["label"]} for o in allowed_openvpn_group_options(policy)]
    return {"group": group, "options": options}


@router.get("/export")
def export_configs_csv(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node_id = _active_node_id(db)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"vpn-configs-node{node_id}-{stamp}.csv"
    return StreamingResponse(
        iter_config_export_csv(db, node_id=node_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_configs_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    require_ha_primary_for_client_ops(db)
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл пуст")
    try:
        rows = parse_import_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if should_import_async(len(rows)):
        task_id = enqueue_config_csv_import(db, rows=rows, actor=admin)
        task = background_task_service.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось создать задачу")
        return background_task_service.build_accepted_payload(
            task,
            f"Импорт {len(rows)} клиент(ов) поставлен в очередь",
        )

    result = run_config_csv_import(
        rows=rows,
        actor_username=admin.username,
        default_owner_id=admin.id,
    )
    return {"success": True, "async": False, "message": result["message"], "result": json.loads(result["output"])}


@router.post("", response_model=VpnConfigResponse, status_code=status.HTTP_201_CREATED)
@tg_mini_token_allowed
def create_config(
    payload: VpnConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # D3: пользователь с планом создаёт конфиги только через «Мои конфиги»
    # (Mini App / /me/plan-configs) или через администратора.
    if current_user.role != UserRole.admin and user_has_plan(current_user):
        provisioning_enabled = get_feature_service().is_enabled("user_provisioning")
        if provisioning_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Добавьте конфиг через Мои конфиги или запросите у админа",
            )
    enforce_user_can_create_config(db, current_user)
    require_ha_primary_for_client_ops(db)
    owner_id = payload.owner_id if current_user.role == UserRole.admin and payload.owner_id else current_user.id
    owner = db.query(User).filter(User.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Владелец не найден")

    node_id = _active_node_id(db)
    existing = (
        db.query(VpnConfig)
        .filter(
            VpnConfig.node_id == node_id,
            VpnConfig.client_name == payload.client_name,
            VpnConfig.vpn_type == payload.vpn_type,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Конфигурация уже существует")
    try:
        validate_new_client_name(
            db, node_id=node_id, client_name=payload.client_name, owner_id=owner_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    require_vpn_type(payload.vpn_type.value, service=get_feature_service())
    enforce_can_create_vpn_type(db, current_user, payload.vpn_type)
    cert_days = openvpn_cert_days_for_actor(current_user, payload.cert_expire_days)
    ttl = awg2_ttl_for_actor(current_user, payload.ttl)

    node = get_active_node(db)
    adapter = get_active_adapter(db)
    try:
        config, ha_replicate_warning = provision_config(
            db,
            node=node,
            client_name=payload.client_name,
            vpn_type=payload.vpn_type,
            owner=owner,
            actor=current_user,
            notify=True,
            cert_expire_days=cert_days if payload.vpn_type == VpnType.openvpn else payload.cert_expire_days,
            ttl=ttl,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _to_response(
        config,
        db,
        include_files=True,
        adapter=adapter,
        ha_replicate_warning=ha_replicate_warning,
        visibility_policy=_viewer_visibility_policy(db, current_user),
        openvpn_group=resolve_openvpn_group_for_user(db, current_user),
        local_ip=_local_ip_for_config(db, config, adapter),
        viewer=current_user,
    )


@router.get("/{config_id}", response_model=VpnConfigResponse)
@tg_mini_token_allowed
def get_config(
    config_id: int,
    include_files: bool = Query(True, description="Загружать список файлов профилей с узла"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    return _to_response(
        config,
        db,
        include_files=include_files,
        visibility_policy=_viewer_visibility_policy(db, current_user),
        openvpn_group=resolve_openvpn_group_for_user(db, current_user),
        local_ip=_local_ip_for_config(db, config),
        viewer=current_user,
    )


@router.patch("/{config_id}", response_model=VpnConfigResponse)
@tg_mini_token_allowed
def update_config(
    config_id: int,
    payload: VpnConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if current_user.role != UserRole.admin and is_in_plan_config(db, current_user, config):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Конфиг из плана нельзя менять напрямую — удалите конфиг целиком в Мои конфиги или обратитесь к администратору",
        )
    _raise_if_cannot_mutate(current_user, config)

    require_ha_primary_for_client_ops(db)

    metadata_changed = False
    cert_renewed = False
    renewed_days: int | None = None

    if payload.description is not None:
        config.description = payload.description
        metadata_changed = True
    if payload.owner_id is not None:
        if current_user.role != UserRole.admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Только администратор может менять владельца")
        owner = db.query(User).filter(User.id == payload.owner_id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Владелец не найден")
        previous_owner_id = config.owner_id
        config.owner_id = payload.owner_id
        if previous_owner_id != payload.owner_id:
            revoke_client_portal_links(db, node_id=config.node_id, client_name=config.client_name)
        metadata_changed = True
    if payload.cert_expire_days is not None and config.vpn_type == VpnType.openvpn:
        adapter = get_active_adapter(db)
        days = openvpn_cert_days_for_actor(current_user, payload.cert_expire_days)
        adapter.add_openvpn_client(config.client_name, days)
        recreate_openvpn_profiles_after_admin_change(
            adapter,
            client_names=[config.client_name],
            hosts=load_node_remote_hosts(db, config.node_id),
        )
        config.cert_expire_days = days
        refresh_config_cert_expiry(config, adapter)
        cert_renewed = True
        renewed_days = days

    db.commit()
    db.refresh(config)

    node = get_active_node(db)
    if cert_renewed and renewed_days is not None:
        maybe_replicate_cert_renew(
            db,
            node_id=node.id,
            primary_config=config,
            cert_expire_days=renewed_days,
        )
    if metadata_changed:
        maybe_replicate_config_metadata(db, node_id=node.id, primary_config=config)

    return _to_response(
        config,
        db,
        include_files=True,
        visibility_policy=_viewer_visibility_policy(db, current_user),
        openvpn_group=resolve_openvpn_group_for_user(db, current_user),
        local_ip=_local_ip_for_config(db, config),
        viewer=current_user,
    )


@router.delete("/{config_id}", response_model=MessageResponse)
@tg_mini_token_allowed
def delete_config(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if current_user.role != UserRole.admin and is_in_plan_config(db, current_user, config):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Конфиг из плана нельзя удалять напрямую — удалите конфиг целиком в Мои конфиги или обратитесь к администратору",
        )
    _raise_if_cannot_mutate(current_user, config)

    require_ha_primary_for_client_ops(db)
    client_name = config.client_name
    owner = db.get(User, config.owner_id)
    was_in_plan = owner is not None and is_in_plan_config(db, owner, config)
    deprovision_config(db, config=config, actor=current_user, notify=True, request=request)
    if was_in_plan:
        owner.provision_state = "pending"
        db.commit()
    return MessageResponse(message=f"Клиент '{client_name}' удалён")


@router.get("/{config_id}/download")
def download_profile(
    config_id: int,
    path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")

    adapter = get_active_adapter(db)
    _require_profile_path_allowed(db, current_user, config, path, adapter=adapter)
    hosts = load_node_remote_hosts(db, config.node_id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    filename = build_profile_download_filename(config.client_name, path=path)
    return attachment_response(content, filename)


@router.get("/{config_id}/qr")
def generate_qr(
    config_id: int,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")

    adapter = get_active_adapter(db)
    _require_profile_path_allowed(db, current_user, config, path, adapter=adapter)
    hosts = load_node_remote_hosts(db, config.node_id)
    content = read_profile_file_for_delivery(adapter, path, hosts)
    if prefers_download_link_qr(path=path, content=content):
        link = _qr_download_service(db, request).create_token(
            file_path=path,
            config_type=config.vpn_type.value,
            config_name=build_profile_download_filename(config.client_name, path=path),
            node_id=config.node_id,
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


@router.post("/{config_id}/one-time-link")
def create_one_time_link(
    config_id: int,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config or not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    _require_profile_path_allowed(db, current_user, config, path)
    return _qr_download_service(db, request).create_token(
        file_path=path,
        config_type=config.vpn_type.value,
        config_name=build_profile_download_filename(config.client_name, path=path),
        node_id=config.node_id,
        creator_id=current_user.id,
        creator_username=current_user.username,
        remote_addr=request.client.host if request.client else None,
    )


@router.post("/sync", response_model=MessageResponse)
def sync_from_antizapret(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Синхронизация клиентов AntiZapret с базой данных (импорт с диска и удаление устаревших записей)."""
    require_ha_primary_for_client_ops(db)
    admin = db.query(User).filter(User.role == UserRole.admin).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Администратор не найден")

    result = import_clients_from_disk(db, get_active_node(db), admin.id)
    return MessageResponse(message=format_config_disk_sync_message(result))
