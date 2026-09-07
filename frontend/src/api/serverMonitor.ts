import { apiFetch } from './http'

export async function getServerMetrics(accurate = false) {
  return apiFetch<import('../types').ServerMetrics>(`/server-monitor/metrics?accurate=${accurate}`)
}

export async function getServerInterfaces() {
  return apiFetch<{
    interfaces: string[]
    groups?: Record<string, string[]>
    primary_interface?: string | null
  }>('/server-monitor/interfaces')
}

export async function getBandwidthChart(iface: string, range: string) {
  return apiFetch<import('../types').BandwidthChart>(
    `/server-monitor/bandwidth?iface=${encodeURIComponent(iface)}&range_key=${range}`,
  )
}
