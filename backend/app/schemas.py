from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import NodeStatus, SyncStatus, UserRole, VpnType


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    web_session_id: str | None = None


class Login2FARequired(BaseModel):
    requires_2fa: bool = True
    temp_token: str
    passkey_available: bool = False


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


class PasskeyRegisterOptionsResponse(BaseModel):
    options: dict[str, Any]


class PasskeyRegisterVerifyRequest(BaseModel):
    credential: dict[str, Any]
    session_key: str
    nickname: str | None = Field(default=None, max_length=128)


class PasskeyAuthOptionsRequest(BaseModel):
    temp_token: str


class PasskeyAuthVerifyRequest(BaseModel):
    temp_token: str
    credential: dict[str, Any]
    session_key: str


class PasskeyCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str
    created_at: datetime
    last_used_at: datetime | None = None


class PasskeyListResponse(BaseModel):
    credentials: list[PasskeyCredentialResponse]
    count: int


class PasskeyRenameRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=128)


class NodeRotateKeyResponse(BaseModel):
    message: str
    node_id: int


class NodeMtlsEnableResponse(BaseModel):
    message: str
    node_id: int
    mtls_enabled: bool = True


class NodeMtlsDisableResponse(BaseModel):
    message: str
    node_id: int
    mtls_enabled: bool = False
    warning: str | None = None


class NodeMtlsStatusResponse(BaseModel):
    ready: bool
    writable: bool
    mtls_dir: str
    ca_cert: str
    panel_cert: str
    panel_key: str
    agent_certs_count: int = 0


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
    telegram_id: str | None = None
    config_quota: int | None = Field(default=None, ge=0, le=1000)


class UserResponse(UserBase):
    id: int
    must_change_password: bool
    totp_enabled: bool = False
    telegram_id: str | None = None
    config_quota: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SelfServiceQuotaResponse(BaseModel):
    used: int
    limit: int | None = None
    remaining: int | None = None
    unlimited: bool = False
    can_create: bool = True
    create_rate_max: int | None = None
    create_rate_window_seconds: int | None = None


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


class VpnConfigHaInfo(BaseModel):
    sync_group_id: int
    shared_domain: str
    node_count: int
    sync_status: SyncStatus
    sync_mode: str


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
    tags: list["ConfigTagResponse"] = []
    ha: VpnConfigHaInfo | None = None

    model_config = {"from_attributes": True}


class ConfigTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default="#6366f1", max_length=16)


class ConfigTagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class ConfigTagResponse(BaseModel):
    id: int
    name: str
    color: str | None = None
    config_count: int = 0

    model_config = {"from_attributes": True}


class ConfigTagsAssignRequest(BaseModel):
    tag_ids: list[int] = Field(default_factory=list)


class ClientTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    vpn_type: VpnType
    cert_expire_days: int | None = Field(default=None, ge=1, le=3650)
    traffic_limit_value: float | None = Field(default=None, gt=0)
    traffic_limit_unit: str | None = Field(default=None, max_length=8)
    traffic_limit_period_days: int | None = Field(default=None, ge=1, le=3650)
    description_template: str | None = Field(default=None, max_length=255)
    sort_order: int = 0


class ClientTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    cert_expire_days: int | None = Field(default=None, ge=1, le=3650)
    traffic_limit_value: float | None = Field(default=None, gt=0)
    traffic_limit_unit: str | None = Field(default=None, max_length=8)
    traffic_limit_period_days: int | None = Field(default=None, ge=1, le=3650)
    description_template: str | None = Field(default=None, max_length=255)
    sort_order: int | None = None


class ClientTemplateResponse(BaseModel):
    id: int
    name: str
    vpn_type: VpnType
    cert_expire_days: int | None
    traffic_limit_value: float | None
    traffic_limit_unit: str | None
    traffic_limit_period_days: int | None
    description_template: str | None
    sort_order: int
    is_builtin: bool

    model_config = {"from_attributes": True}


class ClientTemplateApplyRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    owner_id: int | None = None


