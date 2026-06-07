from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AdminPanel AntiZapret"
    secret_key: str = "change-me-in-production-use-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./data/adminpanel.db"
    antizapret_path: Path = Path("/root/antizapret")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    default_admin_username: str = "admin"
    default_admin_password: str = "admin"
    allow_internal_nodes: bool = False
    node_agent_port: int = 9100
    backup_root: Path = Path("/var/backups/adminpanelaz")
    cidr_list_dir: Path = Path("data/cidr/list")
    traffic_sync_enabled: bool = True
    traffic_sync_interval_seconds: int = 30
    traffic_db_stale_seconds: int = 600
    cidr_db_refresh_enabled: bool = True
    cidr_db_refresh_hour: int = 2
    cidr_db_refresh_minute: int = 30
    antifilter_url: str = "https://antifilter.download/list/allyouneed.lst"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
