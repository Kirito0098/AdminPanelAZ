export type UserRole = 'admin' | 'user' | 'viewer'
export type VpnType = 'openvpn' | 'wireguard'
export type NodeStatus = 'online' | 'offline' | 'unknown'

export interface Node {
  id: number
  name: string
  host: string
  port: number
  status: NodeStatus
  is_local: boolean
  mtls_enabled: boolean
  last_seen_at?: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ActiveNode {
  node: Node
  active: boolean
}

export type SyncStatus = 'unknown' | 'synced' | 'pending' | 'failed'

export interface NodeSyncMismatch {
  kind: string
  only_primary?: string[]
  only_replica?: string[]
  path?: string | null
  primary?: string | null
  replica?: string | null
  detail?: string | null
}

export interface NodeSyncReplicaVerifyResult {
  node_id: number
  node_name?: string | null
  online: boolean
  mismatches: NodeSyncMismatch[]
}

export interface NodeSyncVerifyResult {
  ready: boolean
  shared_domain: string
  primary_node_id: number
  replicas: NodeSyncReplicaVerifyResult[]
  summary: string
}

export interface NodeSyncGroup {
  id: number
  name: string
  shared_domain: string
  primary_node_id: number
  primary_node_name?: string | null
  replica_node_ids: number[]
  replica_node_names: string[]
  sync_mode: string
  sync_status: SyncStatus
  last_sync_at?: string | null
  last_verify_at?: string | null
  last_sync_task_id?: string | null
  last_sync_error?: string | null
  last_verify_result?: NodeSyncVerifyResult | null
  created_at: string
  updated_at: string
}

export interface NodeSyncGroupStatus {
  group_id: number
  sync_status: SyncStatus
  last_sync_at?: string | null
  last_verify_at?: string | null
  last_sync_task_id?: string | null
  last_sync_error?: string | null
  progress_percent?: number | null
  progress_stage?: string | null
}

export interface NodeMtlsStatus {
  ready: boolean
  writable: boolean
  mtls_dir: string
  ca_cert: string
  panel_cert: string
  panel_key: string
  agent_certs_count: number
}

export interface User {
  id: number
  username: string
  role: UserRole
  theme: string
  is_active: boolean
  must_change_password: boolean
  totp_enabled?: boolean
  telegram_id?: string | null
  config_quota?: number | null
  created_at: string
}

export interface SelfServiceQuota {
  used: number
  limit: number | null
  remaining: number | null
  unlimited: boolean
  can_create: boolean
  create_rate_max?: number | null
  create_rate_window_seconds?: number | null
}

export interface ConfigTag {
  id: number
  name: string
  color?: string | null
  config_count?: number
}

export interface ClientTemplate {
  id: number
  name: string
  vpn_type: VpnType
  cert_expire_days?: number | null
  traffic_limit_value?: number | null
  traffic_limit_unit?: string | null
  traffic_limit_period_days?: number | null
  description_template?: string | null
  sort_order: number
  is_builtin: boolean
}

export interface ActiveWebSession {
  session_id: string
  username: string
  remote_addr?: string | null
  user_agent?: string | null
  created_at: string
  last_seen_at: string
  is_current: boolean
}

export interface VpnConfigHaInfo {
  sync_group_id: number
  shared_domain: string
  node_count: number
  sync_status: SyncStatus
  sync_mode: string
}

export interface VpnConfig {
  id: number
  client_name: string
  vpn_type: VpnType
  owner_id: number
  owner_username?: string
  cert_expire_days?: number | null
  description?: string | null
  created_at: string
  updated_at: string
  tags?: ConfigTag[]
  ha?: VpnConfigHaInfo | null
  profile_files: Array<{
    protocol: string
    variant: string
    filename: string
    path: string
    download_filename?: string
  }>
}

export interface MonitoringService {
  name: string
  status: string
  active: boolean
  description?: string | null
}

export interface OpenVpnClient {
  common_name: string
  real_address: string
  virtual_address: string
  bytes_received: number
  bytes_sent: number
  connected_since: string
  connected_since_ts?: number
  profile?: string | null
  data_source?: string
  display_address?: string | null
  client_ip?: string | null
  city?: string | null
  country?: string | null
  isp?: string | null
  location_label?: string | null
  geo_label?: string | null
  node_id?: number | null
  node_name?: string | null
  ha?: VpnConfigHaInfo | null
}

export interface WireGuardPeer {
  interface: string
  public_key: string
  endpoint?: string | null
  allowed_ips?: string | null
  latest_handshake?: string | null
  transfer_rx: number
  transfer_tx: number
  client_name?: string | null
  display_address?: string | null
  client_ip?: string | null
  city?: string | null
  country?: string | null
  isp?: string | null
  location_label?: string | null
  geo_label?: string | null
  node_id?: number | null
  node_name?: string | null
  ha?: VpnConfigHaInfo | null
}

export interface MonitoringNodeSummary {
  node_id: number
  node_name: string
  status: string
  connected_openvpn: number
  connected_wireguard: number
  active_services: number
  total_services: number
  cpu_percent?: number | null
  memory_percent?: number | null
  total_traffic_bytes?: number | null
  cidr_routes_count?: number | null
  error?: string | null
}

export interface GeoRoutingNodeHint {
  node_id: number
  node_name: string
  status: string
  server_ip?: string | null
  country?: string | null
  city?: string | null
  geo_label?: string | null
  is_recommended: boolean
}

export interface GeoRoutingHint {
  client_ip?: string | null
  client_country?: string | null
  client_city?: string | null
  client_geo_label?: string | null
  recommended_node_id?: number | null
  recommended_node_name?: string | null
  hint_message?: string | null
  nodes: GeoRoutingNodeHint[]
}

export interface NodePolicySummary {
  node_id: number
  node_name: string
  openvpn_policies: number
  wireguard_policies: number
  blocked_clients: number
  traffic_limited_clients: number
  default_openvpn_limit_human?: string | null
  default_wireguard_limit_human?: string | null
  default_route_mode?: string | null
}

export interface NodeDefaultLimits {
  limit_value?: number | null
  limit_unit?: string | null
  limit_period_days?: number | null
  limit_human?: string | null
  limit_period_label?: string | null
}

export interface NodeDefaultPolicy {
  node_id: number
  node_name: string
  route_mode?: string | null
  openvpn: NodeDefaultLimits
  wireguard: NodeDefaultLimits
  updated_at?: string | null
  updated_by?: string | null
}

export interface NodeDefaultPolicyUpdate {
  route_mode?: string | null
  openvpn_limit_value?: number | null
  openvpn_limit_unit?: string | null
  openvpn_limit_period_days?: number | null
  openvpn_clear_limit?: boolean
  wireguard_limit_value?: number | null
  wireguard_limit_unit?: string | null
  wireguard_limit_period_days?: number | null
  wireguard_clear_limit?: boolean
}

export interface GlobalDashboardSummary {
  timestamp: string
  nodes_summary: MonitoringNodeSummary[]
  nodes_online?: number
  nodes_total?: number
  total_connected_openvpn?: number
  total_connected_wireguard?: number
}

export interface MonitoringOverview {
  services: MonitoringService[]
  openvpn_clients: OpenVpnClient[]
  wireguard_peers: WireGuardPeer[]
  server_ip?: string | null
  timestamp: string
  node_id?: number | null
  node_name?: string | null
  openvpn_data_source?: string
  scope?: 'node' | 'all'
  nodes_summary?: MonitoringNodeSummary[]
  nodes_online?: number
  nodes_total?: number
  total_connected_openvpn?: number
  total_connected_wireguard?: number
}

export interface OpenVpnEventProfile {
  profile: string
  source_name: string
  exists: boolean
  updated_at_ts: number
  line_count: number
  recent_lines: string[]
}

export interface ConnectionLogsSnapshot {
  openvpn_clients: OpenVpnClient[]
  wireguard_peers: WireGuardPeer[]
  openvpn_data_source?: string
  timestamp: string
}

export interface AppSettings {
  theme: string
  app_name: string
  antizapret_path: string
  include_hosts: string
  exclude_hosts: string
  include_ips: string
  exclude_ips: string
  allow_ips: string
  node_id?: number | null
  node_name?: string | null
}

export interface DashboardSummary {
  total_configs: number
  openvpn_configs: number
  wireguard_configs: number
  connected_openvpn: number
  connected_wireguard: number
  active_services: number
  total_services: number
  server_ip?: string | null
  node_name?: string | null
}

export interface BackupEntry {
  file_name: string
  size_bytes: number
  created_at: string
  components: string[]
  summary: string
}

export interface BackupSettings {
  auto_backup_enabled: boolean
  auto_backup_days: number
  telegram_on_backup: boolean
  backup_az_enabled: boolean
  retention_count: number
}

export interface MonitorSettings {
  cpu_threshold: number
  ram_threshold: number
  interval_seconds: number
  cooldown_minutes: number
}

export interface AlertMetricInfo {
  id: string
  label: string
  requires_node: boolean
}

export interface AlertRule {
  id: number
  name: string
  metric: string
  operator: string
  threshold: number
  node_id: number | null
  cooldown_minutes: number
  enabled: boolean
  last_triggered_at: string | null
  created_at: string
  updated_at: string
}

export interface AlertRuleCreatePayload {
  name: string
  metric: string
  operator?: string
  threshold: number
  node_id?: number | null
  cooldown_minutes?: number
  enabled?: boolean
}

export interface RetentionSettings {
  enabled: boolean
  interval_hours: number
  traffic_sample_retention_days: number
  action_log_retention_days: number
  resource_metrics_retention_days: number
  panel_resource_metrics_retention_days: number
}

export interface GeoIpStatus {
  loaded: boolean
  source: 'local' | 'ip-api'
  city_mmdb_path: string | null
  asn_mmdb_path: string | null
  city_mmdb_exists: boolean
  asn_mmdb_exists: boolean
}

export interface RouteBudgetInfo {
  available: boolean
  limit?: number | null
  used?: number | null
  remaining?: number | null
  original_total?: number | null
  warning?: string | null
  strategy?: string | null
  task_id?: string | null
  finished_at?: string | null
  status?: string | null
  message?: string | null
}

export interface ResourceProfileImpact {
  ram?: string
  cpu_disk?: string
  note?: string
}

export interface ResourceProfileItem {
  key: string
  label: string
  description: string
  recommended_ram_gb?: number | null
  active: boolean
  impact?: ResourceProfileImpact
  workers_disabled?: string[]
}

export interface ResourceProfilesResponse {
  current_profile: string
  requires_restart: boolean
  items: ResourceProfileItem[]
}

export interface ChangelogSection {
  title: string
  items: string[]
}

export interface LatestChangelog {
  success: boolean
  version?: string
  date?: string
  sections?: ChangelogSection[]
  message?: string
}

export interface TelegramSettings {
  bot_token_set: boolean
  bot_username: string
  auth_max_age_seconds: number
  mini_app_url: string
  chat_id: string
  notify_enabled: boolean
  notify_on_backup: boolean
  interactive_enabled: boolean
  webhook_registered: boolean
  webhook_secret_set: boolean
  webhook_set_at: string
}

export interface TelegramLinkCode {
  code: string
  expires_in_seconds: number
}

export interface AdminNotifyEventItem {
  key: string
  label: string
  enabled: boolean
}

export interface AdminNotifySettings {
  telegram_id: string
  notify_enabled: boolean
  bot_token_set: boolean
  events: AdminNotifyEventItem[]
}

export interface TgMiniAuthResponse {
  access_token: string
  token_type: string
  telegram_id: string
}

export interface TgMiniDashboard {
  total_configs: number
  connected_openvpn: number
  connected_wireguard: number
  server_ip: string | null
  openvpn_clients: Array<{ common_name?: string; [key: string]: unknown }>
  wireguard_peers: Array<{
    client_name: string | null
    public_key: string
    transfer_rx: number
    transfer_tx: number
  }>
  timestamp: string
}

export interface TgMiniConfig {
  id: number
  client_name: string
  vpn_type: string
}

export interface TgMiniConfigFile {
  path: string
  filename?: string
  download_filename?: string
  protocol?: string
  variant?: string
}

export interface TgMiniSettings {
  server_ip: string | null
  bot_configured: boolean
  username: string
  role: string
}

export interface TgMiniNode extends Node {
  is_active: boolean
}

export interface TgMiniNodesResponse {
  active_node_id: number | null
  nodes: TgMiniNode[]
}

export interface TgMiniNodeActionResponse {
  node: TgMiniNode
  health: Record<string, unknown>
}

export interface TgMiniQrLink {
  url: string
  token: string
  expires_at: string
  max_downloads: number
  pin_required: boolean
}

export interface TgMiniWarperStatus {
  node_id: number
  node_name: string
  node_host: string
  status: string
  raw: Record<string, unknown>
}

export interface TgMiniCidrStatus {
  total_cidrs: number
  last_refresh_status?: string | null
  last_refresh_finished?: string | null
  active_task?: string | null
  last_compile?: Record<string, unknown> | null
  last_deploy?: Record<string, unknown> | null
}

export interface VpnNetworkEnvRow {
  label: string
  value: string
  mono: boolean
}

export interface VpnNetworkPublishMode {
  key: string
  title: string
  description: string
  requires_domain: boolean
  requires_email: boolean
  warning: string | null
}

export interface VpnNetworkSettings {
  mode_key: string
  mode_title: string
  bullet_points: string[]
  internal_url: string
  primary_urls: Array<{ label: string; url: string }>
  env_rows: VpnNetworkEnvRow[]
  backend_port: string
  nginx_setup_hint: string
  publish_modes: VpnNetworkPublishMode[]
}

export interface VpnNetworkPublishPayload {
  mode: 'http_direct' | 'nginx_le' | 'nginx_selfsigned'
  backend_port: number
  domain?: string | null
  email?: string | null
  https_public_port: number
  http_acme_port: number
}

export interface CidrProviderInfo {
  filename: string
  name: string
  description: string
  category: string
  enabled: boolean
  has_source: boolean
  cidr_count: number
}

export interface RouteStatsInfo {
  config_include_total: number
  config_include_per_file: Record<string, number>
  result_route_ips_count: number
  result_route_ips_exists: boolean
}

export interface RoutingOverview {
  providers: CidrProviderInfo[]
  route_stats: RouteStatsInfo
  list_dir: string
  config_dir: string
  timestamp: string
  node_id?: number | null
  node_name?: string | null
}

export interface CidrDbProviderMeta {
  cidr_count?: number
  last_refreshed_at?: string | null
  refresh_status?: string
  refresh_error?: string | null
  active_asns?: number[]
  anomaly_level?: string
  name?: string
  category?: string
  tags?: string[]
}

export interface CidrDbRefreshHistoryItem {
  id: number
  started_at?: string | null
  finished_at?: string | null
  status?: string
  providers_updated?: number
  providers_failed?: number
  total_cidrs?: number
  triggered_by?: string | null
}

export interface CidrLastCompileSummary {
  finished_at?: string | null
  status?: string | null
  files_updated?: number
  artifact_stamp?: string | null
  message?: string | null
}

export interface CidrDegradationAlert {
  scope: 'provider' | 'global' | string
  provider_key?: string | null
  level: 'critical' | 'warning' | 'info' | 'none' | string
  message: string
}

export interface CidrCompileArtifact {
  cidr_count: number
  exists: boolean
}

export interface CidrRuntimeBackup {
  stamp: string
  files: string[]
  file_count: number
  mtime: number
}

export interface CidrDeployPreviewFile {
  file: string
  status: string
  controller_cidr_count?: number
  node_cidr_count?: number
  diff?: { added: number; removed: number; unchanged: number; changed: boolean }
  error?: string
}

export interface CidrDeployPreviewNode {
  node_id: number
  node_name?: string | null
  status: string
  files?: CidrDeployPreviewFile[]
  total_controller_routes?: number
  total_node_routes?: number
  total_added?: number
  total_removed?: number
  files_changed?: number
  error?: string
}

export interface CidrDeployPreview {
  success: boolean
  message: string
  dry_run?: boolean
  has_changes?: boolean
  artifact_files?: string[]
  controller_artifacts?: Record<string, CidrCompileArtifact>
  per_node?: CidrDeployPreviewNode[]
  nodes_previewed?: number
  nodes_skipped?: number
  nodes_errored?: number
}

export interface CidrDbStatus {
  success: boolean
  last_refresh_started?: string | null
  last_refresh_finished?: string | null
  last_refresh_status?: string | null
  last_refresh_triggered_by?: string | null
  total_cidrs?: number
  providers: Record<string, CidrDbProviderMeta>
  alerts?: CidrDegradationAlert[]
  history?: CidrDbRefreshHistoryItem[]
  last_compile_at?: CidrLastCompileSummary | null
  last_deploy?: CidrLastDeploySummary | null
  compile_artifacts?: Record<string, CidrCompileArtifact>
  runtime_backups?: CidrRuntimeBackup[]
  active_task?: CidrPipelineTask | null
}

export interface AntifilterStatus {
  success: boolean
  cidr_count?: number
  last_refreshed_at?: string | null
  refresh_status?: string
  refresh_error?: string | null
}

export interface DpiAnalysisNode {
  node_id: string
  file: string | null
  severity: string
  severity_score: number
  status_text: string
  alive?: string | null
  host?: string | null
  checker_provider?: string | null
  checker_country?: string | null
  dpi_method?: number | null
}

export interface DpiAnalysisTriggerNode {
  node_id: string
  host?: string | null
  alive?: string | null
  severity: string
  severity_score: number
  status_text: string
  dpi_method?: number | null
}

export interface DpiAnalysisRecommendation {
  file: string
  name?: string
  category?: string
  level: 'must' | 'should' | 'consider' | 'skip'
  confidence: 'high' | 'medium' | 'low' | 'weak' | 'inconclusive'
  actionable: boolean
  reason: string
  trigger_nodes: DpiAnalysisTriggerNode[]
  all_nodes: DpiAnalysisTriggerNode[]
}

export interface DpiAnalysisCaveat {
  type: string
  severity: 'warning' | 'info'
  title: string
  message: string
}

export interface DpiAnalysisProvider {
  file: string
  name?: string
  category?: string
  max_severity_score: number
  detected: number
  possible_detected: number
  unlikely: number
  not_detected: number
  unknown?: number
  nodes: number
}

export interface DpiAnalysisResult {
  success: boolean
  message: string
  summary: {
    total_nodes?: number
    matched_nodes?: number
    unknown_nodes?: number
    all_seen_files?: number
    detected_files?: number
    priority_files?: number
    critical_files?: number
    actionable_files?: number
    weak_signals?: number
  }
  nodes: DpiAnalysisNode[]
  providers: DpiAnalysisProvider[]
  recommendations: DpiAnalysisRecommendation[]
  caveats: DpiAnalysisCaveat[]
  all_seen_files: string[]
  detected_files: string[]
  priority_files: string[]
  critical_files: string[]
  actionable_files: string[]
  unknown_nodes: string[]
}

export interface CidrDeployResult {
  pushed: string[]
  failed: Array<{ file: string; error: string }>
}

export interface CidrDeployPerNodeResult {
  node_id: number
  node_name?: string | null
  status: 'success' | 'failed' | 'skipped'
  pushed_files?: string[]
  failed?: Array<{ file: string; error: string }>
  error?: string | null
}

export interface CidrLastDeploySummary {
  finished_at?: string | null
  status?: string | null
  pushed_count?: number
  failed_count?: number
  target_node_id?: number | null
  artifact_stamp?: string | null
  nodes_deployed?: number
  nodes_failed?: number
  nodes_skipped?: number
  per_node?: CidrDeployPerNodeResult[]
  message?: string | null
}

export interface CidrPipelineTask {
  task_id: string
  task_type: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  message: string
  progress_percent: number
  progress_stage: string
  error?: string | null
  result?: {
    deploy?: CidrDeployResult
    per_node?: CidrDeployPerNodeResult[]
    artifact_stamp?: string | null
    nodes_deployed?: number
    nodes_failed?: number
    nodes_skipped?: number
    [key: string]: unknown
  }
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export type BackgroundTask = CidrPipelineTask

export interface BackgroundTaskAcceptedResponse extends BackgroundTask {
  success: boolean
  queued: boolean
  status_url: string
}

export type BackgroundTaskAccepted = BackgroundTaskAcceptedResponse

export interface ConfigCsvImportResponse {
  success: boolean
  async?: boolean
  queued?: boolean
  task_id?: string
  message: string
  result?: {
    total: number
    succeeded: Array<Record<string, unknown>>
    failed: Array<Record<string, unknown>>
  }
}

export interface EventWebhookEventToggle {
  key: string
  label: string
  enabled: boolean
}

export interface EventWebhookSettings {
  url: string
  secret_configured: boolean
  enabled: boolean
  events: EventWebhookEventToggle[]
}

export interface AuditStreamSettings {
  enabled: boolean
  mode: 'http' | 'syslog' | 'both'
  http_url: string
  secret_configured: boolean
  syslog_host: string
  syslog_port: number
  syslog_protocol: 'udp' | 'tcp'
  format: 'json' | 'cef'
}

export interface TrafficClientRow {
  common_name: string
  protocol_type: string
  total_received: number
  total_sent: number
  total_bytes: number
  total_received_vpn: number
  total_sent_vpn: number
  total_bytes_vpn: number
  total_received_antizapret: number
  total_sent_antizapret: number
  total_bytes_antizapret: number
  traffic_1d: number
  traffic_7d: number
  traffic_30d: number
  total_sessions: number
  first_seen_at?: string | null
  last_seen_at?: string | null
  is_active: boolean
}

export interface TrafficSummary {
  users_count: number
  active_users_count: number
  total_received: number
  total_sent: number
  total_received_vpn: number
  total_sent_vpn: number
  total_received_antizapret: number
  total_sent_antizapret: number
  latest_sample_at?: string | null
  db_age_seconds?: number | null
  db_is_stale: boolean
}

export interface TrafficOverview {
  rows: TrafficClientRow[]
  summary: TrafficSummary
  timestamp: string
  node_id?: number | null
  node_name?: string | null
}

export interface ClientAccessPolicy {
  is_blocked: boolean
  block_mode: string
  node_id?: number | null
  node_name?: string | null
  access_days_left?: number | null
  blocked_days_left?: number | null
  block_duration_days?: number | null
  expires_at?: string | null
  expired?: boolean
  traffic_limit_bytes?: number | null
  traffic_limit_period_days?: number | null
  traffic_limit_period_label?: string | null
  traffic_limit_human?: string | null
  traffic_consumed_bytes?: number | null
  traffic_consumed_human?: string | null
  traffic_bytes_left?: number | null
  traffic_bytes_left_human?: string | null
  traffic_limit_exceeded?: boolean
  traffic_limit_unblock_at?: string | null
  traffic_limit_unblock_label?: string | null
}

export interface FeatureToggleItem {
  key: string
  env_key: string
  label: string
  description: string
  default: boolean
  group: string
  icon: string
  disable_hint?: string | null
  resource_impact_level: string
  resource_impact_label: string
  resource_savings: string
  enabled: boolean
  group_meta: { label?: string; description?: string; badge?: string }
}

export interface FeatureTogglesResponse {
  items: FeatureToggleItem[]
  groups: Record<string, { label: string; description: string; badge: string }>
  total: number
  enabled_count: number
  disabled_count: number
}

export interface FeatureModulesResponse {
  features: Record<string, boolean>
  frontend_paths: Record<string, string>
  settings_tabs: Record<string, string>
}

export interface EditFileEntry {
  key: string
  filename: string
  title: string
}

export interface SecuritySettings {
  ip_restriction_enabled: boolean
  allowed_ips: string[]
  whitelist_firewall: boolean
  whitelist_firewall_applicable: boolean
  whitelist_firewall_active: boolean
  firewall_tools_ready: boolean
  firewall_tools_detail: string
  block_scanners: boolean
  scanner_max_attempts: number
  scanner_ban_seconds: number
  scanner_window_seconds: number
  block_ip_blocked_dwell: boolean
  ip_blocked_dwell_seconds: number
  temp_whitelist: Array<{ ip: string; expires_at: string; hours: number }>
  qr_download_ttl_seconds: number
  qr_download_max_downloads: number
  qr_download_pin_set: boolean
  public_download_enabled: boolean
}

export interface SecretRotationItem {
  secret_id: string
  label: string
  description: string
  storage: string
  env_key?: string | null
  env_path?: string | null
  configured: boolean
  masked_current: string
  auto_generate: boolean
  requires_restart: boolean
  requires_relogin: boolean
}

export interface SecretRotationEnvChangePreview {
  path: string
  key: string
  masked_new_value: string
}

export interface SecretRotationPreview {
  secret_id: string
  label: string
  new_value: string
  masked_new_value: string
  masked_current: string
  preview_token: string
  confirm_phrase: string
  warnings: string[]
  env_change?: SecretRotationEnvChangePreview | null
  storage: string
  requires_relogin: boolean
  requires_restart: boolean
}

export interface SecretRotationApplyResult {
  secret_id: string
  label: string
  message: string
  requires_relogin: boolean
  next_steps: string[]
  reencrypt_stats?: Record<string, number> | null
}

export interface OpenVpnGroupOption {
  key: string
  label: string
}

export interface OpenVpnGroupState {
  group: string
  options: OpenVpnGroupOption[]
}

export interface ServerMetrics {
  cpu_percent: number
  memory_percent: number
  memory_used: number
  memory_total: number
  disk_percent: number
  uptime: string
  load_average: Record<string, number>
  timestamp: string
  hostname?: string
  node_id?: number | null
  node_name?: string | null
}

export interface BandwidthChart {
  iface: string
  range: string
  labels: string[]
  rx_mbps: number[]
  tx_mbps: number[]
  totals?: Record<string, { rx_bytes: number; tx_bytes: number; total_bytes: number }>
  error?: string
}

export interface ResourceHistoryPoint {
  timestamp: string
  cpu_percent: number
  memory_percent: number
  memory_used_mb: number
  memory_total_mb: number
  disk_percent: number
  load_1?: number | null
  load_5?: number | null
  load_15?: number | null
}

export interface ResourceHistory {
  node_id: number
  node_name: string
  period: string
  sample_count: number
  points: ResourceHistoryPoint[]
}

export interface PanelResourceHistoryPoint {
  timestamp: string
  backend_cpu_percent: number
  backend_memory_mb: number
  backend_workers: number
  nginx_memory_mb?: number | null
  watchdog_memory_mb?: number | null
  frontend_dev_memory_mb?: number | null
  total_panel_memory_mb: number
  host_cpu_percent: number
  host_memory_percent: number
  host_memory_used_mb: number
  host_memory_total_mb: number
  host_disk_percent: number
  host_load_1?: number | null
}

export interface PanelResourceHistory {
  period: string
  sample_count: number
  points: PanelResourceHistoryPoint[]
}

export interface PanelResourceCurrent {
  timestamp: string
  backend_cpu_percent: number
  backend_memory_mb: number
  backend_rss_mb: number
  backend_workers: number
  nginx_memory_mb?: number | null
  watchdog_memory_mb?: number | null
  frontend_dev_memory_mb?: number | null
  total_panel_memory_mb: number
  frontend_note: string
  host_cpu_percent: number
  host_memory_percent: number
  host_memory_used_mb: number
  host_memory_total_mb: number
  host_disk_percent: number
  host_load_1?: number | null
  host_hostname: string
  host_uptime: string
}

export interface ScannerBan {
  ip: string
  ban_until: number
  remaining_seconds: number
  strikes: number
  long_term: boolean
}

export interface ActionLogEntry {
  id: number
  username?: string | null
  action: string
  details?: string | null
  remote_addr?: string | null
  created_at: string
}

export interface QrDownloadAuditEntry {
  id: number
  event_type: string
  actor_username?: string | null
  remote_addr?: string | null
  details?: string | null
  created_at: string
}

export interface OpenVpnSocketStatus {
  profile: string
  socket_path: string
  socket_exists: boolean
  responsive: boolean
}

export interface RouteResultFileEntry {
  key: string
  filename: string
  exists: boolean
  line_count: number
}

export interface RoutingProviderContent {
  filename: string
  content: string
  cidr_count: number
}

export interface NodeMtlsDisableResult {
  message: string
  node_id: number
  mtls_enabled: boolean
  warning?: string | null
}

export interface OneTimeLinkResponse {
  url: string
  token: string
  expires_at: string
  max_downloads: number
  pin_required: boolean
}

export interface TrafficChartData {
  client: string
  range: string
  bucket: string
  protocol_filter: string
  labels: string[]
  vpn_bytes: number[]
  antizapret_bytes: number[]
  openvpn_bytes: number[]
  wireguard_bytes: number[]
  total_vpn: number
  total_antizapret: number
  total: number
}

export interface TrafficSessionSourceRow {
  client_ip: string
  display_address?: string | null
  city?: string | null
  country?: string | null
  isp?: string | null
  location_label?: string | null
  geo_label?: string | null
  sessions_count: number
  virtual_addresses: string[]
  total_bytes: number
  first_seen_at?: string | null
  last_seen_at?: string | null
  is_active: boolean
  share_percent: number
}

export interface TrafficSessionItem {
  profile: string
  real_address?: string | null
  virtual_address?: string | null
  connected_since_at?: string | null
  last_seen_at?: string | null
  ended_at?: string | null
  duration_seconds?: number | null
  bytes_received: number
  bytes_sent: number
  total_bytes: number
  is_active: boolean
}

export interface TrafficClientSessions {
  client: string
  total_sessions: number
  unique_sources: number
  unique_virtual_addresses: number
  by_source: TrafficSessionSourceRow[]
  recent_sessions: TrafficSessionItem[]
  node_id?: number | null
  node_name?: string | null
}

export interface AntizapretSettingField {
  key: string
  html_id: string
  type: 'flag' | 'string'
  env: string
  param_label: string
  title: string
  description: string
}

export interface AntizapretSettingsResponse {
  settings: Record<string, string>
  schema: AntizapretSettingField[]
  node_id?: number | null
  node_name?: string | null
}

export interface AntizapretSettingsUpdateResponse {
  success: boolean
  message: string
  changes: number
  needs_apply: boolean
}

export interface WarperHealthResponse {
  installed: boolean
  active: boolean
  version?: string | null
  conflict_antizapret_warp: boolean
  health_error?: string | null
  warper_bin?: boolean | null
  warper_script?: boolean | null
  warper_api?: boolean | null
  missing_components?: string[]
  node_id?: number | null
  node_name?: string | null
  node_host?: string | null
}

export interface WarperStatusResponse {
  status: Record<string, unknown>
  node_id?: number | null
  node_name?: string | null
}

export interface WarperDomainItem {
  domain?: string | null
  name?: string | null
  type?: string | null
  status?: string | null
  [key: string]: unknown
}

export interface WarperDomainListsStatus {
  gemini: boolean
  chatgpt: boolean
}

export interface WarperDomainsResponse {
  domains: WarperDomainItem[]
  lists?: WarperDomainListsStatus
  node_id?: number | null
  node_name?: string | null
}

export type WarperDoctorStatus = 'ok' | 'warn' | 'error' | 'info'

export interface WarperDoctorItem {
  status?: WarperDoctorStatus | string
  text?: string
  check?: string
  name?: string
  message?: string
}

export interface WarperDoctorResponse {
  items: WarperDoctorItem[]
  passed?: boolean | null
  summary?: Record<string, number> | null
  node_id?: number | null
  node_name?: string | null
}

export interface WarperActionResponse {
  message?: string | null
  success?: boolean | null
  node_id?: number | null
  node_name?: string | null
  [key: string]: unknown
}

export interface WarperDomainsBulkResponse {
  added: string[]
  added_count: number
  errors: Array<{ domain: string; error: string }>
  node_id?: number | null
  node_name?: string | null
}

export interface WarperIpRangesResponse {
  ranges: Array<string | Record<string, unknown>>
  node_id?: number | null
  node_name?: string | null
}

export interface WarperTrafficResponse {
  data: Record<string, unknown>
  node_id?: number | null
  node_name?: string | null
}

export interface WarperLogsResponse {
  lines: string[]
  node_id?: number | null
  node_name?: string | null
}

export interface WarperModeResponse {
  mode: Record<string, unknown>
  node_id?: number | null
  node_name?: string | null
}

export type WarperTrafficPeriod = 'today' | 'week' | 'month' | 'all'

export type SiteDiagnosticsStatus = 'ok' | 'warn' | 'fail'

export interface SiteDiagnosticsCheck {
  status: SiteDiagnosticsStatus
  title: string
  category: string
  detail?: string
  hint_ru?: string
}

export interface SiteDiagnosticsStep {
  id: string
  title: string
  description: string
  status: SiteDiagnosticsStatus
  checks: SiteDiagnosticsCheck[]
}

export interface SiteDiagnosticsReport {
  success: boolean
  install_dir: string
  service_name: string
  summary: {
    ok: number
    warn: number
    fail: number
    has_failures: boolean
  }
  steps: SiteDiagnosticsStep[]
  results: SiteDiagnosticsCheck[]
  recommended_commands: string[]
}
