import { describe, expect, it } from 'vitest'

import { readLoginRedirectParams } from './loginRedirectParams'

function read(hash: string, query: string) {
  return readLoginRedirectParams(hash, new URLSearchParams(query))
}

describe('readLoginRedirectParams', () => {
  it('reads nothing from a plain login page', () => {
    expect(read('', '')).toEqual({ token: null, webSessionId: null, tgError: null })
  })

  it('reads the web session id the Telegram login passes next to the token', () => {
    expect(read('#token=a.b.c&session=0123abcdef', '')).toEqual({
      token: 'a.b.c',
      webSessionId: '0123abcdef',
      tgError: null,
    })
    expect(read('#token=a.b.c', '').webSessionId).toBeNull()
    expect(read('#token=a.b.c&session=', '').webSessionId).toBeNull()
  })

  it('accepts a session id only as a header-safe value next to a hash token', () => {
    expect(read('#token=t&session=a%0Ab', '').webSessionId).toBeNull()
    expect(read('#token=t&session=a%20b', '').webSessionId).toBeNull()
    expect(read(`#token=t&session=${'a'.repeat(65)}`, '').webSessionId).toBeNull()
    expect(read(`#token=t&session=${'a'.repeat(64)}`, '').webSessionId).toBe('a'.repeat(64))
    expect(read('#session=abc', '').webSessionId).toBeNull()
    expect(read('', 'token=t&session=abc').webSessionId).toBeNull()
  })

  it('decodes the token from the hash once', () => {
    expect(read('#token=a%2Eb.c', '').token).toBe('a.b.c')
    expect(read('#token=h', 'token=q').token).toBe('h')
  })

  it('ignores a token in the query string', () => {
    expect(read('', 'token=a.b.c').token).toBeNull()
    expect(read('#token=&session=abc', 'token=q')).toEqual({ token: null, webSessionId: null, tgError: null })
  })
})
