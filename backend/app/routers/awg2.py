"""AZ-AWG2 (AmneziaWG 2.0 parallel layer) admin API."""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import decode_access_token_username, require_admin
from app.database import SessionLocal, get_db
from app.models import User, UserRole
from app.schemas import Awg2ObfuscationApply
from app.services.awg2 import Awg2ClientNotFoundError, Awg2NotInstalledError
from app.services.node_manager import get_active_adapter, get_active_node, get_adapter_for_node
from app.services.node_sync.groups import find_sync_group_for_primary, get_replica_nodes
from app.services.node_sync.vpn_state_sync import sync_amneziawg2_state_from_primary

router = APIRouter(prefix="/awg2", tags=["awg2"])


def _node_meta(node) -> dict:
    return {"node_id": node.id, "node_name": node.name, "node_host": node.host}


def _admin_from_stream_token(token: str, db: Session) -> User:
    username = decode_access_token_username(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def _iter_awg2_install_sse(
    adapter,
    mode: str,
    *,
    preset: str | None = None,
    template: str | None = None,
    mtu: int | None = None,
) -> Iterator[str]:
    for event in adapter.awg2_iter_install_stream(
        mode,
        preset=preset,
        template=template,
        mtu=mtu,
    ):
        yield f"data: {json.dumps(event, default=str)}\n\n"


def _ha_sync_awg2_from_active(db: Session) -> dict[str, Any]:
    """Best-effort HA push of AWG2 state to replicas. Never raises."""
    errors: list[dict[str, str | None]] = []
    try:
        node = get_active_node(db)
        group = find_sync_group_for_primary(db, node.id)
        if not group:
            return {"attempted": False, "errors": []}
        primary_adapter = get_active_adapter(db)
        replicas = get_replica_nodes(db, group)
        if not replicas:
            return {"attempted": True, "errors": []}
        for replica in replicas:
            try:
                replica_adapter = get_adapter_for_node(replica)
                sync_amneziawg2_state_from_primary(
                    primary_adapter,
                    replica_adapter,
                    db=db,
                    replica_node=replica,
                )
            except Exception as exc:  # noqa: BLE001 — collect warnings, do not fail apply
                errors.append({"node_name": getattr(replica, "name", None), "error": str(exc)})
        return {"attempted": True, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        return {"attempted": True, "errors": [{"node_name": None, "error": str(exc)}]}


def _map_awg2_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, Awg2NotInstalledError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, Awg2ClientNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/health")
def awg2_health(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    data = get_active_adapter(db).get_awg2_health()
    return {**data, **_node_meta(node)}


@router.get("/status")
def awg2_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_status()
    except Awg2NotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {**data, **_node_meta(node)}


@router.post("/backup")
def awg2_backup(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        data = get_active_adapter(db).export_awg2_backup()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="az-awg2-backup.tar.gz"'},
    )


@router.post("/restore")
async def awg2_restore(
    archive: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node = get_active_node(db)
    try:
        runtime = get_active_adapter(db).restore_awg2_backup(
            await archive.read(),
            archive.filename or "az-awg2-backup.tar.gz",
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    if runtime.get("success") is False:
        errors = runtime.get("errors") or []
        detail = "; ".join(
            str(entry.get("stderr") or entry.get("error") or entry)
            for entry in errors
        ) or "AZ-AWG2 runtime apply failed"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
    ha = _ha_sync_awg2_from_active(db)
    return {
        "message": "AZ-AWG2 восстановлен из бэкапа",
        "runtime": runtime,
        "ha": ha,
        **_node_meta(node),
    }


@router.get("/obfuscation")
def get_obfuscation(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_obfuscation()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return {**data, **_node_meta(node)}


@router.post("/obfuscation/regenerate")
def regenerate_obfuscation(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        result = get_active_adapter(db).awg2_obfuscation_regenerate()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    ha = _ha_sync_awg2_from_active(db)
    return {**result, **_node_meta(node), "ha": ha, "reimport_required": True}


@router.post("/obfuscation/apply")
def apply_obfuscation(
    payload: Awg2ObfuscationApply,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    node = get_active_node(db)
    try:
        result = get_active_adapter(db).awg2_obfuscation_apply(**payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    ha = _ha_sync_awg2_from_active(db)
    return {**result, **_node_meta(node), "ha": ha, "reimport_required": True}


@router.get("/monitoring")
def get_monitoring(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_monitoring()
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return {**data, **_node_meta(node)}


@router.get("/clients/{name}/stats")
def get_client_stats(name: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    node = get_active_node(db)
    try:
        data = get_active_adapter(db).get_awg2_client_stats(name)
    except Exception as exc:  # noqa: BLE001
        raise _map_awg2_exc(exc) from exc
    return {**data, **_node_meta(node)}


@router.get("/install/stream")
async def awg2_install_stream(
    request: Request,
    token: str = Query(..., description="JWT access token"),
    mode: str = Query(..., pattern="^(install|update)$"),
    preset: str | None = Query(None),
    template: str | None = Query(None),
    mtu: int | None = Query(None),
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
            for chunk in _iter_awg2_install_sse(
                adapter,
                mode,
                preset=preset,
                template=template,
                mtu=mtu,
            ):
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
