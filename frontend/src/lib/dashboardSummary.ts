import { isWireGuardOnline } from '@/lib/wireguardStatus'
import type { DashboardSummary, MonitoringOverview, VpnConfig } from '@/types'

/** Config counts for dashboard metric cards (DB list; no live VPN probe). */
export function dashboardSummaryFromConfigs(
  configs: VpnConfig[],
  nodeName?: string | null,
): DashboardSummary {
  return {
    total_configs: configs.length,
    openvpn_configs: configs.filter((c) => c.vpn_type === 'openvpn').length,
    wireguard_configs: configs.filter((c) => c.vpn_type === 'wireguard').length,
    connected_openvpn: 0,
    connected_wireguard: 0,
    active_services: 0,
    total_services: 0,
    server_ip: '',
    node_name: nodeName ?? '',
  }
}

/** Merge live connection/service fields from /monitoring/overview into config counts. */
export function mergeDashboardSummaryMonitoring(
  base: DashboardSummary,
  overview: MonitoringOverview | null | undefined,
): DashboardSummary {
  if (!overview) return base
  const connectedOpenvpn =
    overview.total_connected_openvpn ?? overview.openvpn_clients.length
  const connectedWireguard =
    overview.total_connected_wireguard ??
    overview.wireguard_peers.filter(isWireGuardOnline).length
  const services = overview.services ?? []
  // scope=all отдаёт services=[] (агрегат без служб), но nodes_summary знает каждый узел.
  // Карточка говорит «активных на узле», поэтому берём активный узел, а не сумму по кластеру.
  const activeNodeSummary = overview.nodes_summary?.find((node) => node.node_id === overview.node_id)
  const activeServices =
    activeNodeSummary?.active_services ?? services.filter((service) => service.active).length
  const totalServices = activeNodeSummary?.total_services ?? services.length
  return {
    ...base,
    connected_openvpn: connectedOpenvpn,
    connected_wireguard: connectedWireguard,
    active_services: activeServices,
    total_services: totalServices,
    server_ip: overview.server_ip || base.server_ip || '',
    node_name: overview.node_name || base.node_name || '',
  }
}

export function buildDashboardSummary(
  configs: VpnConfig[],
  overview: MonitoringOverview | null | undefined,
  nodeName?: string | null,
): DashboardSummary {
  return mergeDashboardSummaryMonitoring(dashboardSummaryFromConfigs(configs, nodeName), overview)
}
