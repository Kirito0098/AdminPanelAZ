import { describe, expect, it } from 'vitest'

import { twoFactorBackupCodesConfirm } from './twoFactorConfirm'

describe('twoFactorBackupCodesConfirm', () => {
  it('warns that the old backup codes stop working and asks to save the new ones', () => {
    const texts = twoFactorBackupCodesConfirm(7)
    expect(texts.title).toBe('Выпустить новые резервные коды?')
    expect(texts.description).toContain('Старые резервные коды перестанут действовать')
    expect(texts.description).toContain('сохраните новые')
    expect(texts.confirmLabel).toBe('Продолжить')
  })

  it('says how many old codes will stop working', () => {
    expect(twoFactorBackupCodesConfirm(7).description).toContain('Сейчас осталось: 7')
    expect(twoFactorBackupCodesConfirm(0).description).not.toContain('Сейчас осталось')
  })

  it('asks for the app code only after the warning', () => {
    const texts = twoFactorBackupCodesConfirm(3)
    expect(texts.description).toContain('введите код из приложения')
    expect(texts.codeHint).toContain('Старые резервные коды перестанут действовать')
    expect(texts.submitLabel).toBe('Получить новые коды')
  })
})
