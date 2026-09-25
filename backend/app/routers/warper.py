"""AZ-WARP (WARPER) management API."""

import asyncio
import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.auth import get_active_user_from_access_token, require_admin
from app.models import User, UserRole
from app.schemas import (
    WarperActionResponse,
    WarperAutoResolveResponse,
    WarperCatalogInstalledResponse,
    WarperCatalogNameRequest,
    WarperCatalogSearchResponse,
    WarperCatalogShowResponse,
    WarperDoctorResponse,
    WarperDomainCreate,
    WarperDomainListsStatus,
    WarperDomainListToggle,
    WarperDomainsResponse,
    WarperEnableUpdate,
    WarperFullVpnUpdate,
    WarperHealthResponse,
    WarperIpExportUpdate,
    WarperIpRangeCreate,
    WarperIpRangeModeUpdate,
    WarperIpRangesResponse,
    WarperIpRoutesResponse,
    WarperLogLevelUpdate,
    WarperLogsResponse,
    WarperModeLinkUpdate,
    WarperModeOpenVpnUpdate,
    WarperModeResponse,
    WarperModeSlaveUpdate,
    WarperModeWarpUpdate,
    WarperModeWgUpdate,
    WarperMtuUpdate,
    WarperOvpnConfigRequest,
    WarperResolveCleanRequest,
    WarperSettingsOptionsResponse,
    WarperSingboxStatusResponse,
    WarperStatusResponse,
    WarperSubnetsResponse,
    WarperSubnetUpdate,
    WarperTextContentResponse,
    WarperTextSaveRequest,
    WarperTrafficResponse,
    WarperUpdatesCheckResponse,
)
from app.services.node_manager import get_active_adapter, get_active_node
from app.services.chart_timezone import resolve_chart_timezone
from app.services.warper import SINGBOX_ACTIONS, enrich_warper_traffic_payload

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
    payload = adapter.get_warper_domains_bundle()
    lists = payload.get("lists") or {}
    return WarperDomainsResponse(
        domains=payload.get("domains") or [],
        lists=WarperDomainListsStatus(**lists),
        user_text=payload.get("user_text"),
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
    request: Request,
    period: str = Query("today", pattern="^(today|week|month|all)$"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_warper_traffic(period)
    if isinstance(data, dict):
        tz = resolve_chart_timezone(user=current_user, request=request)
        data = enrich_warper_traffic_payload(data, period, tz_name=tz)
    else:
        data = {"raw": data}
    return WarperTrafficResponse(data=data, **_node_meta(node))


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
    if not isinstance(options, dict):
        options = {}
    return WarperSettingsOptionsResponse(
        warp_keys=options.get("warp_keys") or [],
        warp_key_items=options.get("warp_key_items") or [],
        wg_configs=options.get("wg_configs") or [],
        ovpn_configs=options.get("ovpn_configs") or [],
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
    link = (payload.link or "").strip()
    if link:
        return _action_response(adapter.set_warper_mode_slave(link=link), node)
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


@router.post("/settings/mode/vless", response_model=WarperActionResponse)
def warper_settings_mode_vless(
    payload: WarperModeLinkUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mode_vless(payload.link.strip()), node)


@router.post("/settings/mode/hy2", response_model=WarperActionResponse)
def warper_settings_mode_hy2(
    payload: WarperModeLinkUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_mode_hy2(payload.link.strip()), node)


@router.post("/settings/mode/openvpn", response_model=WarperActionResponse)
def warper_settings_mode_openvpn(
    payload: WarperModeOpenVpnUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(
        adapter.set_warper_mode_openvpn(payload.config_path, payload.username, payload.password),
        node,
    )


@router.post("/settings/ovpn/forget", response_model=WarperActionResponse)
def warper_settings_ovpn_forget(
    payload: WarperOvpnConfigRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_forget_ovpn_credentials(payload.config_path), node)


@router.put("/settings/autopatch", response_model=WarperActionResponse)
def warper_settings_autopatch(
    payload: WarperEnableUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_autopatch(enable=payload.enable), node)


@router.post("/resync", response_model=WarperActionResponse)
def warper_resync(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_resync(), node)


@router.post("/domains/update-lists", response_model=WarperActionResponse)
def warper_domains_update_lists(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_update_lists(), node)


@router.get("/resolve", response_model=WarperAutoResolveResponse)
def warper_resolve_get(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_warper_auto_resolve()
    enabled = bool(data.get("enabled")) if isinstance(data, dict) else False
    return WarperAutoResolveResponse(enabled=enabled, **_node_meta(node))


@router.put("/resolve", response_model=WarperActionResponse)
def warper_resolve_set(
    payload: WarperEnableUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.set_warper_auto_resolve(enable=payload.enable), node)


@router.post("/resolve/sync", response_model=WarperActionResponse)
def warper_resolve_sync(
    force: bool = Query(False),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_resolve_sync(force=force), node)


@router.post("/resolve/clean", response_model=WarperActionResponse)
def warper_resolve_clean(
    payload: WarperResolveCleanRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    domain = (payload.domain or "").strip() or None
    return _action_response(adapter.warper_resolve_clean(domain), node)


@router.get("/ip-routes", response_model=WarperIpRoutesResponse)
def warper_ip_routes(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperIpRoutesResponse(routes=adapter.get_warper_ip_routes(), **_node_meta(node))


@router.post("/ip-routes/clear", response_model=WarperActionResponse)
def warper_ip_routes_clear(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_clear_ip_routes(), node)


@router.get("/subnets", response_model=WarperSubnetsResponse)
def warper_subnets(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperSubnetsResponse(subnets=adapter.get_warper_subnets(), **_node_meta(node))


@router.get("/singbox/status", response_model=WarperSingboxStatusResponse)
def warper_singbox_status(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.get_warper_singbox_status()
    payload = {k: v for k, v in data.items() if k not in {"node_id", "node_name"}} if isinstance(data, dict) else {}
    return WarperSingboxStatusResponse(**payload, **_node_meta(node))


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
    if action not in SINGBOX_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Допустимо: {', '.join(SINGBOX_ACTIONS)}")
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_singbox_action(action), node)


@router.get("/catalog/search", response_model=WarperCatalogSearchResponse)
def warper_catalog_search(
    query: str = Query("", max_length=128),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperCatalogSearchResponse(items=adapter.warper_catalog_search(query), **_node_meta(node))


@router.get("/catalog/installed", response_model=WarperCatalogInstalledResponse)
def warper_catalog_installed(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return WarperCatalogInstalledResponse(items=adapter.warper_catalog_list_installed(), **_node_meta(node))


@router.get("/catalog/show/{name}", response_model=WarperCatalogShowResponse)
def warper_catalog_show(
    name: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.warper_catalog_show(name)
    payload = data if isinstance(data, dict) else {}
    return WarperCatalogShowResponse(**payload, **_node_meta(node))


@router.post("/catalog/add", response_model=WarperActionResponse)
def warper_catalog_add(
    payload: WarperCatalogNameRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_catalog_add(payload.name), node)


@router.post("/catalog/remove", response_model=WarperActionResponse)
def warper_catalog_remove(
    payload: WarperCatalogNameRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_catalog_remove(payload.name), node)


@router.post("/catalog/update", response_model=WarperActionResponse)
def warper_catalog_update(
    name: str = Query("", max_length=128),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_catalog_update(name), node)


@router.post("/catalog/refresh", response_model=WarperActionResponse)
def warper_catalog_refresh(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    return _action_response(adapter.warper_catalog_refresh_cache(), node)


@router.get("/updates/check", response_model=WarperUpdatesCheckResponse)
def warper_updates_check(
    force: bool = Query(False),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    adapter = get_active_adapter(db)
    node = get_active_node(db)
    data = adapter.warper_check_for_updates(force=force)
    return WarperUpdatesCheckResponse(**data, **_node_meta(node))


def _admin_from_stream_token(token: str, db: Session) -> User:
    user = get_active_user_from_access_token(db, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def _iter_warper_update_sse(adapter) -> Iterator[str]:
    for event in adapter.warper_iter_update_stream():
        yield f"data: {json.dumps(event, default=str)}\n\n"


@router.get("/updates/stream")
async def warper_updates_stream(
    request: Request,
    token: str = Query(..., description="JWT access token"),
):
    db = SessionLocal()
    try:
        _admin_from_stream_token(token, db)
    finally:
        db.close()

    async def event_generator():
        db = SessionLocal()
        try:
            adapter = get_active_adapter(db)
            for chunk in _iter_warper_update_sse(adapter):
                if await request.is_disconnected():
                    break
                yield chunk
                await asyncio.sleep(0)
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'error', 'detail': str(exc)}, default=str)}\n\n"
        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
