import { describe, expect, it } from 'vitest'

import { clientPortalActionConfirm } from './clientPortalConfirm'

describe('clientPortalActionConfirm', () => {
  it('warns that rotating breaks the link the client already has', () => {
    const texts = clientPortalActionConfirm('rotate', 'phone-alice')
    expect(texts.title).toBe('Перевыпустить ссылку портала для «phone-alice»?')
    expect(texts.description).toContain('Старая ссылка перестанет открываться')
    expect(texts.description).toContain('клиенту нужно будет отправить новую ссылку')
    expect(texts.confirmLabel).toBe('Перевыпустить')
  })

  it('warns that revoking leaves the client without a working link', () => {
    const texts = clientPortalActionConfirm('revoke', 'laptop-bob')
    expect(texts.title).toBe('Отозвать ссылку портала для «laptop-bob»?')
    expect(texts.description).toContain('Старая ссылка перестанет открываться')
    expect(texts.description).not.toContain('новую ссылку')
    expect(texts.confirmLabel).toBe('Отозвать')
  })
})
