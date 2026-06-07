export type UserRole = 'admin' | 'user'
export type VpnType = 'openvpn' | 'wireguard'

export interface User {
  id: number
  username: string
  role: UserRole
  theme: string
  is_active: boolean
  must_change_password: boolean
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
}

export interface AppSettings {
  theme: string
  app_name: string
  antizapret_path: string
  include_hosts: string
  exclude_hosts: string
  include_ips: string
}
