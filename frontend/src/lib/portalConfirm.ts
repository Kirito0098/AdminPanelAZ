export type PortalAction = 'rotate' | 'revoke'

interface PortalActionConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function portalActionConfirm(
  action: PortalAction,
  name: string,
  subject: 'пользователю' | 'клиенту',
): PortalActionConfirm {
  if (action === 'rotate') {
    return {
      title: `Перевыпустить ссылку портала для «${name}»?`,
      description: `Старая ссылка перестанет открываться — ${subject} нужно будет отправить новую ссылку.`,
      confirmLabel: 'Перевыпустить',
    }
  }
  return {
    title: `Отозвать ссылку портала для «${name}»?`,
    description: 'Старая ссылка перестанет открываться. Новую можно будет создать позже.',
    confirmLabel: 'Отозвать',
  }
}
