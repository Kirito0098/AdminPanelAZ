from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_password_hash
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole, VpnConfig, VpnType
from app.routers import auth, configs, monitoring
from app.routers import settings as settings_router
from app.routers import users
from app.services.antizapret import antizapret_service

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

        try:
            ovpn_clients = antizapret_service.list_openvpn_clients()
            wg_clients = antizapret_service.list_wireguard_clients()
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
    seed_database()
    yield


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


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