class BulkConfigOpRequest(BaseModel):
    operation: Literal["block_temp", "block_perm", "unblock", "delete", "renew_cert"]
    config_ids: list[int] = Field(default_factory=list)
    tag_ids: list[int] = Field(default_factory=list)
    block_days: int | None = Field(default=7, ge=1, le=3650)
    renew_cert_days: int | None = Field(default=3650, ge=1, le=3650)


class ActiveWebSessionResponse(BaseModel):
    session_id: str
    username: str
    remote_addr: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    is_current: bool = False

    model_config = {"from_attributes": True}


class BulkConfigOpQueuedResponse(BaseModel):
    task_id: str
    queued: bool = True
    status_url: str


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
    display_address: str | None = None
    client_ip: str | None = None
    city: str | None = None
    country: str | None = None
    isp: str | None = None
    location_label: str | None = None
    geo_label: str | None = None
    node_id: int | None = None
    node_name: str | None = None
    ha: VpnConfigHaInfo | None = None


class WireGuardPeer(BaseModel):
    interface: str
    public_key: str
    endpoint: str | None = None
    allowed_ips: str | None = None
    latest_handshake: str | None = None
    transfer_rx: int = 0
    transfer_tx: int = 0
    client_name: str | None = None
    display_address: str | None = None
    client_ip: str | None = None
    city: str | None = None
    country: str | None = None
    isp: str | None = None
    location_label: str | None = None
    geo_label: str | None = None
    node_id: int | None = None
    node_name: str | None = None
    ha: VpnConfigHaInfo | None = None


class MonitoringNodeSummary(BaseModel):
    node_id: int
    node_name: str
    status: str
    connected_openvpn: int = 0
    connected_wireguard: int = 0
    active_services: int = 0
    total_services: int = 0
    cpu_percent: float | None = None
    memory_percent: float | None = None
    total_traffic_bytes: int | None = None
    cidr_routes_count: int | None = None
    error: str | None = None


class GeoRoutingNodeHint(BaseModel):
    node_id: int
    node_name: str
    status: str
    server_ip: str | None = None
    country: str | None = None
    city: str | None = None
    geo_label: str | None = None
    is_recommended: bool = False


class GeoRoutingHintResponse(BaseModel):
    client_ip: str | None = None
    client_country: str | None = None
    client_city: str | None = None
    client_geo_label: str | None = None
    recommended_node_id: int | None = None
    recommended_node_name: str | None = None
    hint_message: str | None = None
    nodes: list[GeoRoutingNodeHint] = Field(default_factory=list)


class NodeDefaultLimits(BaseModel):
    limit_value: float | None = None
    limit_unit: str | None = None
    limit_period_days: int | None = None
    limit_human: str | None = None
    limit_period_label: str | None = None


class NodeDefaultPolicyResponse(BaseModel):
    node_id: int
    node_name: str
    route_mode: str | None = None
    openvpn: NodeDefaultLimits = Field(default_factory=NodeDefaultLimits)
    wireguard: NodeDefaultLimits = Field(default_factory=NodeDefaultLimits)
    updated_at: datetime | None = None
    updated_by: str | None = None


class NodeDefaultPolicyUpdate(BaseModel):
    route_mode: str | None = None
    openvpn_limit_value: float | None = Field(default=None, gt=0)
    openvpn_limit_unit: str | None = "GB"
    openvpn_limit_period_days: int | None = None
    openvpn_clear_limit: bool = False
    wireguard_limit_value: float | None = Field(default=None, gt=0)
    wireguard_limit_unit: str | None = "GB"
    wireguard_limit_period_days: int | None = None
    wireguard_clear_limit: bool = False


class NodePolicySummary(BaseModel):
    node_id: int
    node_name: str
    openvpn_policies: int = 0
    wireguard_policies: int = 0
    blocked_clients: int = 0
    traffic_limited_clients: int = 0
    default_openvpn_limit_human: str | None = None
    default_wireguard_limit_human: str | None = None
    default_route_mode: str | None = None


class GlobalDashboardSummary(BaseModel):
    timestamp: datetime
    nodes_summary: list[MonitoringNodeSummary] = Field(default_factory=list)
    nodes_online: int = 0
    nodes_total: int = 0
    total_connected_openvpn: int = 0
    total_connected_wireguard: int = 0


