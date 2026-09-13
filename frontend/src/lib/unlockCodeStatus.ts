import type { UnlockCodeRecord } from '@/types'

export function unlockCodeRedeemedCount(code: UnlockCodeRecord): number {
  if (typeof code.redemption_count === 'number') return code.redemption_count
  return code.redemptions?.length ?? 0
}

export function isUnlockCodeExhausted(code: UnlockCodeRecord): boolean {
  if (typeof code.exhausted === 'boolean') return code.exhausted
  return unlockCodeRedeemedCount(code) >= code.max_redemptions
}

export function unlockCodeStatusLabel(code: UnlockCodeRecord): string | null {
  if (code.revoked_at) return 'Отозван'
  if (isUnlockCodeExhausted(code)) {
    return code.mode === 'single' ? 'Активирован' : 'Исчерпан'
  }
  if (unlockCodeRedeemedCount(code) > 0) return 'Частично'
  return null
}
