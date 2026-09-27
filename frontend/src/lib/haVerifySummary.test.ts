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
})
