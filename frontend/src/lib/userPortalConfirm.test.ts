import { describe, expect, it } from 'vitest'

import { userPortalActionConfirm } from './userPortalConfirm'

describe('userPortalActionConfirm', () => {
  it('warns that rotating breaks the link the user already has', () => {
    const texts = userPortalActionConfirm('rotate', 'alice')
    expect(texts.title).toBe('Перевыпустить ссылку портала для «alice»?')
    expect(texts.description).toContain('Старая ссылка перестанет открываться')
    expect(texts.description).toContain('новую ссылку')
    expect(texts.confirmLabel).toBe('Перевыпустить')
  })

  it('warns that revoking leaves the user without a working link', () => {
    const texts = userPortalActionConfirm('revoke', 'bob')
    expect(texts.title).toBe('Отозвать ссылку портала для «bob»?')
    expect(texts.description).toContain('Старая ссылка перестанет открываться')
    expect(texts.description).not.toContain('новую ссылку')
    expect(texts.confirmLabel).toBe('Отозвать')
  })
})
