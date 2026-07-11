import { describe, expect, it } from 'vitest'
import {
  buildHaSelectorOptions,
  isHaGroupScopePath,
  resolveHaSelectorValue,
} from '@/lib/haNodeScope'
import type { Node, NodeHaContext, NodeSyncGroup } from '@/types'

const nodes: Node[] = [
  {
    id: 1,
    name: 'Локальный сервер',
    host: '127.0.0.1',
    port: 8443,
    status: 'online',
    is_local: true,
    mtls_enabled: false,
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'serv-2',
    host: '10.0.0.2',
    port: 8443,
    status: 'online',
    is_local: false,
    mtls_enabled: true,
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 3,
    name: 'standalone',
    host: '10.0.0.3',
    port: 8443,
    status: 'online',
    is_local: false,
    mtls_enabled: false,
    metadata: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const syncGroups: NodeSyncGroup[] = [
  {
    id: 10,
    name: 'General',
    shared_domain: 'vpn.example.com',
    primary_node_id: 1,
    primary_node_name: 'Локальный сервер',
    replica_node_ids: [2],
    replica_node_names: ['serv-2'],
    sync_mode: 'auto',
    sync_status: 'synced',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

describe('isHaGroupScopePath', () => {
  it('treats dashboard and HA-synced pages as HA scope', () => {
    expect(isHaGroupScopePath('/')).toBe(true)
    expect(isHaGroupScopePath('/traffic')).toBe(true)
    expect(isHaGroupScopePath('/routing')).toBe(true)
    expect(isHaGroupScopePath('/settings/vpn')).toBe(true)
    expect(isHaGroupScopePath('/edit-files')).toBe(true)
  })

  it('treats diagnostic pages as non-HA scope', () => {
    expect(isHaGroupScopePath('/logs')).toBe(false)
    expect(isHaGroupScopePath('/server-monitor')).toBe(false)
    expect(isHaGroupScopePath('/warper')).toBe(false)
    expect(isHaGroupScopePath('/monitoring')).toBe(false)
    expect(isHaGroupScopePath('/nodes')).toBe(false)
  })
})

describe('buildHaSelectorOptions', () => {
  it('returns HA groups and standalone nodes without replicas', () => {
    const options = buildHaSelectorOptions(nodes, syncGroups)
    expect(options).toHaveLength(2)
    expect(options[0]).toMatchObject({
      type: 'group',
      key: 'group:10',
      label: 'General',
      primaryNodeId: 1,
      sharedDomain: 'vpn.example.com',
    })
    expect(options[1]).toMatchObject({
      type: 'node',
      key: 'node:3',
      label: 'standalone',
    })
    expect(options.some((option) => option.type === 'node' && option.nodeId === 2)).toBe(false)
  })
})

describe('resolveHaSelectorValue', () => {
  it('maps primary HA node to group selector value', () => {
    const ha: NodeHaContext = {
      sync_group_id: 10,
      group_name: 'General',
      shared_domain: 'vpn.example.com',
      role: 'primary',
      primary_node_id: 1,
      primary_node_name: 'Локальный сервер',
      sync_mode: 'auto',
      sync_status: 'synced',
    }
    expect(resolveHaSelectorValue(nodes[0], ha, syncGroups)).toBe('group:10')
  })

  it('maps replica HA node to group selector value', () => {
    const ha: NodeHaContext = {
      sync_group_id: 10,
      group_name: 'General',
      shared_domain: 'vpn.example.com',
      role: 'replica',
      primary_node_id: 1,
      primary_node_name: 'Локальный сервер',
      sync_mode: 'auto',
      sync_status: 'synced',
    }
    expect(resolveHaSelectorValue(nodes[1], ha, syncGroups)).toBe('group:10')
  })

  it('maps standalone node to node selector value', () => {
    expect(resolveHaSelectorValue(nodes[2], null, syncGroups)).toBe('node:3')
  })
})
