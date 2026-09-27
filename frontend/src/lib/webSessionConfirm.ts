import type { ActiveWebSession } from '@/types'

export type WebSessionSummary = Pick<ActiveWebSession, 'username' | 'remote_addr' | 'user_agent' | 'is_current'>

export interface WebSessionRevokeConfirm {
  title: string
  description: string
  confirmLabel: string
}

export function webSessionRevokeConfirm(session: WebSessionSummary): WebSessionRevokeConfirm {
  const details = `IP: ${session.remote_addr || '—'}. Браузер: ${session.user_agent || '—'}.`
  if (session.is_current) {
    return {
      title: 'Отозвать вашу текущую сессию?',
      description: `${details} Вы выйдете из панели на этом устройстве — войти нужно будет заново.`,
      confirmLabel: 'Отозвать и выйти',
    }
  }
  return {
    title: `Отозвать сессию «${session.username}»?`,
    description: `${details} Это устройство будет разлогинено при следующем обращении к панели.`,
    confirmLabel: 'Отозвать',
  }
}