class MonitoringOverview(BaseModel):
    services: list[MonitoringService]
    openvpn_clients: list[OpenVpnClient]
    wireguard_peers: list[WireGuardPeer]
    server_ip: str | None = None
    timestamp: datetime
    node_id: int | None = None
    node_name: str | None = None
    openvpn_data_source: str = "status_log"
    scope: str = "node"
    nodes_summary: list[MonitoringNodeSummary] = Field(default_factory=list)
    nodes_online: int = 0
    nodes_total: int = 0
    total_connected_openvpn: int = 0
    total_connected_wireguard: int = 0


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
    watchdog_memory_mb: int | None = None
    frontend_dev_memory_mb: int | None = None
    total_panel_memory_mb: int
    host_cpu_percent: float = 0.0
    host_memory_percent: float = 0.0
    host_memory_used_mb: int = 0
    host_memory_total_mb: int = 0
    host_disk_percent: float = 0.0
    host_load_1: float | None = None


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
    host_cpu_percent: float = 0.0
    host_memory_percent: float = 0.0
    host_memory_used_mb: int = 0
    host_memory_total_mb: int = 0
    host_disk_percent: float = 0.0
    host_load_1: float | None = None
    host_hostname: str = ""
    host_uptime: str = ""


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


class AlertMetricInfo(BaseModel):
    id: str
    label: str
    requires_node: bool = False


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    metric: str
    operator: str
    threshold: float
    node_id: int | None = None
    cooldown_minutes: int
    enabled: bool
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    metric: str
    operator: str = "gt"
    threshold: float
    node_id: int | None = None
    cooldown_minutes: int = Field(default=30, ge=1, le=1440)
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    metric: str | None = None
    operator: str | None = None
    threshold: float | None = None
    node_id: int | None = None
    cooldown_minutes: int | None = Field(default=None, ge=1, le=1440)
    enabled: bool | None = None


class AlertRuleEvaluateResult(BaseModel):
    rule_id: int
    name: str
    metric: str
    value: float | None = None
    threshold: float
    operator: str
    triggered: bool
    skipped_reason: str | None = None


class AlertRuleEvaluateResponse(BaseModel):
    evaluated: int
    triggered: int
    results: list[AlertRuleEvaluateResult]


class GeoIpStatusResponse(BaseModel):
    loaded: bool
    source: Literal["local", "ip-api"]
    city_mmdb_path: str | None = None
    asn_mmdb_path: str | None = None
    city_mmdb_exists: bool = False
    asn_mmdb_exists: bool = False


class RetentionSettingsResponse(BaseModel):
    enabled: bool = True
    interval_hours: int = 24
    traffic_sample_retention_days: int = 90
    action_log_retention_days: int = 365
    resource_metrics_retention_days: int = 30
    panel_resource_metrics_retention_days: int = 30


class RetentionSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=168)
    traffic_sample_retention_days: int | None = Field(default=None, ge=1, le=3650)
    action_log_retention_days: int | None = Field(default=None, ge=1, le=3650)
    resource_metrics_retention_days: int | None = Field(default=None, ge=1, le=3650)
    panel_resource_metrics_retention_days: int | None = Field(default=None, ge=1, le=3650)


class SecretRotationItemResponse(BaseModel):
    secret_id: str
    label: str
    description: str
    storage: str
    env_key: str | None = None
    env_path: str | None = None
    configured: bool
    masked_current: str
    auto_generate: bool
    requires_restart: bool
    requires_relogin: bool


class SecretRotationEnvChangePreview(BaseModel):
    path: str
    key: str
    masked_new_value: str


class SecretRotationPreviewResponse(BaseModel):
    secret_id: str
    label: str
    new_value: str
    masked_new_value: str
    masked_current: str
    preview_token: str
    confirm_phrase: str
    warnings: list[str]
    env_change: SecretRotationEnvChangePreview | None = None
    storage: str
    requires_relogin: bool
    requires_restart: bool


class SecretRotationPreviewRequest(BaseModel):
    secret_id: str
    value: str | None = None


class SecretRotationApplyRequest(BaseModel):
    secret_id: str
    new_value: str
    preview_token: str
    confirm: str = Field(min_length=1)


