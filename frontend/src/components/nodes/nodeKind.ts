import type { Node } from '@/types'

export const PROXY_DEFAULT_PORT = 9101
export const VPN_DEFAULT_PORT = 9100

/** True when node_kind is proxy (defaults to vpn if unset). */
export function isProxyNode(node: Node): boolean {
  return (node.node_kind || 'vpn') === 'proxy'
}
