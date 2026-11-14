import { describe, expect, it } from 'vitest'

import { unwrapErrorPayload } from './http'

describe('unwrapErrorPayload', () => {
  it('unwraps FastAPI HTTPException detail (confirm_deletions)', () => {
    const body = {
      detail: {
        code: 'confirm_deletions',
        configs: [{ node_id: 1, client_name: '123-2', vpn_type: 'openvpn' }],
      },
    }
    expect(unwrapErrorPayload(body)).toEqual({
      code: 'confirm_deletions',
      configs: [{ node_id: 1, client_name: '123-2', vpn_type: 'openvpn' }],
    })
  })

  it('keeps JSONResponse-level body (access_until_conflict)', () => {
    const body = { code: 'access_until_conflict', user_access_until: null }
    expect(unwrapErrorPayload(body)).toEqual(body)
  })

  it('passes through non-objects and null', () => {
    expect(unwrapErrorPayload(undefined)).toBeUndefined()
    expect(unwrapErrorPayload(null)).toBeNull()
    expect(unwrapErrorPayload('boom')).toBe('boom')
  })
})
