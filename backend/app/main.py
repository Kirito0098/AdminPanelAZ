import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_password_hash
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole, VpnConfig, VpnType
from app.routers import (
    auth,
    backups,
    cidr_db,
    client_access,
    configs,
    edit_files,
    game_filters,
    logs,
    maintenance,
    monitoring,
    nodes,
    public_download,
    routing,
    security,
    server_monitor,
    system,
    tg_mini,
    traffic,
)
from app.routers import settings as settings_router
from app.routers import users
from app.services.backup_scheduler import run_backup_scheduler_loop
from app.services.cidr.cidr_scheduler import run_cidr_db_scheduler_loop
from app.services.cidr.pipeline.db_service import CidrDbUpdaterService
from app.services.node_manager import ensure_local_node, get_active_adapter
from app.services.security import SecurityService
from app.services.traffic.worker import run_traffic_collector_loop

settings = get_settings()


def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.default_admin_username).first()
        if not admin:
            admin = User(
                username=settings.default_admin_username,
                password_hash=get_password_hash(settings.default_admin_password),
                role=UserRole.admin,
                theme="dark",
                must_change_password=True,
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
            ovpn_clients = adapter.list_openvpn_clients()
            wg_clients = adapter.list_wireguard_clients()
            for name in ovpn_clients:
                if not db.query(VpnConfig).filter(
                    VpnConfig.client_name == name, VpnConfig.vpn_type == VpnType.openvpn
                ).first():
                    db.add(VpnConfig(client_name=name, vpn_type=VpnType.openvpn, owner_id=admin.id))
            for name in wg_clients:
                if not db.query(VpnConfig).filter(
                    VpnConfig.client_name == name, VpnConfig.vpn_type == VpnType.wireguard
                ).first():
                    db.add(VpnConfig(client_name=name, vpn_type=VpnType.wireguard, owner_id=admin.id))
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
    backup_task = asyncio.create_task(
        run_backup_scheduler_loop(
            app_root=app_root,
            backup_root=Path(settings.backup_root),
            db_path=db_path,
            env_path=app_root / ".env",
        )
    )
    cidr_task = asyncio.create_task(run_cidr_db_scheduler_loop())
    yield
    for task in (collector_task, backup_task, cidr_task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
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


@app.middleware("http")
async def ip_restriction_middleware(request, call_next):
    if request.url.path.startswith("/api/public/") or request.url.path in ("/api/health", "/api/tg-mini", "/api/tg-mini/auth"):
        return await call_next(request)
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        client_ip = request.client.host if request.client else ""
        if request.headers.get("authorization") and not SecurityService().is_ip_allowed(db, client_ip):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Доступ запрещён с вашего IP"})
    finally:
        db.close()
    return await call_next(request)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
