import type { PanelResourceCurrent, PanelResourceHistoryPoint, ResourceProfileItem } from '@/types'

export interface PanelResourceSummary {
  hasData: boolean
  sampleCount: number
  localNodeOnHost: boolean
  panelMbNow: number | null
  nodeAgentMbNow: number | null
  managedVpnMbNow: number | null
  nodeMbNow: number | null
  stackMbNow: number | null
  stackMbAvg7d: number | null
  stackMbPeak7d: number | null
  hostTotalGb: number | null
  hostCpuNow: number | null
  hostDiskNow: number | null
}

export interface ProfileLiveCopy {
  subtitle: string
  description: string
  ram: string
  cpuDisk: string
  note: string
}

const PROFILE_ORDER = ['minimal', 'standard', 'full'] as const

function mbToGb(mb: number): number {
  return Math.round((mb / 1024) * 10) / 10
}

function avg(values: number[]): number | null {
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function roundMb(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(value)) return null
  return Math.round(value)
}

function stripPresetRamLine(description: string): string {
  return description.split(';')[0].trim().replace(/\.$/, '')
}

function stackFromPoint(point: PanelResourceHistoryPoint): number {
  if (point.total_stack_memory_mb != null && point.total_stack_memory_mb > 0) {
    return point.total_stack_memory_mb
  }
  return point.total_panel_memory_mb + (point.local_node_memory_mb ?? 0)
}

function readManagedVpn(live: PanelResourceCurrent | null, latest: PanelResourceHistoryPoint | null): number | null {
  return (
    live?.managed_vpn_memory_mb ??
    latest?.managed_vpn_memory_mb ??
    live?.local_vpn_core_memory_mb ??
    latest?.local_vpn_core_memory_mb ??
    null
  )
}

function readNodeAgent(live: PanelResourceCurrent | null, latest: PanelResourceHistoryPoint | null): number | null {
  return live?.node_agent_memory_mb ?? latest?.node_agent_memory_mb ?? null
}

function readNodeTotal(
  live: PanelResourceCurrent | null,
  latest: PanelResourceHistoryPoint | null,
  nodeAgent: number | null,
  managedVpn: number | null,
): number | null {
  const direct = live?.local_node_memory_mb ?? latest?.local_node_memory_mb
  if (direct != null) return direct
  if (nodeAgent != null || managedVpn != null) return (nodeAgent ?? 0) + (managedVpn ?? 0)
  return null
}

export function summarizePanelResources(
  points: PanelResourceHistoryPoint[],
  live: PanelResourceCurrent | null,
): PanelResourceSummary {
  const stackMbs = points.map(stackFromPoint).filter((v) => v > 0)
  const latest = points.length > 0 ? points[points.length - 1] : null

  const panelMbNow = live?.total_panel_memory_mb ?? latest?.total_panel_memory_mb ?? null
  const nodeAgentMbNow = readNodeAgent(live, latest)
  const managedVpnMbNow = readManagedVpn(live, latest)
  const nodeMbNow = readNodeTotal(live, latest, nodeAgentMbNow, managedVpnMbNow)
  const stackMbNow =
    live?.total_stack_memory_mb ?? latest?.total_stack_memory_mb ?? (panelMbNow != null ? panelMbNow + (nodeMbNow ?? 0) : null)
  const hostTotalMb = live?.host_memory_total_mb ?? latest?.host_memory_total_mb ?? null
  const hostCpuNow = live?.host_cpu_percent ?? latest?.host_cpu_percent ?? null
  const hostDiskNow = live?.host_disk_percent ?? latest?.host_disk_percent ?? null

  return {
    hasData: points.length > 0 || live != null,
    sampleCount: points.length,
    localNodeOnHost: live?.local_node_on_host ?? (nodeMbNow != null && nodeMbNow > 0),
    panelMbNow: roundMb(panelMbNow),
    nodeAgentMbNow: roundMb(nodeAgentMbNow),
    managedVpnMbNow: roundMb(managedVpnMbNow),
    nodeMbNow: roundMb(nodeMbNow),
    stackMbNow: roundMb(stackMbNow),
    stackMbAvg7d: roundMb(avg(stackMbs)),
    stackMbPeak7d: stackMbs.length ? roundMb(Math.max(...stackMbs)) : null,
    hostTotalGb: hostTotalMb != null ? mbToGb(hostTotalMb) : null,
    hostCpuNow,
    hostDiskNow,
  }
}

