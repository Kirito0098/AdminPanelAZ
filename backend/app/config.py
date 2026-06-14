from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET_KEY = "change-me-in-production-use-long-random-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AdminPanel AntiZapret"
    app_env: str = "development"
    secret_key: str = _DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_token_cookie_name: str = "refresh_token"
    refresh_token_cookie_secure: bool = False
    refresh_token_cookie_samesite: str = "lax"
    require_production_secrets: bool = True
    enforce_password_policy: bool = False
    min_password_length: int = 8
    auth_rate_limit_enabled: bool = True
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 300
    auth_rate_limit_backend: str = "memory"
    api_rate_limit_enabled: bool = True
    api_rate_limit_max_requests: int = 120
    api_rate_limit_window_seconds: int = 60
    api_rate_limit_backend: str = "memory"
    redis_url: str = ""
    security_headers_enabled: bool = True
    enforce_https: bool = False
    hsts_max_age: int = 31536000
    content_security_policy: str = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; "
        "frame-src 'self' https://oauth.telegram.org; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self' https://oauth.telegram.org"
    )
    audit_log_enabled: bool = True
    database_url: str = "sqlite:///./data/adminpanel.db"
    cidr_database_url: str = "sqlite:///./data/cidr/cidr.db"
    antizapret_path: Path = Path("/root/antizapret")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    default_admin_username: str = "admin"
    default_admin_password: str = "admin"
    default_admin_must_change_password: bool = True
    allow_internal_nodes: bool = False
    local_antizapret_enabled: bool = True
    node_agent_port: int = 9100
    backup_root: Path = Path("/var/backups/adminpanelaz")
    cidr_list_dir: Path = Path("data/cidr/list")
    cidr_db_staging_dir: Path = Path("data/cidr/staging")
    cidr_db_csv_import_batch: int = 10_000
    cidr_db_csv_import_chunk_rows: int = 50_000
    cidr_db_keep_staging_csv: bool = False
    traffic_sync_enabled: bool = True
    traffic_sync_interval_seconds: int = 60
    traffic_limit_reconcile_after_sync: bool = True
    wg_policy_sync_enabled: bool = True
    wg_policy_sync_interval_seconds: int = 120
    node_health_sync_enabled: bool = True
    node_health_sync_interval_seconds: int = 60
    resource_metrics_enabled: bool = True
    resource_metrics_interval_seconds: int = 60
    resource_metrics_retention_days: int = 30
    panel_resource_metrics_enabled: bool = True
    panel_resource_metrics_interval_seconds: int = 60
    panel_resource_metrics_retention_days: int = 30
    monitor_cpu_threshold: int = 90
    monitor_ram_threshold: int = 90
    monitor_check_interval_seconds: int = 60
    monitor_cooldown_minutes: int = 30
    traffic_db_stale_seconds: int = 600
    monitoring_overview_cache_ttl_seconds: int = 20
    cert_sync_enabled: bool = True
    cert_sync_interval_seconds: int = 300
    node_active_health_cache_seconds: int = 45
    openvpn_socket_dir: Path = Path("/run/openvpn-server")
    openvpn_socket_timeout: float = 2.5
    openvpn_socket_idle_timeout: float = 0.12
    openvpn_log_tail_lines: int = 200
    openvpn_event_max_response_bytes: int = 524288
    cidr_db_refresh_enabled: bool = True
    cidr_db_refresh_hour: int = 2
    cidr_db_refresh_minute: int = 30
    cidr_db_compile_after_refresh: bool = False
    cidr_db_deploy_after_compile: bool = False
    cidr_db_deploy_target: str = "active"
    cidr_db_deploy_target_node_ids: str = ""
    antifilter_url: str = "https://antifilter.download/list/allyouneed.lst"
    serve_frontend: bool = False
    frontend_dist_path: Path = Path("../frontend/dist")
    domain: str = ""
    behind_nginx: bool = False
    trusted_proxy_ips: str = "127.0.0.1,::1"
    forwarded_allow_ips: str = "127.0.0.1,::1"
    node_agent_allowed_ips: str = ""
    node_agent_mtls_enabled: bool = False
    node_agent_mtls_dir: Path = Path("/etc/adminpanelaz/mtls")
    node_agent_mtls_ca_cert: str = "/etc/adminpanelaz/mtls/ca.crt"
    node_agent_mtls_client_cert: str = "/etc/adminpanelaz/mtls/panel.crt"
    node_agent_mtls_client_key: str = "/etc/adminpanelaz/mtls/panel.key"
    node_api_key_rotation_days: int = 0
    node_api_key_rotation_check_hours: int = 24
    active_web_session_tracking_enabled: bool = True
    active_web_session_ttl_seconds: int = 180
    active_web_session_touch_interval_seconds: int = 30
    nightly_idle_restart_enabled: bool = True
    nightly_idle_restart_cron: str = "0 4 * * *"
    admin_panel_az_service_name: str = "admin-panel-az.service"

    @field_validator("auth_rate_limit_backend", "api_rate_limit_backend")
    @classmethod
    def normalize_rate_limit_backend(cls, value: str) -> str:
        normalized = (value or "memory").strip().lower()
        if normalized not in {"memory", "redis"}:
            raise ValueError("Rate limit backend must be 'memory' or 'redis'")
        return normalized

    @field_validator("refresh_token_cookie_samesite")
    @classmethod
    def normalize_samesite(cls, value: str) -> str:
        normalized = (value or "lax").strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("REFRESH_TOKEN_COOKIE_SAMESITE must be lax, strict, or none")
        return normalized

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str) -> str:
        normalized = (value or "development").strip().lower()
        if normalized not in {"development", "production"}:
            raise ValueError("APP_ENV must be 'development' or 'production'")
        return normalized

    @field_validator("cidr_db_deploy_target")
    @classmethod
    def normalize_cidr_db_deploy_target(cls, value: str) -> str:
        normalized = (value or "active").strip().lower()
        if normalized not in {"active", "all_online", "node_ids"}:
            raise ValueError("CIDR_DB_DEPLOY_TARGET must be active, all_online, or node_ids")
        return normalized

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def node_agent_allowed_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.node_agent_allowed_ips.split(",") if ip.strip()]

    @property
    def cidr_db_deploy_target_node_id_list(self) -> list[int]:
        ids: list[int] = []
        for part in self.cidr_db_deploy_target_node_ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                continue
        return ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
