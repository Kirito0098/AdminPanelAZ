from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
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
        "script-src 'self' https://telegram.org https://oauth.telegram.org; "
        "style-src 'self'; "
        "style-src-attr 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss:; "
        "frame-src 'self' https://oauth.telegram.org; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self' https://oauth.telegram.org"
    )
    csp_relaxed_dev: bool = False
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "AdminPanel AntiZapret"
    webauthn_origin: str = ""
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
    node_sync_reconcile_enabled: bool = True
    node_sync_reconcile_interval_seconds: int = 600
    node_sync_auto_replicate_config_files: bool = True
    node_sync_auto_replicate_policies: bool = True
    node_sync_auto_heal: bool = False
    node_sync_auto_heal_max_failures: int = 3
    node_sync_replicate_doall: bool = True
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
    monitor_sustained_seconds: int = 180
    traffic_db_stale_seconds: int = 600
    monitoring_overview_cache_ttl_seconds: int = 45
    cert_sync_enabled: bool = True
    cert_sync_interval_seconds: int = 300
    self_service_reminder_enabled: bool = True
    self_service_reminder_interval_seconds: int = 3600
    self_service_reminder_cert_days_threshold: int = 7
    self_service_traffic_warning_percent: int = 90
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
    uvicorn_workers: int = 1
    resource_profile: str = "standard"
    retention_enabled: bool = True
    retention_interval_hours: int = 24
    traffic_sample_retention_days: int = 90
    action_log_retention_days: int = 365
    retention_batch_size: int = 5000
    health_deep_node_ping: bool = True
    health_deep_node_ping_timeout_seconds: float = 3.0
    bulk_config_op_max_workers: int = 4
    telegram_bot_command_rate_limit_enabled: bool = True
    geoip_city_mmdb_path: Path = Path("data/geoip/GeoLite2-City.mmdb")
    geoip_asn_mmdb_path: Path = Path("data/geoip/GeoLite2-ASN.mmdb")
    noc_report_enabled: bool = True
    noc_report_check_interval_seconds: int = 60
    noc_report_daily_cron: str = "0 8 * * *"
    noc_report_weekly_cron: str = "0 9 * * 1"
    noc_report_weekly_image_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "noc_report_weekly_image_enabled",
            "noc_report_weekly_pdf_enabled",
        ),
    )
    noc_report_weekly_image_tg_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "noc_report_weekly_image_tg_enabled",
            "noc_report_weekly_pdf_tg_enabled",
        ),
    )
    noc_report_weekly_image_top_clients: int = Field(
        default=10,
        validation_alias=AliasChoices(
            "noc_report_weekly_image_top_clients",
            "noc_report_weekly_pdf_top_clients",
        ),
    )
    alert_rules_enabled: bool = True
    alert_rules_check_interval_seconds: int = 60
    openapi_docs_enabled: bool = True
    openapi_docs_allowed_ips: str = ""
    config_csv_import_async_threshold: int = 100
    event_webhook_timeout_seconds: float = 5.0
    event_webhook_max_attempts: int = 5
    event_webhook_retry_interval_seconds: int = 60

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
    def openapi_docs_allowed_ip_list(self) -> list[str]:
        return [ip.strip() for ip in self.openapi_docs_allowed_ips.split(",") if ip.strip()]

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
