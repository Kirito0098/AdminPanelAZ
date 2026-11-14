import { createStorage } from '@/lib/safeStorage'

const storage = createStorage('sidebar-nav')

const GROUP_STATES = ['open', 'closed'] as const

/** Свёрнутость группы сайдбара переживает перезагрузку; по умолчанию группа открыта. */
export function readGroupOpen(id: string): boolean {
  return storage.readChoice(`group:${id}`, GROUP_STATES) !== 'closed'
}

export function writeGroupOpen(id: string, open: boolean): void {
  storage.write(`group:${id}`, open ? 'open' : 'closed')
}
