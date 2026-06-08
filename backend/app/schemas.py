from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import NodeStatus, UserRole, VpnType


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    web_session_id: str | None = None


class Login2FARequired(BaseModel):
    requires_2fa: bool = True
    temp_token: str


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: str | None = None
    captcha_text: str | None = None


class Login2FARequest(BaseModel):
    temp_token: str
    code: str = Field(min_length=6, max_length=16)


class TwoFASetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_data_url: str


class TwoFAEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TwoFADisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class TwoFAStatusResponse(BaseModel):
    enabled: bool
    backup_codes_remaining: int = 0


class TwoFABackupCodesResponse(BaseModel):
    backup_codes: list[str]


class NodeRotateKeyResponse(BaseModel):
    message: str
    node_id: int


class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.user
    theme: str = "dark"
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=4)


class UserUpdate(BaseModel):
    role: UserRole | None = None
    theme: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=4)


class UserResponse(UserBase):
    id: int
    must_change_password: bool
    totp_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=4)


class VpnConfigCreate(BaseModel):
    client_name: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    vpn_type: VpnType
    cert_expire_days: int | None = Field(default=3650, ge=1, le=3650)
    description: str | None = None
    owner_id: int | None = None


class VpnConfigUpdate(BaseModel):
    description: str | None = None
    cert_expire_days: int | None = Field(default=None, ge=1, le=3650)
    owner_id: int | None = None


class VpnConfigResponse(BaseModel):
    id: int
    client_name: str
    vpn_type: VpnType
    owner_id: int
    owner_username: str | None = None
    cert_expire_days: int | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    profile_files: list[dict[str, str]] = []

    model_config = {"from_attributes": True}


class ProfileFile(BaseModel):
    protocol: str
    variant: str
    filename: str
    path: str
    content: str | None = None


class MonitoringService(BaseModel):
    name: str
    status: str
    active: bool
    description: str | None = None


class OpenVpnClient(BaseModel):
    common_name: str
    real_address: str
    virtual_address: str
    bytes_received: int
    bytes_sent: int
    connected_since: str
    connected_since_ts: int = 0
    profile: str | None = None
    data_source: str = "status_log"


class WireGuardPeer(BaseModel):
    interface: str
    public_key: str
    endpoint: str | None = None
    allowed_ips: str | None = None
    latest_handshake: str | None = None
    transfer_rx: int = 0
    transfer_tx: int = 0
    client_name: str | None = None


class MonitoringOverview(BaseModel):
    services: list[MonitoringService]
    openvpn_clients: list[OpenVpnClient]
    wireguard_peers: list[WireGuardPeer]
    server_ip: str | None = None
    timestamp: datetime
    node_id: int | None = None
    node_name: str | None = None
    openvpn_data_source: str = "status_log"


class ResourceHistoryPoint(BaseModel):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: int
    memory_total_mb: int
    disk_percent: float
    load_1: float | None = None
    load_5: float | None = None
    load_15: float | None = None


class ResourceHistoryResponse(BaseModel):
    node_id: int
    node_name: str
    period: str
    sample_count: int
    points: list[ResourceHistoryPoint]


class PanelResourceHistoryPoint(BaseModel):
    timestamp: datetime
    backend_cpu_percent: float
    backend_memory_mb: int
    backend_workers: int
    nginx_memory_mb: int | None = None
    total_panel_memory_mb: int


class PanelResourceHistoryResponse(BaseModel):
    period: str
    sample_count: int
    points: list[PanelResourceHistoryPoint]


class PanelResourceCurrentResponse(BaseModel):
    timestamp: datetime
    backend_cpu_percent: float
    backend_memory_mb: int
    backend_rss_mb: int
    backend_workers: int
    nginx_memory_mb: int | None = None
    watchdog_memory_mb: int | None = None
    frontend_dev_memory_mb: int | None = None
    total_panel_memory_mb: int
    frontend_note: str


class AppSettingsResponse(BaseModel):
    theme: str
    app_name: str
    antizapret_path: str
    include_hosts: str = ""
    exclude_hosts: str = ""
    include_ips: str = ""
    exclude_ips: str = ""
    allow_ips: str = ""
    node_id: int | None = None
    node_name: str | None = None


class AppSettingsUpdate(BaseModel):
    theme: str | None = None
    include_hosts: str | None = None
    exclude_hosts: str | None = None
    include_ips: str | None = None
    exclude_ips: str | None = None
    allow_ips: str | None = None


