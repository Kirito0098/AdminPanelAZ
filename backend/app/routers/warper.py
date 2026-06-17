"""AZ-WARP (WARPER) management API."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_admin
from app.models import User
from app.schemas import (
    WarperActionResponse,
    WarperDoctorResponse,
    WarperDomainCreate,
    WarperDomainListsStatus,
    WarperDomainListToggle,
    WarperDomainsBulkCreate,
    WarperDomainsBulkResponse,
    WarperDomainsResponse,
    WarperFullVpnUpdate,
    WarperHealthResponse,
    WarperIpExportUpdate,
    WarperIpRangeCreate,
    WarperIpRangeModeUpdate,
    WarperIpRangesResponse,
    WarperLogLevelUpdate,
    WarperLogsResponse,
    WarperModeResponse,
    WarperModeSlaveUpdate,
    WarperModeWarpUpdate,
    WarperModeWgUpdate,
    WarperMtuUpdate,
    WarperSettingsOptionsResponse,
    WarperStatusResponse,
    WarperSubnetUpdate,
    WarperTextContentResponse,
    WarperTextSaveRequest,
    WarperTrafficResponse,
)
from app.services.node_manager import get_active_adapter, get_active_node

router = APIRouter(prefix="/warper", tags=["warper"])


def _node_meta(node) -> dict:
    return {"node_id": node.id, "node_name": node.name, "node_host": node.host}


def _action_response(result, node) -> WarperActionResponse:
    if isinstance(result, dict):
        return WarperActionResponse(**result, **_node_meta(node))
    return WarperActionResponse(message=str(result), **_node_meta(node))


@router.get("/health", response_model=WarperHealthResponse)
def warper_health(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_warper_health()
    return WarperHealthResponse(**data, **_node_meta(node))


@router.get("/status", response_model=WarperStatusResponse)
def warper_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperStatusResponse(status=adapter.get_warper_status(), **_node_meta(node))


@router.get("/doctor", response_model=WarperDoctorResponse)
def warper_doctor(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    items = adapter.get_warper_doctor()
    summary = {"ok": 0, "warn": 0, "error": 0, "info": 0}
    for item in items:
        status_key = str(item.get("status") or "info")
        if status_key not in summary:
            status_key = "info"
        summary[status_key] += 1
    passed = not summary["error"] if items else None
    return WarperDoctorResponse(
        items=items,
        passed=passed,
        summary=summary if items else None,
        **_node_meta(node),
    )


@router.post("/toggle", response_model=WarperActionResponse)
def warper_toggle(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_toggle(), node)


@router.get("/domains", response_model=WarperDomainsResponse)
def warper_domains_list(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    lists = adapter.get_warper_domain_lists()
    return WarperDomainsResponse(
        domains=adapter.get_warper_domains(),
        lists=WarperDomainListsStatus(**lists),
        user_text=adapter.get_warper_user_domains_text(),
        **_node_meta(node),
    )


@router.post("/domains", response_model=WarperActionResponse)
def warper_domains_add(
    payload: WarperDomainCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.add_warper_domain(payload.domain), node)


@router.post("/domains/bulk", response_model=WarperDomainsBulkResponse)
def warper_domains_bulk(
    payload: WarperDomainsBulkCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    result = adapter.add_warper_domains_bulk(payload.domains)
    return WarperDomainsBulkResponse(**result, **_node_meta(node))


@router.post("/domains/lists/{name}", response_model=WarperActionResponse)
def warper_domains_list_toggle(
    name: str,
    payload: WarperDomainListToggle,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_domain_list(name, enable=payload.enable), node)


@router.get("/domains/text", response_model=WarperTextContentResponse)
def warper_domains_text_get(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperTextContentResponse(content=adapter.get_warper_user_domains_text(), **_node_meta(node))


@router.put("/domains/text", response_model=WarperActionResponse)
def warper_domains_text_save(
    payload: WarperTextSaveRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.save_warper_user_domains_text(payload.text), node)


@router.delete("/domains/{domain:path}", response_model=WarperActionResponse)
def warper_domains_remove(
    domain: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.remove_warper_domain(domain), node)


@router.post("/domains/sync", response_model=WarperActionResponse)
def warper_domains_sync(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.sync_warper_domains(), node)


@router.get("/ip-ranges", response_model=WarperIpRangesResponse)
def warper_ip_ranges_list(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperIpRangesResponse(
        ranges=adapter.get_warper_ip_ranges(),
        content=adapter.get_warper_ip_ranges_text(),
        **_node_meta(node),
    )


@router.post("/ip-ranges", response_model=WarperActionResponse)
def warper_ip_ranges_add(
    payload: WarperIpRangeCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.add_warper_ip_range(payload.cidr), node)


@router.get("/ip-ranges/text", response_model=WarperTextContentResponse)
def warper_ip_ranges_text_get(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperTextContentResponse(content=adapter.get_warper_ip_ranges_text(), **_node_meta(node))


@router.put("/ip-ranges/text", response_model=WarperActionResponse)
def warper_ip_ranges_text_save(
    payload: WarperTextSaveRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.save_warper_ip_ranges_text(payload.text), node)


@router.delete("/ip-ranges/{cidr:path}", response_model=WarperActionResponse)
def warper_ip_ranges_remove(
    cidr: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.remove_warper_ip_range(cidr), node)


@router.post("/ip-ranges/sync", response_model=WarperActionResponse)
def warper_ip_ranges_sync(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.sync_warper_ip_ranges(), node)


@router.post("/ip-ranges/mode", response_model=WarperActionResponse)
def warper_ip_ranges_mode(
    payload: WarperIpRangeModeUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_ip_route_mode(payload.mode), node)


@router.post("/ip-ranges/export", response_model=WarperActionResponse)
def warper_ip_ranges_export(
    payload: WarperIpExportUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_ip_export(enable=payload.enable), node)


@router.get("/traffic", response_model=WarperTrafficResponse)
def warper_traffic(
    period: str = Query("today", pattern="^(today|week|month|all)$"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_warper_traffic(period)
    return WarperTrafficResponse(data=data if isinstance(data, dict) else {"raw": data}, **_node_meta(node))


@router.get("/logs", response_model=WarperLogsResponse)
def warper_logs(
    lines: int = Query(200, ge=1, le=2000),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperLogsResponse(lines=adapter.get_warper_logs(lines), **_node_meta(node))


@router.get("/settings/mode", response_model=WarperModeResponse)
def warper_settings_mode(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    mode = adapter.get_warper_mode()
    return WarperModeResponse(mode=mode if isinstance(mode, dict) else {}, **_node_meta(node))


@router.get("/settings/options", response_model=WarperSettingsOptionsResponse)
def warper_settings_options(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    options = adapter.get_warper_settings_options()
    return WarperSettingsOptionsResponse(
        warp_keys=options.get("warp_keys", []) if isinstance(options, dict) else [],
        wg_configs=options.get("wg_configs", []) if isinstance(options, dict) else [],
        **_node_meta(node),
    )


@router.post("/settings/mode/warp", response_model=WarperActionResponse)
def warper_settings_mode_warp(
    payload: WarperModeWarpUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mode_warp(payload.key_source), node)


@router.post("/settings/mode/slave", response_model=WarperActionResponse)
def warper_settings_mode_slave(
    payload: WarperModeSlaveUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mode_slave(payload.host, payload.port, payload.key), node)


@router.post("/settings/mode/wg", response_model=WarperActionResponse)
def warper_settings_mode_wg(
    payload: WarperModeWgUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mode_wg(payload.config_path), node)


@router.put("/settings/fullvpn", response_model=WarperActionResponse)
def warper_settings_fullvpn(
    payload: WarperFullVpnUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_fullvpn(enable=payload.enable), node)


@router.put("/settings/subnet", response_model=WarperActionResponse)
def warper_settings_subnet(
    payload: WarperSubnetUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_subnet(payload.subnet), node)


@router.put("/settings/mtu", response_model=WarperActionResponse)
def warper_settings_mtu(
    payload: WarperMtuUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mtu(payload.mtu), node)


@router.put("/settings/log-level", response_model=WarperActionResponse)
def warper_settings_log_level(
    payload: WarperLogLevelUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_log_level(payload.level), node)


@router.post("/singbox/{action}", response_model=WarperActionResponse)
def warper_singbox_action(
    action: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if action not in {"start", "stop", "restart"}:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Допустимо: start, stop, restart")
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_singbox_action(action), node)
