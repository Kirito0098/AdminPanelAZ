"""Runbook API: in-panel wrapper for site-diagnostics-cli."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_admin
from app.models import User
from app.services.site_diagnostics import (
    report_to_dict,
    resolve_diagnostics_context,
    run_site_diagnostics,
)

router = APIRouter(prefix="/site-diagnostics", tags=["site-diagnostics"])


@router.post("/run")
def run_site_diagnostics_api(_: User = Depends(require_admin)):
    ctx = resolve_diagnostics_context()
    report = run_site_diagnostics(ctx)
    return report_to_dict(report, ctx)
