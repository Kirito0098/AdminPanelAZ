import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)
from app.middleware.api_rate_limit import ApiRateLimitMiddleware
from app.middleware.http_security import HttpSecurityMiddleware, build_robots_txt, build_security_txt, get_panel_branding
from app.middleware.active_session import ActiveSessionMiddleware
from app.services.security_bootstrap import validate_panel_settings
from app.database import Base, SessionLocal, engine, run_db_migrations
from app.cidr_database import CidrBase, cidr_engine, run_cidr_db_migrations
from app.models import User, UserRole, VpnConfig, VpnType
from app.routers import (
    alert_rules,
    auth,
    backups,
    cidr_db,
    client_access,
    client_templates,
    config_tags,
    configs,
    configs_bulk,
    edit_files,
    ip_blocked,
    logs,
    maintenance,
    monitoring,
    nodes,
    node_sync,
    public_download,
    routing,
    warper,
    security,
    server_monitor,
    site_diagnostics,
    system,
    feature_toggles,
    tests,
    tasks,
    tg_mini,
    traffic,
    telegram_webhook,
    session,
)
from app.routers import settings as settings_router
from app.routers import users
from app.services.admin_bootstrap import upsert_bootstrap_admin
from app.services.node_manager import get_active_adapter, get_active_node, sync_local_node
from app.services.ip_restriction import ip_restriction_service
from app.services.lifespan_workers import cancel_background_tasks, spawn_background_tasks
from app.services.worker_lifecycle import should_start_resource_monitor

settings = get_settings()
validate_panel_settings(settings)


def seed_database():
    Base.metadata.create_all(bind=engine)
    run_db_migrations()
    run_cidr_db_migrations()
    db = SessionLocal()
    try:
        try:
            upsert_bootstrap_admin(db, force=False, settings=settings)
        except ValueError:
            pass

        sync_local_node(db)

        try:
            admin = db.query(User).filter(User.role == UserRole.admin).first()
            if not admin:
                raise ValueError("admin user not found")
            adapter = get_active_adapter(db)
            node_id = get_active_node(db).id
            ovpn_clients = adapter.list_openvpn_clients()
            wg_clients = adapter.list_wireguard_clients()
            for name in ovpn_clients:
                if not db.query(VpnConfig).filter(
                    VpnConfig.node_id == node_id,
                    VpnConfig.client_name == name,
                    VpnConfig.vpn_type == VpnType.openvpn,
                ).first():
                    db.add(
                        VpnConfig(
                            node_id=node_id,
                            client_name=name,
                            vpn_type=VpnType.openvpn,
                            owner_id=admin.id,
                        )
                    )
            for name in wg_clients:
                if not db.query(VpnConfig).filter(
                    VpnConfig.node_id == node_id,
                    VpnConfig.client_name == name,
                    VpnConfig.vpn_type == VpnType.wireguard,
                ).first():
                    db.add(
                        VpnConfig(
                            node_id=node_id,
                            client_name=name,
                            vpn_type=VpnType.wireguard,
                            owner_id=admin.id,
                        )
                    )
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    from pathlib import Path

    from app.services.health_checks import mark_app_started

    mark_app_started()
    seed_database()
    app_root = Path(__file__).resolve().parents[1]
    db_url = settings.database_url
    db_path = Path(db_url.replace("sqlite:///", ""))
    if not db_path.is_absolute():
        db_path = app_root / db_path
    env_path = app_root / ".env"
    background_tasks = spawn_background_tasks(app_root=app_root, db_path=db_path, env_path=env_path)
    from app.services.admin_notify import admin_notify_service

    if should_start_resource_monitor():
        admin_notify_service.start_monitor()
    try:
        from app.services.background_tasks import background_task_service

        recovered = background_task_service.recover_stale_running_tasks()
        if recovered:
            logger.info("Recovered %d stale background task(s) after restart", recovered)
    except Exception:
        pass
    try:
        from app.services.cidr.pipeline.list_migration import migrate_legacy_cidr_list_dir

        migrated = migrate_legacy_cidr_list_dir()
        if migrated:
            logger.info("Migrated %d legacy CIDR list file(s) on startup", migrated)
    except Exception:
        logger.debug("Legacy CIDR list migration skipped", exc_info=True)
    try:
        ip_restriction_service.sync_firewall()
    except Exception:
        pass
    try:
        from app.database import SessionLocal

        startup_db = SessionLocal()
        try:
            ip_restriction_service.sync_whitelist_port_firewall(startup_db)
        finally:
            startup_db.close()
    except Exception:
        pass
    yield
    await cancel_background_tasks(background_tasks)


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(ActiveSessionMiddleware)
app.add_middleware(HttpSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Captcha-Id", "X-Web-Session-Id", "Accept"],
)
app.add_middleware(ApiRateLimitMiddleware)

