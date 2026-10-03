interface UnlockCodeRevokeConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function unlockCodeRevokeConfirm(code: string): UnlockCodeRevokeConfirm {
  return {
    title: `Отозвать unlock-ключ «${code}»?`,
    description:
      'Ключ больше нельзя будет активировать. Вернуть ключ нельзя — при необходимости создайте новый. Уже продлённый по нему доступ сохранится.',
    confirmLabel: 'Отозвать',
  }
}
