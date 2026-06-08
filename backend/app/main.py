import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_password_hash
from app.config import get_settings
from app.middleware.http_security import HttpSecurityMiddleware
from app.middleware.active_session import ActiveSessionMiddleware
from app.services.security_bootstrap import validate_panel_settings
from app.database import Base, SessionLocal, engine, run_db_migrations
from app.models import User, UserRole, VpnConfig, VpnType
from app.routers import (
    auth,
    backups,
    cidr_db,
    client_access,
    configs,
    edit_files,
    game_filters,
    ip_blocked,
    logs,
    maintenance,
    monitoring,
    nodes,
    public_download,
    routing,
    security,
    server_monitor,
    system,
    feature_toggles,
    tests,
    tasks,
    tg_mini,
    traffic,
    session,
)
from app.routers import settings as settings_router
from app.routers import users
from app.services.backup_scheduler import run_backup_scheduler_loop
from app.services.cidr.cidr_scheduler import run_cidr_db_scheduler_loop
from app.services.wg_policy_sync_worker import run_wg_policy_sync_loop
from app.services.nightly_idle_restart_worker import run_nightly_idle_restart_loop
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.node_manager import ensure_local_node, get_active_adapter, get_active_node
from app.services.ip_restriction import ip_restriction_service
from app.services.node_health_worker import run_node_health_loop
from app.services.panel_resource_metrics_worker import run_panel_resource_metrics_loop
from app.services.resource_metrics_worker import run_resource_metrics_loop
from app.services.node_key_rotation import run_node_key_rotation_loop
from app.services.traffic.worker import run_traffic_collector_loop

settings = get_settings()
validate_panel_settings(settings)


def seed_database():
    Base.metadata.create_all(bind=engine)
    run_db_migrations()
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.default_admin_username).first()
        if not admin:
            admin = User(
                username=settings.default_admin_username,
                password_hash=get_password_hash(settings.default_admin_password),
                role=UserRole.admin,
                theme="dark",
                must_change_password=settings.default_admin_must_change_password,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        ensure_local_node(db)

        try:
            CidrDbUpdaterService(db=db).seed_builtin_presets()
        except Exception:
            pass

        try:
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

    seed_database()
    app_root = Path(__file__).resolve().parents[1]
    db_url = settings.database_url
    db_path = Path(db_url.replace("sqlite:///", ""))
    if not db_path.is_absolute():
        db_path = app_root / db_path
    collector_task = asyncio.create_task(run_traffic_collector_loop())
    health_task = asyncio.create_task(run_node_health_loop())
    resource_metrics_task = asyncio.create_task(run_resource_metrics_loop())
    panel_resource_metrics_task = asyncio.create_task(run_panel_resource_metrics_loop())
    backup_task = asyncio.create_task(
        run_backup_scheduler_loop(
            app_root=app_root,
            backup_root=Path(settings.backup_root),
            db_path=db_path,
            env_path=app_root / ".env",
        )
    )
    cidr_task = asyncio.create_task(run_cidr_db_scheduler_loop())
    wg_policy_sync_task = asyncio.create_task(run_wg_policy_sync_loop())
    nightly_idle_restart_task = asyncio.create_task(run_nightly_idle_restart_loop())
    key_rotation_task = asyncio.create_task(run_node_key_rotation_loop())
    from app.services.admin_notify import admin_notify_service

    admin_notify_service.start_monitor()
    try:
        ip_restriction_service.sync_firewall()
    except Exception:
        pass
    yield
    for task in (
        collector_task,
        health_task,
        resource_metrics_task,
        panel_resource_metrics_task,
        backup_task,
        cidr_task,
        wg_policy_sync_task,
        nightly_idle_restart_task,
        key_rotation_task,
    ):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(ActiveSessionMiddleware)
app.add_middleware(HttpSecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Captcha-Id", "X-Web-Session-Id", "Accept"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(configs.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(nodes.router, prefix="/api")
app.include_router(routing.router, prefix="/api")
app.include_router(cidr_db.router, prefix="/api")
app.include_router(traffic.router, prefix="/api")
app.include_router(client_access.router, prefix="/api")
app.include_router(edit_files.router, prefix="/api")
app.include_router(security.router, prefix="/api")
app.include_router(public_download.router, prefix="/api")
app.include_router(server_monitor.router, prefix="/api")
app.include_router(game_filters.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(tg_mini.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
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
        or path.startswith("/api/ip-blocked")
        or path.startswith("/api/auth/captcha")
        or path.startswith("/api/auth/telegram")
        or path.startswith("/api/auth/refresh")
        or path.startswith("/api/auth/login")
        or path in ("/api/health", "/ip-blocked")
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


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}


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

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        if full_path:
            candidate = dist / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index_file)


if settings.serve_frontend:
    _mount_frontend(app)
