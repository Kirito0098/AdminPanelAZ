from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import AppSetting, User, UserRole, ViewerConfigAccess, VpnConfig, VpnType
from app.schemas import ConfigTagResponse, MessageResponse, SelfServiceQuotaResponse, VpnConfigCreate, VpnConfigHaInfo, VpnConfigResponse, VpnConfigUpdate
from app.services.self_service import build_quota_payload, enforce_user_can_create_config
from app.services.admin_notify import admin_notify_service
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
from app.services.config_import import format_config_disk_sync_message, import_clients_from_disk
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.node_sync.client_sync import (
    maybe_replicate_cert_renew,
    maybe_replicate_create,
    maybe_replicate_delete,
    maybe_replicate_config_metadata,
    purge_ha_shadow_configs,
)
from app.services.node_sync.groups import (
    build_ha_metadata,
    find_sync_group_containing_node,
    find_sync_group_for_primary,
    require_ha_primary_for_client_ops,
)
from app.services.openvpn_cert import resolve_openvpn_cert_days_remaining
from app.services.openvpn_group import (
    filter_openvpn_profile_files,
    get_user_openvpn_group,
    list_openvpn_groups,
    set_user_openvpn_group,
)
from app.services.notify_time import get_client_timezone_from_request
from app.services.profile_download_name import build_profile_download_filename, enrich_profile_files
from app.services.profile_files import profile_files_batch_key
from app.services.panel_publish_info import resolve_public_base_url
from app.services.qr_download import QrDownloadService
from app.services.qr_generator import generate_qr_png
from app.services.security import SecurityService

router = APIRouter(prefix="/configs", tags=["configs"])

PROFILE_FILES_MAX_WORKERS = 12


def _qr_download_service(db: Session, request: Request) -> QrDownloadService:
    sec = SecurityService().get_settings(db)
    pin_row = db.query(AppSetting).filter(AppSetting.key == "qr_download_pin").first()
    base_url = resolve_public_base_url(request)
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
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.viewer and db is not None:
        grants = db.query(ViewerConfigAccess).filter_by(user_id=user.id).all()
        if grants:
            groups = {g.config_group.lower() for g in grants}
            return config.client_name.lower() in groups or any(
                config.client_name.lower().startswith(g) for g in groups
            )
        return False
    return config.owner_id == user.id


def _fill_missing_cert_expire_days(configs: list[VpnConfig], db: Session, adapter: NodeAdapter | None = None) -> None:
    node_adapter = adapter or get_active_adapter(db)
    dirty = False
    for config in configs:
        if config.vpn_type != VpnType.openvpn or config.cert_expire_days is not None:
            continue
        days = resolve_openvpn_cert_days_remaining(node_adapter, config.client_name)
        if days is not None:
            config.cert_expire_days = days
            dirty = True
    if dirty:
        db.commit()


def _to_response(
    config: VpnConfig,
    db: Session,
    include_files: bool = False,
    *,
    openvpn_group: str | None = None,
    adapter: NodeAdapter | None = None,
    profile_files: list[dict[str, str]] | None = None,
    tags: list[ConfigTagResponse] | None = None,
) -> VpnConfigResponse:
    owner = db.query(User).filter(User.id == config.owner_id).first()
    files: list[dict[str, str]] = []
    if include_files:
        if profile_files is not None:
            files = profile_files
        else:
            node_adapter = adapter or get_active_adapter(db)
            files = node_adapter.get_profile_files(config.client_name, config.vpn_type)
        if config.vpn_type == VpnType.openvpn and openvpn_group:
            files = filter_openvpn_profile_files(files, openvpn_group)
        if files:
            files = enrich_profile_files(config.client_name, files)
    return VpnConfigResponse(
        id=config.id,
        client_name=config.client_name,
        vpn_type=config.vpn_type,
        owner_id=config.owner_id,
        owner_username=owner.username if owner else None,
        cert_expire_days=config.cert_expire_days,
        description=config.description,
        created_at=config.created_at,
        updated_at=config.updated_at,
        profile_files=files,
        tags=tags or [],
        ha=_ha_info_for_config(db, config),
    )


def _list_accessible_configs(db: Session, current_user: User) -> list[VpnConfig]:
    query = _scoped_config_query(db)
    if current_user.role == UserRole.viewer:
        grants = db.query(ViewerConfigAccess).filter_by(user_id=current_user.id).all()
        if not grants:
            return []
        configs = query.order_by(VpnConfig.created_at.desc()).all()
        return [c for c in configs if _can_access_config(current_user, c, db)]
    if current_user.role != UserRole.admin:
        query = query.filter(VpnConfig.owner_id == current_user.id)
    return query.order_by(VpnConfig.created_at.desc()).all()


