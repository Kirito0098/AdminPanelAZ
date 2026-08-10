import type { Awg2HealthResponse, Node } from '@/types'

export const AWG2_INSTALL_CMD =
  'bash <(curl -fsSL https://raw.githubusercontent.com/blindtechnique/az-awg2/main/install.sh)'

export function formatAwg2NodeLabel(health: Awg2HealthResponse | null, activeNode: Node | null): string {
  const name = health?.node_name ?? activeNode?.name
  const host = health?.node_host ?? activeNode?.host
  if (name && host) return `${name} (${host})`
  if (name) return name
  if (host) return host
  return 'активном узле панели'
}
