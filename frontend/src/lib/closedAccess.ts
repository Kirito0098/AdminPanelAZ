import type { ClosedAccessView } from '@/types'
import { parseTimestamp } from '@/lib/datetime'

export type ClosedAccessTone = 'danger' | 'warning'

export interface ClosedAccessCopy {
  tone: ClosedAccessTone
  /** Заголовок баннера. */
  title: string
  /** Пояснение под заголовком (причина приостановки и т.п.). */
  description: string | null
  /** Показать действие «Ввести ключ» (продление unlock-кодом). */
  canRedeem: boolean
  /** Подпись основного действия продления. */
  redeemLabel: string
  /** Показать действие «Запросить продление» (Stage 2, Telegram). */
  canRequest: boolean
  /** Показать действие «Написать администратору». */
  canContact: boolean
}

/** Дата в формате DD.MM (спека 7.4). */
export function shortDayMonth(value: string | null | undefined): string {
  const date = parseTimestamp(value)
  if (!date) return ''
  try {
    return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' }).format(date)
  } catch {
    return ''
  }
}

/** Тексты и доступные действия закрытого доступа (спека 7.4). */
export function closedAccessCopy(view: ClosedAccessView | null | undefined): ClosedAccessCopy | null {
  if (!view) return null
  const day = shortDayMonth(view.access_until)
  switch (view.state) {
    case 'expired':
      return {
        tone: 'danger',
        title: day ? `Доступ истёк ${day}` : 'Доступ истёк',
        description: 'Продлите доступ unlock-ключом, чтобы снова пользоваться конфигами.',
        canRedeem: true,
        redeemLabel: 'Ввести ключ',
        canRequest: Boolean(view.requests_enabled),
        canContact: false,
      }
    case 'traffic_limit':
      return {
        tone: 'danger',
        title: 'Лимит трафика исчерпан',
        description: 'Откроется после продления — введите unlock-ключ.',
        canRedeem: true,
        redeemLabel: 'Ввести ключ',
        canRequest: Boolean(view.requests_enabled),
        canContact: false,
      }
    case 'suspended':
      return {
        tone: 'danger',
        title: 'Доступ приостановлен администратором',
        description: view.reason ? `Причина: ${view.reason}` : null,
        canRedeem: false,
        redeemLabel: 'Продлить',
        canRequest: false,
        canContact: Boolean(view.contact_url),
      }
    case 'expiring':
    default:
      return {
        tone: 'warning',
        title: day ? `Доступ до ${day}` : 'Доступ скоро истечёт',
        description: 'Продлите доступ заранее, чтобы не остаться без подключения.',
        canRedeem: true,
        redeemLabel: 'Продлить',
        canRequest: Boolean(view.requests_enabled),
        canContact: false,
      }
  }
}
