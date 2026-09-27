import { apiFetch } from './http'
import type { ServerMetrics, BandwidthChart } from '../types'

export async function getServerMetrics(accurate = false) {
  return apiFetch<ServerMetrics>(`/server-monitor/metrics?accurate=${accurate}`)
}

export async function getServerInterfaces() {
  return apiFetch<{
    interfaces: string[]
    groups?: Record<string, string[]>
    primary_interface?: string | null
  }>('/server-monitor/interfaces')
}

export async function getBandwidthChart(iface: string, range: string) {
  return apiFetch<BandwidthChart>(
    `/server-monitor/bandwidth?iface=${encodeURIComponent(iface)}&range_key=${range}`,
  )
}
