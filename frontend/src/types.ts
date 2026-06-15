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
  created_at: string
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
}

export interface MonitoringNodeSummary {
  node_id: number
  node_name: string
  status: string
  connected_openvpn: number
  connected_wireguard: number
  active_services: number
  total_services: number
  error?: string | null
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

export interface CidrPresetInfo {
  key: string
  name: string
  description: string
  providers: string[]
}

export interface CidrPresetSettings {
  region_scopes: string[]
  include_non_geo_fallback: boolean
  exclude_ru_cidrs: boolean
}

export interface CidrDbPresetInfo {
  id: number
  key: string
  name: string
  description: string
  is_builtin: boolean
  providers: string[]
  settings: CidrPresetSettings
  sort_order?: number
  created_at?: string
  updated_at?: string
  providers_meta?: Record<string, { name: string; category: string; tags: string[] }>
}

export interface RouteStatsInfo {
  config_include_total: number
  config_include_per_file: Record<string, number>
  result_route_ips_count: number
  result_route_ips_exists: boolean
}

export interface RoutingOverview {
  providers: CidrProviderInfo[]
  presets: CidrPresetInfo[]
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
  active_task?: CidrPipelineTask | null
}

export interface AntifilterStatus {
  success: boolean
  cidr_count?: number
  last_refreshed_at?: string | null
  refresh_status?: string
  refresh_error?: string | null
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