class SecretRotationApplyResponse(BaseModel):
    secret_id: str
    label: str
    message: str
    requires_relogin: bool
    next_steps: list[str]
    reencrypt_stats: dict[str, int] | None = None


class RouteBudgetInfo(BaseModel):
    available: bool = False
    limit: int | None = None
    used: int | None = None
    remaining: int | None = None
    original_total: int | None = None
    warning: str | None = None
    strategy: str | None = None
    task_id: str | None = None
    finished_at: str | None = None
    status: str | None = None
    message: str | None = None


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
    bot_username: str = ""
    auth_max_age_seconds: int = 300
    mini_app_url: str = ""
    chat_id: str = ""
    notify_enabled: bool = False
    notify_on_backup: bool = False
    interactive_enabled: bool = False
    webhook_registered: bool = False
    webhook_secret_set: bool = False
    webhook_set_at: str = ""


class TelegramSettingsUpdate(BaseModel):
    bot_token: str | None = None
    bot_username: str | None = None
    auth_max_age_seconds: int | None = Field(default=None, ge=30, le=86400)
    chat_id: str | None = None
    notify_enabled: bool | None = None
    notify_on_backup: bool | None = None
    interactive_enabled: bool | None = None


class TelegramLinkCodeResponse(BaseModel):
    code: str
    expires_in_seconds: int


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
    mtls_enabled: bool = False
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
    pass


class NodeUpdateRollRequest(BaseModel):
    node_ids: list[int]


class NodeUpdatesResponse(BaseModel):
    node_id: int
    agent: dict[str, Any] = {}


class NodeUpdateResult(BaseModel):
    node_id: int
    success: bool
    message: str
    restarting: bool = False
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    detail: dict[str, Any] = {}
    errors: list[str] = []


class NodeSyncGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    shared_domain: str = Field(min_length=1, max_length=255)
    primary_node_id: int = Field(ge=1)
    replica_node_ids: list[int] = Field(min_length=1)
    sync_mode: str = Field(default="manual_full", max_length=32)


class NodeSyncGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    shared_domain: str | None = Field(default=None, min_length=1, max_length=255)
    primary_node_id: int | None = Field(default=None, ge=1)
    replica_node_ids: list[int] | None = None
    sync_mode: str | None = Field(default=None, max_length=32)


class NodeSyncMismatch(BaseModel):
    kind: str
    only_primary: list[str] = []
    only_replica: list[str] = []
    path: str | None = None
    primary: str | None = None
    replica: str | None = None
    detail: str | None = None


class NodeSyncReplicaVerifyResult(BaseModel):
    node_id: int
    node_name: str | None = None
    online: bool = True
    mismatches: list[NodeSyncMismatch] = []


class NodeSyncVerifyResponse(BaseModel):
    ready: bool
    shared_domain: str
    primary_node_id: int
    replicas: list[NodeSyncReplicaVerifyResult] = []
    summary: str = ""


class NodeSyncGroupResponse(BaseModel):
    id: int
    name: str
    shared_domain: str
    primary_node_id: int
    primary_node_name: str | None = None
    replica_node_ids: list[int] = []
    replica_node_names: list[str] = []
    sync_mode: str
    sync_status: SyncStatus
    last_sync_at: datetime | None = None
    last_verify_at: datetime | None = None
    last_sync_task_id: str | None = None
    last_sync_error: str | None = None
    last_verify_result: NodeSyncVerifyResponse | dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class NodeSyncGroupStatusResponse(BaseModel):
    group_id: int
    sync_status: SyncStatus
    last_sync_at: datetime | None = None
    last_verify_at: datetime | None = None
    last_sync_task_id: str | None = None
    last_sync_error: str | None = None
    progress_percent: int | None = None
    progress_stage: str | None = None


class NodeSyncPushFullResponse(BaseModel):
    task_id: str
    group_id: int
    message: str
    queued: bool = True
    status_url: str | None = None


class CidrProviderInfo(BaseModel):
    filename: str
    name: str
    description: str = ""
    category: str = ""
    enabled: bool = False
    has_source: bool = False
    cidr_count: int = 0


class RouteStatsInfo(BaseModel):
    config_include_total: int = 0
    config_include_per_file: dict[str, int] = {}
    result_route_ips_count: int = 0
    result_route_ips_exists: bool = False


