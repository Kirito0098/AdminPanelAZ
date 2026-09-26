export type UserPortalAction = 'rotate' | 'revoke'

export interface UserPortalActionConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function userPortalActionConfirm(action: UserPortalAction, username: string): UserPortalActionConfirm {
  if (action === 'rotate') {
    return {
      title: `Перевыпустить ссылку портала для «${username}»?`,
      description: 'Старая ссылка перестанет открываться — пользователю нужно будет отправить новую ссылку.',
      confirmLabel: 'Перевыпустить',
    }
  }
  return {
    title: `Отозвать ссылку портала для «${username}»?`,
    description: 'Старая ссылка перестанет открываться. Новую можно будет создать позже.',
    confirmLabel: 'Отозвать',
  }
}
