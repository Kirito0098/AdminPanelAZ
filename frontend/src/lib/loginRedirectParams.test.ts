import { describe, expect, it } from 'vitest'

import { TG_ERROR_MAX_LENGTH, readLoginRedirectParams } from './loginRedirectParams'

function read(hash: string, query: string) {
  return readLoginRedirectParams(hash, new URLSearchParams(query))
}

describe('readLoginRedirectParams', () => {
  it('reads nothing from a plain login page', () => {
    expect(read('', '')).toEqual({ token: null, tgError: null })
  })

  it('does not decode the Telegram error twice', () => {
    expect(read('', 'tg_error=%25').tgError).toBe('%')
    expect(read('', 'tg_error=50%25%20done').tgError).toBe('50% done')
    expect(read('', 'tg_error=%2541').tgError).toBe('%41')
    expect(read('', 'tg_error=%D0%9E%D1%88%D0%B8%D0%B1%D0%BA%D0%B0').tgError).toBe('Ошибка')
  })

  it('survives malformed escapes', () => {
    expect(read('', 'tg_error=%').tgError).toBe('%')
    expect(read('', 'tg_error=%E0%A4%A').tgError).not.toBeNull()
    expect(read('#token=%', '').token).toBe('%')
    expect(read('#token=%E0%A4%A', '').token).toBe('%E0%A4%A')
  })

  it('decodes the token from the hash once and takes the query token as is', () => {
    expect(read('#token=a%2Eb.c', '').token).toBe('a.b.c')
    expect(read('', 'token=a.b.c').token).toBe('a.b.c')
    expect(read('', 'token=a%252Eb').token).toBe('a%2Eb')
    expect(read('#token=h', 'token=q').token).toBe('h')
  })

  it('ignores an empty error and caps a long one', () => {
    expect(read('', 'tg_error=').tgError).toBeNull()
    expect(read('', 'tg_error=%20%20').tgError).toBeNull()
    const long = read('', `tg_error=${'x'.repeat(TG_ERROR_MAX_LENGTH + 50)}`).tgError
    expect(long).toHaveLength(TG_ERROR_MAX_LENGTH)
  })
})
