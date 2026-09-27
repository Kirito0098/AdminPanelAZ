import { describe, expect, it } from 'vitest'

import { passkeyDeleteConfirm } from './passkeyConfirm'

describe('passkeyDeleteConfirm', () => {
  it('names the passkey and warns that it can no longer be used to sign in', () => {
    const texts = passkeyDeleteConfirm('MacBook Touch ID')
    expect(texts.title).toBe('Удалить passkey «MacBook Touch ID»?')
    expect(texts.description).toContain('Войти в панель с этим passkey больше не получится')
    expect(texts.description).toContain('Вернуть его нельзя')
    expect(texts.confirmLabel).toBe('Удалить')
  })
})