def _fetch_profile_files_map(
    adapter: NodeAdapter,
    configs: list[VpnConfig],
    *,
    openvpn_group: str | None = None,
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
        result[config.id] = enrich_profile_files(config.client_name, files)
    return result


@router.get("/quota", response_model=SelfServiceQuotaResponse)
def get_config_quota(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SelfServiceQuotaResponse(**build_quota_payload(db, current_user))


@router.get("", response_model=list[VpnConfigResponse])
def list_configs(
    include_files: bool = Query(False, description="Загружать список файлов профилей с узла"),
    tag_ids: list[int] = Query(default=[], description="Фильтр по тегам (OR)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    openvpn_group = get_user_openvpn_group(db, current_user.id)
    configs = _list_accessible_configs(db, current_user)
    if tag_ids:
        node_id = _active_node_id(db)
        allowed_ids = {c.id for c in configs}
        matched = set(resolve_config_ids_by_tags(db, node_id, tag_ids))
        configs = [c for c in configs if c.id in matched and c.id in allowed_ids]
    adapter = get_active_adapter(db) if include_files else None
    files_map: dict[int, list[dict[str, str]]] = {}
    if include_files and adapter is not None and configs:
        files_map = _fetch_profile_files_map(adapter, configs, openvpn_group=openvpn_group)
    tags_map = get_tags_for_configs(db, [c.id for c in configs]) if configs else {}
    return [
        _to_response(
            c,
            db,
            include_files=include_files,
            openvpn_group=openvpn_group,
            adapter=adapter,
            profile_files=files_map.get(c.id) if include_files else None,
            tags=[
                ConfigTagResponse(id=t.id, name=t.name, color=t.color)
                for t in tags_map.get(c.id, [])
            ],
        )
        for c in configs
    ]


@router.get("/profile-files")
def list_profile_files(
    ids: str = Query("", description="ID конфигураций через запятую; пусто — все доступные"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    openvpn_group = get_user_openvpn_group(db, current_user.id)
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
    files_map = _fetch_profile_files_map(adapter, configs, openvpn_group=openvpn_group)
    return {str(config_id): files for config_id, files in files_map.items()}


class OpenVpnGroupUpdate(BaseModel):
    group: str


@router.get("/openvpn-group")
def get_openvpn_group(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {
        "group": get_user_openvpn_group(db, current_user.id),
        "options": list_openvpn_groups(),
    }


@router.put("/openvpn-group")
def put_openvpn_group(
    payload: OpenVpnGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = set_user_openvpn_group(db, current_user.id, payload.group)
    return {"group": group, "options": list_openvpn_groups()}


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
async def import_configs_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    require_ha_primary_for_client_ops(db)
    content = await file.read()
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
def create_config(
    payload: VpnConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    require_vpn_type(payload.vpn_type.value, service=get_feature_service())

    adapter = get_active_adapter(db)
    if payload.vpn_type == VpnType.openvpn:
        adapter.add_openvpn_client(payload.client_name, payload.cert_expire_days or 3650)
    else:
        adapter.add_wireguard_client(payload.client_name)

    config = VpnConfig(
        node_id=node_id,
        client_name=payload.client_name,
        vpn_type=payload.vpn_type,
        owner_id=owner_id,
        cert_expire_days=payload.cert_expire_days,
        description=payload.description,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    group = find_sync_group_for_primary(db, node_id)
    if group:
        maybe_replicate_create(db, node_id=node_id, primary_config=config)

    node = get_active_node(db)
    admin_notify_service.send_config_create(
        db,
        actor_username=current_user.username,
        target_name=config.client_name,
        target_type=config.vpn_type.value,
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )
    return _to_response(config, db, include_files=True, adapter=adapter)


@router.get("/{config_id}", response_model=VpnConfigResponse)
def get_config(
    config_id: int,
    include_files: bool = Query(True, description="Загружать список файлов профилей с узла"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return _to_response(config, db, include_files=include_files)


@router.patch("/{config_id}", response_model=VpnConfigResponse)
def update_config(
    config_id: int,
    payload: VpnConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

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
        config.owner_id = payload.owner_id
        metadata_changed = True
    if payload.cert_expire_days is not None and config.vpn_type == VpnType.openvpn:
        get_active_adapter(db).add_openvpn_client(config.client_name, payload.cert_expire_days)
        config.cert_expire_days = payload.cert_expire_days
        cert_renewed = True
        renewed_days = payload.cert_expire_days

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

    return _to_response(config, db, include_files=True)


@router.delete("/{config_id}", response_model=MessageResponse)
def delete_config(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    require_ha_primary_for_client_ops(db)
    adapter = get_active_adapter(db)
    if config.vpn_type == VpnType.openvpn:
        adapter.delete_openvpn_client(config.client_name)
    else:
        adapter.delete_wireguard_client(config.client_name)

    client_name = config.client_name
    vpn_type = config.vpn_type.value
    node = get_active_node(db)

    sync_group = find_sync_group_for_primary(db, node.id)
    if sync_group:
        maybe_replicate_delete(db, node_id=node.id, primary_config=config)

    purge_ha_shadow_configs(db, config.id)
    db.delete(config)
    db.commit()
    admin_notify_service.send_config_delete(
        db,
        actor_username=current_user.username,
        target_name=client_name,
        target_type=vpn_type,
        node_id=node.id,
        node_name=node.name,
        client_timezone=get_client_timezone_from_request(request),
    )
    return MessageResponse(message=f"Клиент '{client_name}' удалён")


@router.get("/{config_id}/download")
def download_profile(
    config_id: int,
    path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    content = get_active_adapter(db).read_profile_file(path)
    filename = build_profile_download_filename(config.client_name, path=path)
    return PlainTextResponse(content, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{config_id}/qr")
def generate_qr(
    config_id: int,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    config = _get_config_for_active_node(db, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    content = get_active_adapter(db).read_profile_file(path)
    qr_mode = "profile"
    headers: dict[str, str] = {"X-Qr-Content": qr_mode}
    try:
        png = generate_qr_png(content)
    except ValueError:
        link = _qr_download_service(db, request).create_token(
            file_path=path,
            config_type=config.vpn_type.value,
            config_name=build_profile_download_filename(config.client_name, path=path),
            creator_id=current_user.id,
            creator_username=current_user.username,
            remote_addr=request.client.host if request.client else None,
        )
        png = generate_qr_png(link["url"])
        qr_mode = "download-link"
        headers = {"X-Qr-Content": qr_mode, "X-Qr-Download-Url": link["url"]}
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
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Конфигурация не найдена")
    if not _can_access_config(current_user, config, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return _qr_download_service(db, request).create_token(
        file_path=path,
        config_type=config.vpn_type.value,
        config_name=build_profile_download_filename(config.client_name, path=path),
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
