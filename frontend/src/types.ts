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
  last_seen_at?: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ActiveNode {
  node: Node
  active: boolean
}

export interface User {
  id: number
  username: string
  role: UserRole
  theme: string
  is_active: boolean
  must_change_password: boolean
  totp_enabled?: boolean
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
  profile_files: Array<{ protocol: string; variant: string; filename: string; path: string }>
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
  retention_count: number
}

export interface TelegramSettings {
  bot_token_set: boolean
  chat_id: string
  notify_enabled: boolean
  notify_on_backup: boolean
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

export interface CidrDbStatus {
  success: boolean
  last_refresh_started?: string | null
  last_refresh_finished?: string | null
  last_refresh_status?: string | null
  last_refresh_triggered_by?: string | null
  total_cidrs?: number
  providers: Record<string, CidrDbProviderMeta>
  alerts?: string[]
  history?: CidrDbRefreshHistoryItem[]
}

export interface AntifilterStatus {
  success: boolean
  cidr_count?: number
  last_refreshed_at?: string | null
  refresh_status?: string
  refresh_error?: string | null
}

export interface CidrPipelineTask {
  task_id: string
  task_type: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  message: string
  progress_percent: number
  progress_stage: string
  error?: string | null
  result?: unknown
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
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

export interface GameFilterItem {
  key: string
  title: string
  subtitle: string
  domains: string[]
  mode: string
  selected: boolean
}

export interface SecuritySettings {
  ip_restriction_enabled: boolean
  allowed_ips: string[]
  block_scanners: boolean
  scanner_max_attempts: number
  scanner_ban_seconds: number
  temp_whitelist: Array<{ ip: string; expires_at: string; hours: number }>
  qr_download_ttl_seconds: number
  qr_download_max_downloads: number
  qr_download_pin_set: boolean
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
  total_panel_memory_mb: number
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
