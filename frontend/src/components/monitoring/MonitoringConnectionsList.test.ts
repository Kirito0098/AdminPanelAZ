import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import type { OpenVpnClient, WireGuardPeer } from '@/types'

import { buildMonitoringConnectionRows } from './MonitoringConnectionsList'

const baseOptions = {
  showOpenVpn: true,
  showWireGuard: true,
  isWireGuardOnline: () => true,
}

const originalTz = process.env.TZ

describe('buildMonitoringConnectionRows sortTime', () => {
  beforeAll(() => {
    process.env.TZ = 'Europe/Moscow'
  })

  afterAll(() => {
    if (originalTz === undefined) delete process.env.TZ
    else process.env.TZ = originalTz
  })

  it('reads a naive WireGuard handshake as UTC', () => {
    const peer: WireGuardPeer = {
      interface: 'wg0',
      public_key: 'pk',
      latest_handshake: '2026-09-27T11:14:54',
      transfer_rx: 0,
      transfer_tx: 0,
    }

    const [row] = buildMonitoringConnectionRows([], [peer], baseOptions)

    expect(row.sortTime).toBe(Date.UTC(2026, 8, 27, 11, 14, 54))
  })

  it('prefers connected_since_ts for OpenVPN', () => {
    const client: OpenVpnClient = {
      common_name: 'alice',
      real_address: '1.2.3.4:5555',
      virtual_address: '10.8.0.2',
      bytes_received: 0,
      bytes_sent: 0,
      connected_since: '2026-09-27 14:14:54',
      connected_since_ts: 1_790_507_694,
    }

    const [row] = buildMonitoringConnectionRows([client], [], baseOptions)

    expect(row.sortTime).toBe(1_790_507_694_000)
  })

  it('reads OpenVPN connected_since as local time when connected_since_ts is missing', () => {
    const client: OpenVpnClient = {
      common_name: 'alice',
      real_address: '1.2.3.4:5555',
      virtual_address: '10.8.0.2',
      bytes_received: 0,
      bytes_sent: 0,
      connected_since: '2026-09-27 14:14:54',
      connected_since_ts: 0,
    }

    const [row] = buildMonitoringConnectionRows([client], [], baseOptions)

    expect(row.sortTime).toBe(new Date(2026, 8, 27, 14, 14, 54).getTime())
  })
})
