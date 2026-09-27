"""Public client portal meta + raw profile download (no auth, Host = portal_domain)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.client_portal import (
    assert_portal_host,
    build_public_portal_payload,
    get_valid_portal_token,
    redeem_public_portal_code,
    read_portal_profile,
)
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.file_download import attachment_response
from app.services.ip_restriction import ip_restriction_service
from app.services.public_download_rate_limit import public_download_rate_limit_service

router = APIRouter(prefix="/public/portal", tags=["public-portal"])


def _require_portal_enabled() -> None:
    service = get_feature_service()
    if not service.is_enabled("client_portal"):
        raise HTTPException(status_code=403, detail=module_disabled_message("client_portal"))


class PublicPortalRedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)


@router.get("/{token}")
def portal_meta(token: str, request: Request, db: Session = Depends(get_db)):
    _require_portal_enabled()
    assert_portal_host(db, request.headers.get("host"))
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)
    row = get_valid_portal_token(db, token)
    return build_public_portal_payload(db, row)


@router.get("/{token}/download")
def portal_download(
    token: str,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    node_id: int | None = None,
    client_name: str | None = None,
):
    _require_portal_enabled()
    assert_portal_host(db, request.headers.get("host"))
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)
    row = get_valid_portal_token(db, token)
    filename, content = read_portal_profile(db, row, path, node_id=node_id, client_name=client_name)
    return attachment_response(content, filename)


@router.post("/{token}/redeem")
def portal_redeem(
    token: str,
    payload: PublicPortalRedeemRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    assert_portal_host(db, request.headers.get("host"))
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)
    _require_portal_enabled()
    if not get_feature_service().is_enabled("unlock_codes"):
        raise HTTPException(status_code=403, detail=module_disabled_message("unlock_codes"))
    row = get_valid_portal_token(db, token)
    try:
        result = redeem_public_portal_code(db, row, code=payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "grant_days": result["grant_days"],
        "protocols_applied": result["protocols_applied"],
        "access_until_by_protocol": result.get("access_until_by_protocol") or {},
        "access_until": result.get("access_until"),
    }