class DashboardSummary(BaseModel):
    total_configs: int
    openvpn_configs: int
    wireguard_configs: int
    connected_openvpn: int
    connected_wireguard: int
    active_services: int
    total_services: int
    server_ip: str | None = None
    node_name: str | None = None


class BackupEntry(BaseModel):
    file_name: str
    size_bytes: int
    created_at: str
    components: list[str] = []
    summary: str = ""


class BackupCreateRequest(BaseModel):
    include_configs: bool = False
    include_antizapret_backup: bool = False


class BackupRestoreRequest(BaseModel):
    file_name: str


class BackupSettingsResponse(BaseModel):
    auto_backup_enabled: bool = False
    auto_backup_days: int = 7
    telegram_on_backup: bool = False
    backup_az_enabled: bool = True
    retention_count: int = 5


class BackupSettingsUpdate(BaseModel):
    auto_backup_enabled: bool | None = None
    auto_backup_days: int | None = Field(default=None, ge=1, le=90)
    telegram_on_backup: bool | None = None
    backup_az_enabled: bool | None = None
    retention_count: int | None = Field(default=None, ge=1, le=30)


class MonitorSettingsResponse(BaseModel):
    cpu_threshold: int = 90
    ram_threshold: int = 90
    interval_seconds: int = 60
    cooldown_minutes: int = 30


class MonitorSettingsUpdate(BaseModel):
    cpu_threshold: int | None = Field(default=None, ge=1, le=100)
    ram_threshold: int | None = Field(default=None, ge=1, le=100)
    interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    cooldown_minutes: int | None = Field(default=None, ge=1, le=1440)


class ChangelogSection(BaseModel):
    title: str
    items: list[str]


class LatestChangelogResponse(BaseModel):
    success: bool = True
    version: str = ""
    date: str = ""
    sections: list[ChangelogSection] = []
    message: str = ""


class TelegramSettingsResponse(BaseModel):
    bot_token_set: bool = False
    chat_id: str = ""
    notify_enabled: bool = False
    notify_on_backup: bool = False


class TelegramSettingsUpdate(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None
    notify_enabled: bool | None = None
    notify_on_backup: bool | None = None


class AdminNotifyEventItem(BaseModel):
    key: str
    label: str
    enabled: bool


class AdminNotifySettingsResponse(BaseModel):
    telegram_id: str = ""
    notify_enabled: bool = False
    bot_token_set: bool = False
    events: list[AdminNotifyEventItem]


class AdminNotifySettingsUpdate(BaseModel):
    telegram_id: str | None = None
    events: dict[str, bool] | None = None


class VpnNetworkEnvRow(BaseModel):
    label: str
    value: str
    mono: bool = True


class VpnNetworkPublishModeInfo(BaseModel):
    key: str
    title: str
    description: str
    requires_domain: bool = False
    requires_email: bool = False
    warning: str | None = None


class VpnNetworkPublishRequest(BaseModel):
    mode: str = Field(pattern=r"^(http_direct|nginx_le|nginx_selfsigned)$")
    backend_port: int = Field(default=8000, ge=1, le=65535)
    domain: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    https_public_port: int = Field(default=443, ge=1, le=65535)
    http_acme_port: int = Field(default=80, ge=1, le=65535)


class VpnNetworkSettingsResponse(BaseModel):
    mode_key: str
    mode_title: str
    bullet_points: list[str]
    internal_url: str
    primary_urls: list[dict[str, str]]
    env_rows: list[VpnNetworkEnvRow]
    backend_port: str
    nginx_setup_hint: str = "scripts/nginx-setup.sh"
    publish_modes: list[VpnNetworkPublishModeInfo] = []


class ServiceRestartRequest(BaseModel):
    service_name: str


class MessageResponse(BaseModel):
    message: str
    detail: Any | None = None


class BackgroundTaskResponse(BaseModel):
    success: bool = True
    task_id: str
    task_type: str
    status: str
    message: str | None = None
    progress_percent: int = 0
    progress_stage: str | None = None
    output: str | None = None
    error: str | None = None
    result: Any | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    queued: bool | None = None
    status_url: str | None = None


class NodeBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=9100, ge=1, le=65535)


