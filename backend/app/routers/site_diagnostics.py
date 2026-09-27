"""Runbook API: in-panel wrapper for site-diagnostics-cli."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.services.action_log import log_action
from app.services.background_tasks import background_task_service
from app.services.nginx_default_deny import (
    DefaultDenyResult,
    is_nginx_publish_mode,
    run_default_deny_script,
    script_path as default_deny_script_path,
)
from app.services.site_diagnostics import (
    check_result_to_dict,
    ip_access_check_result,
    read_diagnostics_env,
    report_to_dict,
    resolve_diagnostics_context,
    run_site_diagnostics,
)

router = APIRouter(prefix="/site-diagnostics", tags=["site-diagnostics"])

_REFUSE_NOT_APPLICABLE = (
    "Закрывать нечего: на портах панели по IP сервера отвечает другой сайт "
    "или vhost панели в nginx не найден."
)
_REFUSE_OWN_DEFAULT = (
    "На портах панели уже есть ваш сервер по умолчанию nginx — панель его не заменяет."
)
# Фоновые задачи, которые переписывают конфигурацию nginx и перезагружают его.
_NGINX_TASK_CONFLICTS = (
    ("vpn_network_publish", "Сначала дождитесь завершения публикации панели"),
    ("portal_publish", "Сейчас выполняется настройка портала"),
    ("portal_readiness_prepare", "Подготовка портала уже выполняется"),
)


def _nginx_task_conflict_response() -> JSONResponse | None:
    for task_type, detail in _NGINX_TASK_CONFLICTS:
        active_task = background_task_service.find_active_task(task_type)
        if active_task:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": detail, "active_task_id": active_task.id},
            )
    return None


def _close_ip_access_message(result: DefaultDenyResult) -> str:
    if result.status in ("not_applicable", "own_default"):
        if result.changed:
            return (
                "Устаревший сервер по умолчанию убран — закрывать по IP больше нечего; "
                "nginx перечитал конфигурацию"
            )
        return "Закрывать по IP нечего — nginx не перезагружался"
    if result.changed:
        message = "Доступ к панели по IP сервера закрыт — nginx перечитал конфигурацию"
    else:
        message = "Доступ по IP уже был закрыт — nginx не перезагружался"
    if any(p.get("reason") == "no_cert" for p in result.ports):
        message += ". HTTPS по IP остался открыт: нет сертификата-заглушки (nginx старше 1.19.4)"
    return message


@router.post("/run")
def run_site_diagnostics_api(_: User = Depends(require_admin)):
    ctx = resolve_diagnostics_context()
    report = run_site_diagnostics(ctx)
    return report_to_dict(report, ctx)


@router.post("/close-ip-access")
def close_ip_access_api(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ставит только сервер по умолчанию nginx (00-adminpanelaz-default-deny) и делает reload."""
    ctx = resolve_diagnostics_context()
    env = read_diagnostics_env(ctx)
    if not is_nginx_publish_mode(env):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Панель опубликована без nginx — закрыть доступ по IP через nginx нельзя. "
            "Ограничьте вход в разделе «Защита входа» или firewall'ом.",
        )
    conflict = _nginx_task_conflict_response()
    if conflict is not None:
        return conflict

    script = default_deny_script_path(ctx.install_dir)
    current = run_default_deny_script(script, "--check")
    if current.status is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось проверить nginx: {current.message}",
        )
    if current.status == "not_applicable":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_REFUSE_NOT_APPLICABLE)
    if current.status == "own_default":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_REFUSE_OWN_DEFAULT)

    result = run_default_deny_script(script, "--apply")

    from app.services.ip_restriction import ip_restriction_service

    if result.ok:
        details = f"status={result.status} changed={'true' if result.changed else 'false'}"
    else:
        details = f"status=failed error={result.error or 'unknown'} message={result.message}"
    log_action(
        db,
        action="site_diagnostics_close_ip_access",
        user_id=admin.id,
        username=admin.username,
        remote_addr=ip_restriction_service.get_client_ip(request),
        details=details,
    )
    if not result.ok:
        reason = result.message or "nginx не принял изменения"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось закрыть доступ по IP: {reason}",
        )

    message = _close_ip_access_message(result)
    check = ip_access_check_result(result, ctx)
    check.category = "nginx"
    return {
        "success": True,
        "status": result.status,
        "changed": result.changed,
        "message": message,
        "check": check_result_to_dict(check),
    }
