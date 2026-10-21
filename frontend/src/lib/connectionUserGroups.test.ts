import { describe, expect, it } from 'vitest'
import { groupConnectionsByOwner, type OwnerGroupableConnection } from './connectionUserGroups'

function connection(
  overrides: Partial<OwnerGroupableConnection> & { key: string },
): OwnerGroupableConnection & { key: string } {
  return {
    protocol: 'openvpn',
    online: true,
    rx: 0,
    tx: 0,
    sortTime: 0,
    ...overrides,
  }
}

describe('groupConnectionsByOwner', () => {
  it('aggregates connections, protocols and nodes per owner', () => {
    const groups = groupConnectionsByOwner([
      connection({
        key: 'a',
        ownerId: 1,
        ownerName: 'alice',
        rx: 100,
        tx: 20,
        sortTime: 10,
        activeNodeName: 'primary',
      }),
      connection({
        key: 'b',
        ownerId: 1,
        ownerName: 'alice',
        protocol: 'wireguard',
        online: false,
        rx: 5,
        tx: 5,
        sortTime: 30,
        nodeName: 'replica',
      }),
      connection({
        key: 'c',
        ownerId: null,
        ownerName: null,
        rx: 1,
        tx: 1,
        sortTime: 20,
      }),
    ])

    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({
      key: 'user:1',
      ownerName: 'alice',
      connectionsCount: 2,
      onlineCount: 1,
      rx: 105,
      tx: 25,
      lastActivity: 30,
    })
    expect(groups[0].protocols).toEqual(['openvpn', 'wireguard'])
    expect(groups[0].nodes).toEqual(['primary', 'replica'])
    expect(groups[1].key).toBe('unowned')
    expect(groups[1].ownerName).toBe('Без владельца')
  })

  it('orders groups online-first and then by traffic', () => {
    const groups = groupConnectionsByOwner([
      connection({ key: 'a', ownerId: 1, ownerName: 'offline', online: false, rx: 1000 }),
      connection({ key: 'b', ownerId: 2, ownerName: 'online-small', online: true, rx: 1 }),
      connection({ key: 'c', ownerId: 3, ownerName: 'online-big', online: true, rx: 500 }),
    ])

    expect(groups.map((group) => group.ownerName)).toEqual(['online-big', 'online-small', 'offline'])
  })
})
