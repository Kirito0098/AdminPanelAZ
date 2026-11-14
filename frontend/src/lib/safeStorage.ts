/**
 * localStorage с префиксом раздела: недоступен в SSR и молча переживает
 * приватный режим и переполнение квоты.
 */
export function createStorage(prefix: string) {
  const keyOf = (name: string) => `${prefix}:${name}`

  function read(name: string): string | null {
    if (typeof window === 'undefined') return null
    try {
      return window.localStorage.getItem(keyOf(name))
    } catch {
      return null
    }
  }

  function write(name: string, value: string): void {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(keyOf(name), value)
    } catch {
      /* ignore quota / private mode */
    }
  }

  function readChoice<T extends string>(name: string, allowed: readonly T[]): T | null {
    const value = read(name)
    return value && (allowed as readonly string[]).includes(value) ? (value as T) : null
  }

  return { read, write, readChoice }
}
