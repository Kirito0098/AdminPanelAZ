import { describe, expect, it } from 'vitest'
import {
  PROXY_LINK_NONE,
  linkedVpnNodeIdFromSelectorValue,
  proxyLinkSelectorOptions,
  resolveProxyLinkSelectorValue,
  resolveProxyLinkTarget,
} from '@/lib/proxyLinkTarget'
import type { Node, NodeSyncGroup } from '@/types'

const nodes: Node[] = [
  {
    id: 1,
    name: 'primary',
    host: '10.0.0.1',
    port: 9100,
    status: 'online',
    is_local: false,
    mtls_enabled: false,
    node_kind: 'vpn',
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'replica',
    host: '10.0.0.2',
    port: 9100,
    status: 'online',
    is_local: false,
    mtls_enabled: false,
    node_kind: 'vpn',
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 3,
    name: 'standalone',
    host: '10.0.0.3',
    port: 9100,
    status: 'online',
    is_local: false,
    mtls_enabled: false,
    node_kind: 'vpn',
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 9,
    name: 'proxy-ru',
    host: '1.2.3.4',
    port: 9101,
    status: 'online',
    is_local: false,
    mtls_enabled: false,
    node_kind: 'proxy',
    linked_vpn_node_id: 1,
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const syncGroups: NodeSyncGroup[] = [
  {
    id: 10,
    name: 'Europe',
    shared_domain: 'eu.example.com',
    primary_node_id: 1,
    primary_node_name: 'primary',
    replica_node_ids: [2],
    replica_node_names: ['replica'],
    sync_mode: 'manual_full',
    sync_status: 'synced',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

describe('resolveProxyLinkTarget', () => {
  it('returns null when unlinked', () => {
    expect(resolveProxyLinkTarget(null, nodes, syncGroups)).toBeNull()
    expect(resolveProxyLinkTarget(undefined, nodes, syncGroups)).toBeNull()
  })

  it('labels HA membership when linked vpn is in a group', () => {
    expect(resolveProxyLinkTarget(1, nodes, syncGroups)).toEqual({
      kind: 'ha',
      label: 'HA «Europe»',
      shortLabel: 'Europe',
      vpnNodeId: 1,
      vpnNodeName: 'primary',
      haGroupId: 10,
      haGroupName: 'Europe',
    })
    expect(resolveProxyLinkTarget(2, nodes, syncGroups)?.kind).toBe('ha')
  })

  it('labels standalone vpn node', () => {
    expect(resolveProxyLinkTarget(3, nodes, syncGroups)).toEqual({
      kind: 'vpn',
      label: 'standalone',
      shortLabel: 'standalone',
      vpnNodeId: 3,
      vpnNodeName: 'standalone',
    })
  })

  it('labels missing vpn node', () => {
    expect(resolveProxyLinkTarget(99, nodes, syncGroups)).toEqual({
      kind: 'missing',
      label: 'узел #99 (не найден)',
      shortLabel: '#99',
      vpnNodeId: 99,
    })
  })
})

describe('proxy link selector helpers', () => {
  it('builds options without proxy nodes', () => {
    const options = proxyLinkSelectorOptions(nodes, syncGroups)
    expect(options.map((o) => o.key)).toEqual(['group:10', 'node:3'])
  })

  it('round-trips selector values', () => {
    const options = proxyLinkSelectorOptions(nodes, syncGroups)
    expect(resolveProxyLinkSelectorValue(null, nodes, syncGroups)).toBe(PROXY_LINK_NONE)
    expect(resolveProxyLinkSelectorValue(1, nodes, syncGroups)).toBe('group:10')
    expect(resolveProxyLinkSelectorValue(3, nodes, syncGroups)).toBe('node:3')
    expect(linkedVpnNodeIdFromSelectorValue(PROXY_LINK_NONE, options)).toBeNull()
    expect(linkedVpnNodeIdFromSelectorValue('group:10', options)).toBe(1)
    expect(linkedVpnNodeIdFromSelectorValue('node:3', options)).toBe(3)
  })
})
