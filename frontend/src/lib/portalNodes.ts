import type { PortalClientEntry, PortalMetaResponse, PortalNodeEntry } from '@/api/portal'

export interface PortalSelection {
  node: PortalNodeEntry | null
  client: PortalClientEntry | null
}

export function normalizePortalNodes(data: PortalMetaResponse): PortalNodeEntry[] {
  if (data.kind === 'user') return data.nodes
  return [
    {
      node_id: data.node_id,
      label: '',
      clients: [
        {
          node_id: data.node_id,
          client_name: data.client_name,
          protocols: data.protocols,
          files: data.files,
          status: data.status,
        },
      ],
    },
  ]
}

export function portalClientKey(client: PortalClientEntry): string {
  return `${client.node_id}:${client.client_name}`
}

export function pickPortalSelection(
  nodes: PortalNodeEntry[],
  nodeId: number | null,
  clientKey: string,
): PortalSelection {
  const node = nodes.find((item) => item.node_id === nodeId) ?? nodes[0] ?? null
  if (!node) return { node: null, client: null }
  const client = node.clients.find((item) => portalClientKey(item) === clientKey) ?? node.clients[0] ?? null
  return { node, client }
}

export function portalProfileLabel(nodes: PortalNodeEntry[], selection: PortalSelection): string {
  if (!selection.client) return 'Нет профилей'
  if (nodes.length > 1 && selection.node) return `${selection.node.label} · ${selection.client.client_name}`
  return selection.client.client_name
}
