import { apiFetch } from './http'

export async function rotateNodeApiKey(nodeId: number) {
  return apiFetch<{ message: string; node_id: number }>(`/nodes/${nodeId}/rotate-key`, {
    method: 'POST',
  })
}

export async function disableNodeMtls(nodeId: number) {
  return apiFetch<import('../types').NodeMtlsDisableResult>(`/nodes/${nodeId}/disable-mtls`, {
    method: 'POST',
  })
}

export async function enableNodeMtls(nodeId: number) {
  return apiFetch<{ message: string; node_id: number; mtls_enabled: boolean }>(
    `/nodes/${nodeId}/enable-mtls`,
    { method: 'POST' },
  )
}

export async function getNodeMtlsStatus() {
  return apiFetch<import('../types').NodeMtlsStatus>('/nodes/mtls/status')
}

export async function getNodes() {
  return apiFetch<import('../types').Node[]>('/nodes')
}

export async function getActiveNode() {
  return apiFetch<import('../types').ActiveNode>('/nodes/active')
}

export async function createNode(data: {
  name: string
  host: string
  port: number
  api_key: string
  node_kind?: import('../types').NodeKind | string
  destination_ip?: string | null
  linked_vpn_node_id?: number | null
}) {
  return apiFetch<import('../types').Node>('/nodes', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateNode(
  id: number,
  data: Partial<{
    name: string
    host: string
    port: number
    api_key: string
    destination_ip: string | null
    linked_vpn_node_id: number | null
  }>,
) {
  return apiFetch<import('../types').Node>(`/nodes/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function getProxyNodeStatus(nodeId: number) {
  return apiFetch<import('../types').ProxyStatusResponse>(`/nodes/${nodeId}/proxy/status`)
}

export async function putProxyNodeStatus(nodeId: number) {
  return apiFetch<import('../types').ProxyStatusResponse>(`/nodes/${nodeId}/proxy/status`, {
    method: 'PUT',
  })
}

export async function putProxyDestination(nodeId: number, destinationIp: string) {
  return apiFetch<import('../types').ProxyStatusResponse>(`/nodes/${nodeId}/proxy/destination`, {
    method: 'PUT',
    body: JSON.stringify({ destination_ip: destinationIp }),
  })
}

export async function getProxyMappings(nodeId: number) {
  return apiFetch<import('../types').ProxyMappingsResponse>(`/nodes/${nodeId}/proxy/mappings`)
}

export async function deleteNode(id: number) {
  return apiFetch(`/nodes/${id}`, { method: 'DELETE' })
}

export async function checkNodeHealth(id: number) {
  return apiFetch<{
    node_id: number
    status: import('../types').NodeStatus
    health: Record<string, unknown>
    last_seen_at?: string | null
  }>(`/nodes/${id}/health`, { method: 'POST' })
}

export async function activateNode(id: number) {
  return apiFetch<import('../types').ActiveNode>(`/nodes/${id}/activate`, { method: 'POST' })
}

export async function getNodeRemoteHosts(nodeId: number) {
  return apiFetch<import('../types').NodeRemoteHostsResponse>(`/nodes/${nodeId}/remote-hosts`)
}

export async function putNodeRemoteHosts(
  nodeId: number,
  hosts: string[],
  applyToWireguard = false,
) {
  return apiFetch<import('../types').NodeRemoteHostsResponse>(`/nodes/${nodeId}/remote-hosts`, {
    method: 'PUT',
    body: JSON.stringify({ hosts, apply_to_wireguard: applyToWireguard }),
  })
}

export async function allowFirstRemoteHost(nodeId: number) {
  return apiFetch<{ added: boolean; host: string; detail?: string; warnings?: string[] }>(
    `/nodes/${nodeId}/remote-hosts/allow-first`,
    { method: 'POST' },
  )
}

export async function getNodeOpenVpnMultihome(nodeId: number) {
  return apiFetch<import('../types').NodeOpenVpnMultihomeResponse>(
    `/nodes/${nodeId}/openvpn-multihome`,
  )
}

export async function putNodeOpenVpnMultihome(nodeId: number, enabled: boolean) {
  return apiFetch<import('../types').NodeOpenVpnMultihomeResponse>(
    `/nodes/${nodeId}/openvpn-multihome`,
    {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    },
  )
}

export async function checkNodeUpdates(id: number) {
  return apiFetch<{
    node_id: number
    agent: Record<string, unknown>
  }>(`/nodes/${id}/updates`)
}

export async function applyNodeUpdate(id: number) {
  return apiFetch<{
    node_id: number
    success: boolean
    message: string
    restarting: boolean
    before: Record<string, unknown>
    after: Record<string, unknown>
    detail: Record<string, unknown>
    errors: string[]
  }>(`/nodes/${id}/update`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function restartNodeAgent(id: number) {
  return apiFetch<{
    node_id: number
    success: boolean
    message: string
    restarting: boolean
  }>(`/nodes/${id}/restart-agent`, {
    method: 'POST',
  })
}

export async function rollingNodeUpdate(nodeIds: number[]) {
  return apiFetch<import('../types').BackgroundTaskAccepted>('/nodes/update-roll', {
    method: 'POST',
    body: JSON.stringify({ node_ids: nodeIds }),
  })
}

export async function getNodeSyncGroups() {
  return apiFetch<import('../types').NodeSyncGroup[]>('/nodes/sync-groups')
}

export async function createNodeSyncGroup(data: {
  name: string
  shared_domain: string
  shared_domain_wireguard?: string | null
  primary_node_id: number
  replica_node_ids: number[]
  sync_mode?: string
}) {
  return apiFetch<import('../types').NodeSyncGroup>('/nodes/sync-groups', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateNodeSyncGroup(
  id: number,
  data: Partial<{
    name: string
    shared_domain: string
    shared_domain_wireguard: string | null
    primary_node_id: number
    replica_node_ids: number[]
    sync_mode: string
  }>,
) {
  return apiFetch<import('../types').NodeSyncGroup>(`/nodes/sync-groups/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteNodeSyncGroup(id: number) {
  return apiFetch<{ message: string }>(`/nodes/sync-groups/${id}`, { method: 'DELETE' })
}

export async function setupNodeSyncGroup(id: number) {
  return apiFetch<{
    task_id: string
    group_id: number
    message: string
    queued?: boolean
    status_url?: string | null
  }>(`/nodes/sync-groups/${id}/setup`, { method: 'POST' })
}

export async function applyNodeSyncGroupSharedDomain(id: number) {
  return apiFetch<{
    task_id: string
    group_id: number
    message: string
    queued?: boolean
    status_url?: string | null
  }>(`/nodes/sync-groups/${id}/apply-shared-domain`, { method: 'POST' })
}

export async function verifyNodeSyncGroup(id: number) {
  return apiFetch<import('../types').NodeSyncVerifyResult>(`/nodes/sync-groups/${id}/verify`, {
    method: 'POST',
  })
}