class NodeCreate(NodeBase):
    api_key: str | None = Field(default=None, min_length=8)


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    api_key: str | None = Field(default=None, min_length=8)


class NodeResponse(NodeBase):
    id: int
    status: NodeStatus
    is_local: bool
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NodeHealthResponse(BaseModel):
    node_id: int
    status: NodeStatus
    health: dict[str, Any] = {}
    last_seen_at: datetime | None = None


class ActiveNodeResponse(BaseModel):
    node: NodeResponse
    active: bool = True


class NodeUpdateRequest(BaseModel):
    scope: str = Field(default="all", pattern="^(all|agent|antizapret)$")
    run_doall: bool = True


class NodeUpdatesResponse(BaseModel):
    node_id: int
    agent: dict[str, Any] = {}
    antizapret: dict[str, Any] = {}


class NodeUpdateResult(BaseModel):
    node_id: int
    success: bool
    message: str
    restarting: bool = False
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    errors: list[str] = []


class CidrProviderInfo(BaseModel):
    filename: str
    name: str
    description: str = ""
    category: str = ""
    enabled: bool = False
    has_source: bool = False
    cidr_count: int = 0


class CidrPresetInfo(BaseModel):
    key: str
    name: str
    description: str = ""
    providers: list[str] = []


class CidrProviderMetaLite(BaseModel):
    name: str
    category: str = ""
    tags: list[str] = []


class CidrPresetSettings(BaseModel):
    region_scopes: list[str] = ["all"]
    include_non_geo_fallback: bool = False
    exclude_ru_cidrs: bool = False


class CidrDbPresetInfo(BaseModel):
    id: int
    key: str
    name: str
    description: str = ""
    is_builtin: bool
    providers: list[str]
    settings: CidrPresetSettings = CidrPresetSettings()
    sort_order: int = 0
    created_at: str
    updated_at: str
    providers_meta: dict[str, CidrProviderMetaLite] | None = None


class CidrPresetCreateRequest(BaseModel):
    name: str
    description: str = ""
    providers: list[str]
    settings: CidrPresetSettings | None = None


class CidrPresetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    providers: list[str] | None = None
    settings: CidrPresetSettings | None = None


class RouteStatsInfo(BaseModel):
    config_include_total: int = 0
    config_include_per_file: dict[str, int] = {}
    result_route_ips_count: int = 0
    result_route_ips_exists: bool = False


class RoutingOverview(BaseModel):
    providers: list[CidrProviderInfo]
    presets: list[CidrPresetInfo]
    route_stats: RouteStatsInfo
    list_dir: str = ""
    config_dir: str = ""
    timestamp: datetime | None = None
    node_id: int | None = None
    node_name: str | None = None


class AntizapretSettingFieldSchema(BaseModel):
    key: str
    html_id: str
    type: Literal["flag", "string"]
    env: str
    param_label: str = ""
    title: str = ""
    description: str = ""


class AntizapretSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    settings: dict[str, str]
    param_schema: list[AntizapretSettingFieldSchema] = Field(alias="schema")
    node_id: int | None = None
    node_name: str | None = None


class AntizapretSettingsUpdateResponse(BaseModel):
    success: bool = True
    message: str
    changes: int
    needs_apply: bool


class TrafficClientRow(BaseModel):
    common_name: str
    protocol_type: str
    total_received: int = 0
    total_sent: int = 0
    total_bytes: int = 0
    total_received_vpn: int = 0
    total_sent_vpn: int = 0
    total_bytes_vpn: int = 0
    total_received_antizapret: int = 0
    total_sent_antizapret: int = 0
    total_bytes_antizapret: int = 0
    traffic_1d: int = 0
    traffic_7d: int = 0
    traffic_30d: int = 0
    total_sessions: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    is_active: bool = False


class TrafficSummary(BaseModel):
    users_count: int = 0
    active_users_count: int = 0
    total_received: int = 0
    total_sent: int = 0
    total_received_vpn: int = 0
    total_sent_vpn: int = 0
    total_received_antizapret: int = 0
    total_sent_antizapret: int = 0
    latest_sample_at: str | None = None
    db_age_seconds: int | None = None
    db_is_stale: bool = False


class TrafficOverview(BaseModel):
    rows: list[TrafficClientRow]
    summary: TrafficSummary
    timestamp: datetime
    node_id: int | None = None
    node_name: str | None = None
