export type ClientPortalAction = 'rotate' | 'revoke'

export interface ClientPortalActionConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function clientPortalActionConfirm(action: ClientPortalAction, clientName: string): ClientPortalActionConfirm {
  if (action === 'rotate') {
    return {
      title: `Перевыпустить ссылку портала для «${clientName}»?`,
      description: 'Старая ссылка перестанет открываться — клиенту нужно будет отправить новую ссылку.',
      confirmLabel: 'Перевыпустить',
    }
  }
  return {
    title: `Отозвать ссылку портала для «${clientName}»?`,
    description: 'Старая ссылка перестанет открываться. Новую можно будет создать позже.',
    confirmLabel: 'Отозвать',
  }
}
