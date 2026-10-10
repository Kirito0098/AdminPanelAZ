import { describe, expect, it } from 'vitest'
import { parseHaVerifyResult } from './haVerifySummary'

describe('parseHaVerifyResult', () => {
  it('explains a replica still owing an OpenVPN restart', () => {
    const view = parseHaVerifyResult({
      ready: false,
      shared_domain: 'vpn.example.com',
      primary_node_id: 1,
      summary: 'Расхождения между основным узлом и репликой',
      replicas: [
        {
          node_id: 2,
          node_name: 'replica',
          online: true,
          mismatches: [{ kind: 'openvpn_restart_pending', detail: 'OpenVPN ещё не перезапущен' }],
        },
      ],
    })

    const [mismatch] = view.replicas[0].mismatches
    expect(mismatch.title).toBe('OpenVPN не перезапущен после смены сертификата сервера')
    expect(mismatch.details).toEqual(['OpenVPN ещё не перезапущен'])
    expect(mismatch.hint).toContain('перезапустит OpenVPN')
  })

  it('explains live WireGuard peers missing on the replica', () => {
    const view = parseHaVerifyResult({
      ready: false,
      shared_domain: 'vpn.example.com',
      primary_node_id: 1,
      summary: 'Расхождения между основным узлом и репликой',
      replicas: [
        {
          node_id: 2,
          node_name: 'replica',
          online: true,
          mismatches: [{ kind: 'wireguard_peers', only_primary: ['vpn: alice'], only_replica: [] }],
        },
      ],
    })

    const [mismatch] = view.replicas[0].mismatches
    expect(mismatch.title).toBe('Работающий WireGuard на реплике отличается')
    expect(mismatch.details).toEqual(['Есть только на основном (1): vpn: alice'])
    expect(mismatch.hint).toContain('Синхронизировать')
  })

  it('explains AWG2 clients missing on the replica', () => {
    const view = parseHaVerifyResult({
      ready: false,
      shared_domain: 'vpn.example.com',
      primary_node_id: 1,
      summary: 'Расхождения между основным узлом и репликой',
      replicas: [
        {
          node_id: 2,
          node_name: 'replica',
          online: true,
          mismatches: [{ kind: 'awg2_clients', only_primary: [], only_replica: ['bob'] }],
        },
      ],
    })

    const [mismatch] = view.replicas[0].mismatches
    expect(mismatch.title).toBe('Разные клиенты AZ-AWG2')
    expect(mismatch.details).toEqual(['Есть только на реплике (1): bob'])
  })

  it('lists live runtime checks among verify checks', () => {
    const view = parseHaVerifyResult({
      ready: true,
      shared_domain: 'vpn.example.com',
      primary_node_id: 1,
      summary: 'Готово к DNS-переключению',
      replicas: [],
    })

    expect(view.checkedSummary).toContain('работающие peer WireGuard')
    expect(view.checkedSummary).toContain('клиенты AZ-AWG2')
  })
})
