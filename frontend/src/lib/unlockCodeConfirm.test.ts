import { describe, expect, it } from 'vitest'

import { unlockCodeRevokeConfirm } from './unlockCodeConfirm'

describe('unlockCodeRevokeConfirm', () => {
  it('names the key and warns that revoking cannot be undone', () => {
    const texts = unlockCodeRevokeConfirm('AZ-7K2M-9QX4')
    expect(texts.title).toBe('Отозвать unlock-ключ «AZ-7K2M-9QX4»?')
    expect(texts.description).toContain('больше нельзя будет активировать')
    expect(texts.description).toContain('Вернуть ключ нельзя')
    expect(texts.confirmLabel).toBe('Отозвать')
  })

  it('says that access already extended by the key is kept', () => {
    expect(unlockCodeRevokeConfirm('AZ-0000').description).toContain('Уже продлённый по нему доступ сохранится')
  })
})