function formatNodePart(summary: PanelResourceSummary): string {
  const agent = summary.nodeAgentMbNow ?? 0
  const vpn = summary.managedVpnMbNow ?? 0
  if (agent > 0 && vpn > 0) {
    return `нода ${agent} MB + VPN ${vpn} MB`
  }
  if (summary.nodeMbNow != null && summary.nodeMbNow > 0) {
    return `нода ${summary.nodeMbNow} MB`
  }
  return 'нода —'
}

export function formatMeasuredSubtitle(summary: PanelResourceSummary): string | null {
  if (!summary.hasData || summary.stackMbNow == null || summary.panelMbNow == null) return null
  return `AdminPanelAZ ${summary.panelMbNow} MB + ${formatNodePart(summary)} ≈ ${summary.stackMbNow} MB`
}

export function formatComparedProfileHint(
  profile: Pick<ResourceProfileItem, 'key' | 'label' | 'panel_mb_delta'>,
  summary: PanelResourceSummary | null,
  currentProfileKey: string,
): string | null {
  if (profile.key === currentProfileKey) return null
  if (!summary?.stackMbNow || !summary.panelMbNow) {
    return profile.key === 'minimal'
      ? 'меньше фоновых задач AdminPanelAZ'
      : profile.key === 'standard'
        ? 'без CIDR scheduler'
        : null
  }

  const delta = profile.panel_mb_delta ?? 0
  const projectedStack = Math.max(0, summary.panelMbNow + delta) + (summary.nodeMbNow ?? 0)
  const currentLabel = PROFILE_ORDER.includes(currentProfileKey as (typeof PROFILE_ORDER)[number])
    ? currentProfileKey
    : 'текущий'

  if (delta < 0) {
    return `сейчас ${currentLabel}: ~${summary.stackMbNow} MB · здесь обычно ~${projectedStack} MB`
  }
  if (profile.key === 'full') {
    return `сейчас ${currentLabel}: ~${summary.stackMbNow} MB · Full — все collectors`
  }
  return null
}

export function buildProfileLiveCopy(
  profile: Pick<ResourceProfileItem, 'description' | 'impact'>,
  summary: PanelResourceSummary,
): ProfileLiveCopy {
  const stackLine = formatMeasuredSubtitle(summary) ?? 'замер недоступен'
  const subtitle = stackLine

  const descBase = stripPresetRamLine(profile.description)
  const description = `${descBase}. ${stackLine}.`

  const avgPart =
    summary.stackMbAvg7d != null ? ` · ср. стек за 7 дн. ~${summary.stackMbAvg7d} MB` : ''
  const ram = `AdminPanelAZ ${summary.panelMbNow ?? '—'} MB + ${formatNodePart(summary)} ≈ ${summary.stackMbNow ?? '—'} MB${avgPart}`

  const cpu = summary.hostCpuNow != null ? `${Math.round(summary.hostCpuNow)}%` : '—'
  const disk = summary.hostDiskNow != null ? `${Math.round(summary.hostDiskNow)}%` : '—'
  const cpuDisk = `CPU хоста ${cpu}, диск занято ${disk}`

  let note = profile.impact?.note ?? ''
  if (summary.stackMbNow != null) {
    note = 'Стек: AdminPanelAZ + локальная нода и её VPN-сервисы (OpenVPN, ANTIZAPRET_PATH). Сторонние проекты на VDS не учитываются.'
  }

  return { subtitle, description, ram, cpuDisk, note }
}
