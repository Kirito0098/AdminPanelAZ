import { useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'

type PageTabOptions<T extends string> = {
  /** Вкладки уже отфильтрованы по правам и feature-флагам, список не пустой. */
  tabs: readonly T[]
  /** Имя query-параметра. Вложенные вкладки используют своё (`log`, `scope`). */
  param?: string
  /** Что показать, если в URL неизвестное значение. По умолчанию первая вкладка. */
  fallback?: T
}

/**
 * Вкладка страницы живёт в URL: ссылку можно переслать, «назад» возвращает
 * на предыдущую вкладку. Остальные параметры (`client`, `user`, `requests`)
 * не теряются, hash сохраняется.
 */
export function usePageTab<T extends string>({
  tabs,
  param = 'tab',
  fallback,
}: PageTabOptions<T>): readonly [T, (next: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get(param)
  const tab = (
    requested && (tabs as readonly string[]).includes(requested)
      ? requested
      : (fallback ?? tabs[0])
  ) as T

  // Radix Tabs зовёт onValueChange и на mousedown, и на click: без ref одна
  // вкладка даёт две записи в истории и «назад» не возвращает предыдущую.
  const lastWritten = useRef<T>(tab)
  useEffect(() => {
    lastWritten.current = tab
  }, [tab])

  const setTab = useCallback(
    (next: T) => {
      if (lastWritten.current === next) return
      lastWritten.current = next
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev)
          params.set(param, next)
          return params
        },
        { replace: false },
      )
    },
    [param, setSearchParams],
  )

  return [tab, setTab] as const
}
