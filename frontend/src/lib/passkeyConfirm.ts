export interface PasskeyDeleteConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function passkeyDeleteConfirm(nickname: string): PasskeyDeleteConfirm {
  return {
    title: `Удалить passkey «${nickname}»?`,
    description:
      'Войти в панель с этим passkey больше не получится. Вернуть его нельзя — при необходимости добавьте passkey заново.',
    confirmLabel: 'Удалить',
  }
}
