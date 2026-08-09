/** Склонение «N узел/узла/узлов» для русского UI. */
export function formatHaNodeCount(count: number): string {
  const n = Math.abs(count) % 100
  const n1 = n % 10
  if (n > 10 && n < 20) return `${count} узлов`
  if (n1 === 1) return `${count} узел`
  if (n1 >= 2 && n1 <= 4) return `${count} узла`
  return `${count} узлов`
}

/** Effective WireGuard/AWG shared domain (falls back to OpenVPN domain). */
export function effectiveHaWireguardDomain(group: {
  shared_domain: string
  shared_domain_wireguard?: string | null
}): string {
  const wg = (group.shared_domain_wireguard || '').trim()
  return wg || group.shared_domain.trim()
}

/** Label for list/DNS/confirm: one domain or «ovpn / awg» when they differ. */
export function formatHaSharedDomains(group: {
  shared_domain: string
  shared_domain_wireguard?: string | null
}): string {
  const ovpn = group.shared_domain.trim()
  const wg = effectiveHaWireguardDomain(group)
  if (!ovpn) return wg
  if (!wg || ovpn === wg) return ovpn
  return `${ovpn} / ${wg}`
}

export function formatHaBadgeLabel(ha: { shared_domain: string; node_count: number }): string {
  return `HA: ${ha.shared_domain} · ${formatHaNodeCount(ha.node_count)}`
}

export function haBadgeTitle(ha: { node_count: number }): string {
  return `Клиент синхронизирован в HA-группе и доступен на ${formatHaNodeCount(ha.node_count)} (primary и replica)`
}
