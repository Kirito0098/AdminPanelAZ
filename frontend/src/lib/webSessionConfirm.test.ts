import { describe, expect, it } from 'vitest'

import { webSessionRevokeConfirm } from './webSessionConfirm'

describe('webSessionRevokeConfirm', () => {
  it('describes another session and warns that the device will be signed out', () => {
    const texts = webSessionRevokeConfirm({
      username: 'admin',
      remote_addr: '203.0.113.7',
      user_agent: 'Mozilla/5.0 Firefox/131.0',
      is_current: false,
    })
    expect(texts.title).toBe('Отозвать сессию «admin»?')
    expect(texts.description).toContain('IP: 203.0.113.7')
    expect(texts.description).toContain('Браузер: Mozilla/5.0 Firefox/131.0')
    expect(texts.description).toContain('Это устройство будет разлогинено')
    expect(texts.description).not.toContain('Вы выйдете')
    expect(texts.confirmLabel).toBe('Отозвать')
  })

  it('shows a dash for an unknown IP or browser', () => {
    const texts = webSessionRevokeConfirm({ username: 'ops', remote_addr: null, is_current: false })
    expect(texts.description).toContain('IP: —')
    expect(texts.description).toContain('Браузер: —')
  })

  it('warns that revoking the current session signs you out yourself', () => {
    const texts = webSessionRevokeConfirm({
      username: 'admin',
      remote_addr: '198.51.100.2',
      user_agent: 'Chrome',
      is_current: true,
    })
    expect(texts.title).toBe('Отозвать вашу текущую сессию?')
    expect(texts.description).toContain('IP: 198.51.100.2')
    expect(texts.description).toContain('Вы выйдете из панели на этом устройстве')
    expect(texts.confirmLabel).toBe('Отозвать и выйти')
  })
})
