export interface TwoFactorBackupCodesConfirm {
  title: string
  description: string
  confirmLabel: string
  codeHint: string
  submitLabel: string
}

export function twoFactorBackupCodesConfirm(backupRemaining: number): TwoFactorBackupCodesConfirm {
  const remaining = backupRemaining > 0 ? ` Сейчас осталось: ${backupRemaining}.` : ''
  return {
    title: 'Выпустить новые резервные коды?',
    description: `Старые резервные коды перестанут действовать сразу после выпуска новых.${remaining} Новые коды будут показаны один раз — сохраните новые в надёжном месте. После подтверждения введите код из приложения.`,
    confirmLabel: 'Продолжить',
    codeHint: 'Введите код из приложения. Старые резервные коды перестанут действовать — сохраните новые.',
    submitLabel: 'Получить новые коды',
  }
}
