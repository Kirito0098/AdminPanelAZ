import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, Ban, CheckCircle2, Loader2, PauseCircle, Shield, Trash2 } from 'lucide-react'
import { formatDate } from '@/lib/datetime'
import type { User } from '@/types'

export type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning'
export type CardTone = 'active' | 'expiring' | 'expired' | 'suspended' | 'attention' | 'neutral'
export type MetaTone = 'default' | 'warning' | 'danger' | 'success'

/** Срок доступа: текст, тон строки и тон карточки. */
export function accessParts(user: User): {
  text: string
  tone: MetaTone
  cardTone: CardTone | null
} {
  if (!user.access_until) return { text: 'не задан', tone: 'default', cardTone: null }
  const d = new Date(user.access_until)
  const now = new Date()
  if (d < now) {
    return { text: `истёк ${formatDate(user.access_until)}`, tone: 'danger', cardTone: 'expired' }
  }
  if (d.getTime() <= now.getTime() + 7 * 86400000) {
    return { text: `до ${formatDate(user.access_until)}`, tone: 'warning', cardTone: 'expiring' }
  }
  return { text: formatDate(user.access_until), tone: 'default', cardTone: null }
}

/** Состояние карточки абонента: бейдж и тон. Общее для карточек и таблицы. */
export function resolveCardState(user: User): {
  tone: CardTone
  label: string
  variant: BadgeVariant
  icon: LucideIcon
} {
  // Абонент в удалении — первым: иначе карточка покажет «Отключён» (is_active=false).
  if ((user.provision_state ?? '') === 'pending_deletion') {
    return { tone: 'neutral', label: 'Удаляется', variant: 'outline', icon: Trash2 }
  }
  if (user.suspended_at) {
    return { tone: 'suspended', label: 'Приостановлен', variant: 'destructive', icon: PauseCircle }
  }
  if (user.is_active === false) {
    return { tone: 'neutral', label: 'Отключён', variant: 'outline', icon: Ban }
  }
  const access = accessParts(user)
  if (access.cardTone === 'expired') {
    return { tone: 'expired', label: 'Истёк', variant: 'destructive', icon: AlertTriangle }
  }
  if (access.cardTone === 'expiring') {
    return { tone: 'expiring', label: 'Истекает', variant: 'warning', icon: AlertTriangle }
  }
  const state = user.provision_state ?? 'unmanaged'
  if (state === 'partial') {
    return { tone: 'attention', label: 'Требует внимания', variant: 'warning', icon: AlertTriangle }
  }
  if (state === 'pending') {
    return { tone: 'attention', label: 'Применяется', variant: 'default', icon: Loader2 }
  }
  if (state === 'ok') {
    return { tone: 'active', label: 'Активный', variant: 'success', icon: CheckCircle2 }
  }
  return { tone: 'neutral', label: 'Без набора', variant: 'secondary', icon: Shield }
}