app.include_router(auth.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(configs.router, prefix="/api")
app.include_router(configs_bulk.router, prefix="/api")
app.include_router(config_tags.router, prefix="/api")
app.include_router(client_templates.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(alert_rules.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(node_sync.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
app.include_router(routing.router, prefix="/api")
app.include_router(warper.router, prefix="/api")
app.include_router(cidr_db.router, prefix="/api")
app.include_router(traffic.router, prefix="/api")
app.include_router(client_access.router, prefix="/api")
app.include_router(edit_files.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(public_download.router, prefix="/api")
app.include_router(server_monitor.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(tg_mini.router, prefix="/api")
app.include_router(telegram_webhook.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
app.include_router(site_diagnostics.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(feature_toggles.router, prefix="/api")
app.include_router(feature_toggles.feature_modules_router, prefix="/api")
app.include_router(ip_blocked.router)


@app.middleware("http")
async def feature_guard_middleware(request, call_next):
    path = request.url.path
    if path.startswith("/api/"):
        from app.services.feature_guards import blocked_json_response, check_path_access, get_feature_service

        blocked = check_path_access(path, service=get_feature_service())
        if blocked is not None:
            module_key, _ = blocked
            return blocked_json_response(module_key)
    return await call_next(request)


@app.middleware("http")
async def ip_restriction_middleware(request, call_next):
    path = request.url.path
    exempt = (
        path.startswith("/api/public/")
        or path.startswith("/api/tg-mini")
        or path.startswith("/api/telegram/webhook/")
        or path.startswith("/api/ip-blocked")
        or path.startswith("/api/auth/captcha")
        or path.startswith("/api/auth/telegram")
        or path.startswith("/api/auth/refresh")
        or path.startswith("/api/auth/login")
        or path in ("/api/health", "/api/health/deep", "/metrics", "/ip-blocked")
    )
    if exempt:
        return await call_next(request)

    from app.database import SessionLocal
    from fastapi.responses import JSONResponse, RedirectResponse

    db = SessionLocal()
    try:
        client_ip = ip_restriction_service.get_client_ip(request)
        if ip_restriction_service.should_hard_deny(db, client_ip):
            return JSONResponse(status_code=403, content={"detail": "Доступ заблокирован на уровне сервера"})

        settings = ip_restriction_service.get_settings(db)
        if settings.get("ip_restriction_enabled") and not ip_restriction_service.is_ip_allowed(db, client_ip):
            if ip_restriction_service.should_count_denied_access(path):
                ip_restriction_service.record_denied_access(db, client_ip)
            accept = request.headers.get("accept", "")
            if path.startswith("/api/") or "application/json" in accept:
                return JSONResponse(status_code=403, content={"detail": "Доступ запрещён с вашего IP"})
            return RedirectResponse(url="/ip-blocked", status_code=302)
    finally:
        db.close()
    return await call_next(request)


def _register_openapi_docs_routes() -> None:
    from fastapi import Request
    from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
    from fastapi.responses import JSONResponse

    from app.services.openapi_docs_gate import assert_openapi_docs_access

    @app.get("/openapi.json", include_in_schema=False)
    async def protected_openapi_schema(request: Request):
        assert_openapi_docs_access(request)
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False)
    async def protected_swagger_ui(request: Request):
        assert_openapi_docs_access(request)
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{settings.app_name} — Swagger UI")

    @app.get("/redoc", include_in_schema=False)
    async def protected_redoc(request: Request):
        assert_openapi_docs_access(request)
        return get_redoc_html(openapi_url="/openapi.json", title=f"{settings.app_name} — ReDoc")


_register_openapi_docs_routes()


@app.get("/api/health")
def health():
    from app.services.health_checks import build_light_health

    return build_light_health()


@app.get("/api/health/deep")
def health_deep():
    from pathlib import Path

    from app.database import SessionLocal
    from app.services.health_checks import build_deep_health

    app_root = Path(__file__).resolve().parents[1]
    db = SessionLocal()
    try:
        return build_deep_health(db, app_root=app_root)
    finally:
        db.close()


@app.get("/metrics", include_in_schema=False)
def metrics():
    from fastapi.responses import Response

    from app.database import SessionLocal
    from app.services.prometheus_metrics import render_metrics

    db = SessionLocal()
    try:
        body, content_type = render_metrics(db)
        return Response(content=body, media_type=content_type)
    finally:
        db.close()


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(build_robots_txt(), media_type="text/plain")


@app.get("/.well-known/security.txt", include_in_schema=False)
def security_txt():
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(build_security_txt(get_panel_branding()), media_type="text/plain")


def _mount_frontend(app: FastAPI) -> None:
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = settings.frontend_dist_path
    if not dist.is_absolute():
        dist = Path(__file__).resolve().parents[1] / dist
    if not dist.is_dir():
        return

    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    index_file = dist / "index.html"

    # Fallback for stale backends: without this, POST to a missing /api/* route matches the
    # GET-only SPA catch-all below and surfaces misleading "Method Not Allowed" (405).
    @app.api_route(
        "/api/{rest:path}",
        methods=["POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def api_route_not_found(rest: str):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="API endpoint not found — перезапустите панель после обновления")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str, request: Request):
        from app.services.html_csp import serve_html_with_nonce

        if full_path.startswith("api/") or full_path == "api":
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        if full_path:
            candidate = dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        return serve_html_with_nonce(request, index_file)


if settings.serve_frontend:
    _mount_frontend(app)