class RoutingOverview(BaseModel):
    providers: list[CidrProviderInfo]
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


class WarperHealthResponse(BaseModel):
    installed: bool
    active: bool = False
    version: str | None = None
    conflict_antizapret_warp: bool = False
    health_error: str | None = None
    warper_bin: bool | None = None
    warper_script: bool | None = None
    warper_api: bool | None = None
    missing_components: list[str] = Field(default_factory=list)
    node_id: int | None = None
    node_name: str | None = None
    node_host: str | None = None


class WarperStatusResponse(BaseModel):
    status: dict
    node_id: int | None = None
    node_name: str | None = None


class WarperDomainItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    domain: str | None = None
    name: str | None = None
    type: str | None = None
    status: str | None = None


class WarperDomainCreate(BaseModel):
    domain: str = Field(..., min_length=1)


class WarperDomainListsStatus(BaseModel):
    gemini: bool = False
    chatgpt: bool = False


class WarperDomainsResponse(BaseModel):
    domains: list[WarperDomainItem | dict]
    lists: WarperDomainListsStatus = Field(default_factory=WarperDomainListsStatus)
    node_id: int | None = None
    node_name: str | None = None


class WarperDoctorResponse(BaseModel):
    items: list[dict]
    passed: bool | None = None
    summary: dict[str, int] | None = None
    node_id: int | None = None
    node_name: str | None = None


class WarperActionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str | None = None
    success: bool | None = None
    node_id: int | None = None
    node_name: str | None = None


class WarperDomainsBulkCreate(BaseModel):
    domains: list[str] = Field(default_factory=list)


class WarperDomainsBulkResponse(BaseModel):
    added: list[str] = Field(default_factory=list)
    added_count: int = 0
    errors: list[dict[str, str]] = Field(default_factory=list)
    node_id: int | None = None
    node_name: str | None = None


class WarperDomainListToggle(BaseModel):
    enable: bool


class WarperIpRangeCreate(BaseModel):
    cidr: str = Field(..., min_length=1)


class WarperIpRangesResponse(BaseModel):
    ranges: list[str | dict]
    node_id: int | None = None
    node_name: str | None = None


class WarperIpRangeModeUpdate(BaseModel):
    mode: str = Field(..., min_length=1)


class WarperIpExportUpdate(BaseModel):
    enable: bool


class WarperTrafficResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: dict = Field(default_factory=dict)
    node_id: int | None = None
    node_name: str | None = None


class WarperLogsResponse(BaseModel):
    lines: list[str] = Field(default_factory=list)
    node_id: int | None = None
    node_name: str | None = None


class WarperModeResponse(BaseModel):
    mode: dict = Field(default_factory=dict)
    node_id: int | None = None
    node_name: str | None = None


class WarperMtuUpdate(BaseModel):
    mtu: int = Field(..., ge=1280, le=1500)


class WarperLogLevelUpdate(BaseModel):
    level: str = Field(..., min_length=1)


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


class TrafficSessionSourceRow(BaseModel):
    client_ip: str
    display_address: str | None = None
    city: str | None = None
    country: str | None = None
    isp: str | None = None
    location_label: str | None = None
    geo_label: str | None = None
    sessions_count: int = 0
    virtual_addresses: list[str] = Field(default_factory=list)
    total_bytes: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    is_active: bool = False
    share_percent: float = 0.0


class TrafficSessionItem(BaseModel):
    profile: str = "unknown"
    real_address: str | None = None
    virtual_address: str | None = None
    connected_since_at: str | None = None
    last_seen_at: str | None = None
    ended_at: str | None = None
    duration_seconds: int | None = None
    bytes_received: int = 0
    bytes_sent: int = 0
    total_bytes: int = 0
    is_active: bool = False


class TrafficClientSessionsResponse(BaseModel):
    client: str
    total_sessions: int = 0
    unique_sources: int = 0
    unique_virtual_addresses: int = 0
    by_source: list[TrafficSessionSourceRow] = Field(default_factory=list)
    recent_sessions: list[TrafficSessionItem] = Field(default_factory=list)
    node_id: int | None = None
    node_name: str | None = None
