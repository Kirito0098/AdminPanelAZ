import type { BackgroundTask } from '@/types'

type HaHostCopy = {
  node_name?: string
  node_id?: number
  hosts?: Record<string, string>
  error?: string
}

type HaOpenVpnRestart = {
  node_name?: string
  node_id?: number
  restarted?: string[]
  skipped?: string[]
  failed?: Array<{ unit?: string; error?: string }>
}

type HaPushFullPayload = {
  host_copy?: HaHostCopy[]
  restored?: Array<{ node_name?: string; node_id?: number }>
  openvpn_restart?: HaOpenVpnRestart[]
  message?: string
}

type HaSharedDomainPayload = {
  domain?: string
  updated?: Array<{ node_name?: string; node_id?: number }>
  openvpn_restart?: HaOpenVpnRestart[]
}

type HaSetupPayload = {
  shared_domain?: HaSharedDomainPayload
  push_full?: HaPushFullPayload
}

function shortUnitName(unit: string): string {
  return unit.replace('openvpn-server@', 'ovpn:')
}

function formatHostCopy(items: HaHostCopy[] | undefined): string[] {
  if (!items?.length) return []
  return items.map((item) => {
    const name = item.node_name || String(item.node_id ?? 'узел')
    if (item.error) return `${name}: не удалось скопировать хосты (${item.error})`
    const hosts = item.hosts ?? {}
    const labels = Object.entries(hosts)
      .map(([key, value]) => `${key}=${value}`)
      .join(', ')
    return labels ? `${name}: скопировано ${labels}` : `${name}: хосты обновлены`
  })
}

function formatOpenVpnRestart(items: HaOpenVpnRestart[] | undefined): string[] {
  if (!items?.length) return []
  return items.flatMap((item) => {
    const name = item.node_name || String(item.node_id ?? 'узел')
    const lines: string[] = []
    if (item.restarted?.length) {
      lines.push(
        `${name}: перезапущено ${item.restarted.map(shortUnitName).join(', ')}`,
      )
    }
    if (item.failed?.length) {
      lines.push(
        `${name}: ошибка перезапуска ${item.failed
          .map((entry) => shortUnitName(entry.unit || 'openvpn'))
          .join(', ')}`,
      )
    }
    return lines
  })
}

function formatRestored(items: HaPushFullPayload['restored']): string[] {
  if (!items?.length) return []
  return items.map(
    (item) => `${item.node_name || item.node_id}: восстановлен бэкап AntiZapret`,
  )
}

function formatSharedDomainUpdated(items: HaSharedDomainPayload['updated']): string[] {
  if (!items?.length) return []
  return items.map(
    (item) => `${item.node_name || item.node_id}: домен записан в OPENVPN_HOST / WIREGUARD_HOST`,
  )
}

function parseTaskOutput(task: BackgroundTask | null | undefined): unknown {
  const raw = task?.output
  if (!raw) return null
  try {
    return JSON.parse(raw) as unknown
  } catch {
    return null
  }
}

export function formatHaSyncTaskSummary(task: BackgroundTask | null | undefined): string | null {
  const parsed = parseTaskOutput(task)
  if (!parsed || typeof parsed !== 'object') {
    return task?.message?.trim() || null
  }

  const lines: string[] = []

  if ('shared_domain' in parsed || 'push_full' in parsed) {
    const setup = parsed as HaSetupPayload
    if (setup.shared_domain) {
      const domain = setup.shared_domain.domain
      if (domain) lines.push(`Домен ${domain} применён на узлах`)
      lines.push(...formatSharedDomainUpdated(setup.shared_domain.updated))
      lines.push(...formatOpenVpnRestart(setup.shared_domain.openvpn_restart))
    }
    if (setup.push_full) {
      lines.push(...formatHostCopy(setup.push_full.host_copy))
      lines.push(...formatRestored(setup.push_full.restored))
      lines.push(...formatOpenVpnRestart(setup.push_full.openvpn_restart))
      if (setup.push_full.message) lines.push(setup.push_full.message)
    }
  } else if ('host_copy' in parsed || 'restored' in parsed) {
    const push = parsed as HaPushFullPayload
    lines.push(...formatHostCopy(push.host_copy))
    lines.push(...formatRestored(push.restored))
    lines.push(...formatOpenVpnRestart(push.openvpn_restart))
    if (push.message) lines.push(push.message)
  } else if ('updated' in parsed || 'domain' in parsed) {
    const domainPayload = parsed as HaSharedDomainPayload
    if (domainPayload.domain) lines.push(`Домен ${domainPayload.domain} применён`)
    lines.push(...formatSharedDomainUpdated(domainPayload.updated))
    lines.push(...formatOpenVpnRestart(domainPayload.openvpn_restart))
  }

  const compact = [...new Set(lines.map((line) => line.trim()).filter(Boolean))]
  if (compact.length) return compact.join(' · ')
  return task?.message?.trim() || null
}

export function formatHaSyncTaskDetails(task: BackgroundTask | null | undefined): string[] {
  const summary = formatHaSyncTaskSummary(task)
  if (!summary) return []
  return summary.split(' · ').map((line) => line.trim()).filter(Boolean)
}
