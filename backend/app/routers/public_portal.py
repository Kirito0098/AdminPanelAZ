"""Public client portal meta + raw profile download (no auth, Host = portal_domain)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.client_portal import (
    assert_portal_host,
    build_portal_payload,
    get_valid_portal_token,
    read_portal_profile,
)
from app.services.feature_guards import get_feature_service, module_disabled_message
from app.services.file_download import attachment_response
from app.services.ip_restriction import ip_restriction_service
from app.services.public_download_rate_limit import public_download_rate_limit_service
from fastapi import HTTPException

router = APIRouter(prefix="/public/portal", tags=["public-portal"])


def _require_portal_enabled() -> None:
    service = get_feature_service()
    if not service.is_enabled("client_portal"):
        raise HTTPException(status_code=403, detail=module_disabled_message("client_portal"))


@router.get("/{token}")
def portal_meta(token: str, request: Request, db: Session = Depends(get_db)):
    _require_portal_enabled()
    assert_portal_host(db, request.headers.get("host"))
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)
    row = get_valid_portal_token(db, token)
    return build_portal_payload(db, row)


@router.get("/{token}/download")
def portal_download(token: str, path: str, request: Request, db: Session = Depends(get_db)):
    _require_portal_enabled()
    assert_portal_host(db, request.headers.get("host"))
    client_ip = ip_restriction_service.get_client_ip(request)
    public_download_rate_limit_service.consume(client_ip)
    row = get_valid_portal_token(db, token)
    filename, content = read_portal_profile(db, row, path)
    return attachment_response(content, filename)
