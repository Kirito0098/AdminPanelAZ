import { describe, expect, it } from 'vitest'

import type { PortalClientEntry, PortalNodeEntry } from '@/api/portal'
import { normalizePortalNodes, pickPortalSelection, portalClientKey, portalProfileLabel } from './portalNodes'

function client(nodeId: number, name: string): PortalClientEntry {
  return { node_id: nodeId, client_name: name, protocols: ['wireguard'], files: [] }
}

const nodes: PortalNodeEntry[] = [
  { node_id: 2, label: 'Германия', clients: [client(2, 'carol')] },
  { node_id: 1, label: 'Финляндия', clients: [client(1, 'alice'), client(1, 'bob')] },
]

describe('normalizePortalNodes', () => {
  it('returns user nodes as is', () => {
    expect(normalizePortalNodes({ kind: 'user', brand_title: 'VPN', unlock_codes_enabled: false, nodes })).toBe(nodes)
  })

  it('wraps a client link into one node with one client', () => {
    const result = normalizePortalNodes({
      kind: 'client',
      brand_title: 'VPN',
      unlock_codes_enabled: false,
      node_id: 4,
      client_name: 'dave',
      protocols: ['openvpn'],
      files: [],
    })
    expect(result).toEqual([
      {
        node_id: 4,
        label: '',
        clients: [{ node_id: 4, client_name: 'dave', protocols: ['openvpn'], files: [], status: undefined }],
      },
    ])
  })
})

describe('pickPortalSelection', () => {
  it('defaults to the first node and its first client', () => {
    const sel = pickPortalSelection(nodes, null, '')
    expect(sel.node?.node_id).toBe(2)
    expect(sel.client?.client_name).toBe('carol')
  })

  it('keeps an existing node and client', () => {
    const sel = pickPortalSelection(nodes, 1, portalClientKey(client(1, 'bob')))
    expect(sel.node?.node_id).toBe(1)
    expect(sel.client?.client_name).toBe('bob')
  })

  it('falls back to the first client of the same node when the client is gone', () => {
    const sel = pickPortalSelection(nodes, 1, '1:zed')
    expect(sel.node?.node_id).toBe(1)
    expect(sel.client?.client_name).toBe('alice')
  })

  it('falls back to the first node when the node is gone', () => {
    const sel = pickPortalSelection(nodes, 9, '9:x')
    expect(sel.node?.node_id).toBe(2)
    expect(sel.client?.client_name).toBe('carol')
  })

  it('returns nulls for an empty list', () => {
    expect(pickPortalSelection([], null, '')).toEqual({ node: null, client: null })
  })
})

describe('portalProfileLabel', () => {
  it('prefixes the node label when there are several nodes', () => {
    expect(portalProfileLabel(nodes, pickPortalSelection(nodes, 1, '1:bob'))).toBe('Финляндия · bob')
  })

  it('shows only the client name for a single node', () => {
    const single = [nodes[1]]
    expect(portalProfileLabel(single, pickPortalSelection(single, 1, '1:bob'))).toBe('bob')
  })

  it('shows the empty state without a client', () => {
    expect(portalProfileLabel([], { node: null, client: null })).toBe('Нет профилей')
  })
})
