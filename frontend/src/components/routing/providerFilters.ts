import { providerCategoryLabel, providerSlug } from './utils'

/** Минимальный набор полей провайдера, нужный фильтру. */
export interface FilterableProvider {
  filename: string
  name: string
  category: string
  description?: string | null
  enabled?: boolean
}

export type ProviderQuickFilter =
  | 'all'
  | 'enabled'
  | 'disabled'
  | 'errors'
  | 'needs_deploy'
  | 'needs_compile'

export interface ProviderFilterOptions<P extends FilterableProvider> {
  /** Поиск без учёта регистра: имя, файл, slug, описание, теги, категория. */
  query?: string
  /** Категория провайдера или `all`. */
  category?: string
  /** Статус обновления в БД (ok/partial/error/never) или `all`. */
  status?: string
  /** Статус из метаданных БД; отсутствие значения считается `never`. */
  statusOf?: (provider: P) => string | null | undefined
  quickFilter?: ProviderQuickFilter
  needsCompile?: (provider: P) => boolean
  needsDeploy?: (provider: P) => boolean
  /** Теги из метаданных БД: тоже участвуют в поиске. */
  tagsOf?: (provider: P) => readonly string[] | null | undefined
}

/**
 * Единый фильтр провайдеров для вкладок маршрутизации.
 * Пустой запрос не сужает список: возвращаются все провайдеры, подходящие под категорию и статус.
 */
export function filterProviders<P extends FilterableProvider>(
  providers: readonly P[],
  options: ProviderFilterOptions<P> = {},
): P[] {
  const {
    query = '',
    category = 'all',
    status = 'all',
    statusOf,
    quickFilter = 'all',
    needsCompile,
    needsDeploy,
    tagsOf,
  } = options
  const q = query.trim().toLowerCase()

  return providers.filter((provider) => {
    if (category !== 'all' && provider.category !== category) return false

    const dbStatus = statusOf?.(provider) ?? 'never'
    if (status !== 'all' && dbStatus !== status) return false

    if (quickFilter === 'enabled' && !provider.enabled) return false
    if (quickFilter === 'disabled' && provider.enabled) return false
    if (quickFilter === 'errors' && dbStatus !== 'error') return false
    if (quickFilter === 'needs_deploy' && !needsDeploy?.(provider)) return false
    if (quickFilter === 'needs_compile' && !needsCompile?.(provider)) return false

    if (!q) return true

    const haystack = [
      provider.name,
      provider.filename,
      providerSlug(provider.filename),
      provider.description ?? '',
      ...(tagsOf?.(provider) ?? []),
      provider.category,
      providerCategoryLabel(provider.category),
    ]
    return haystack.some((value) => value.toLowerCase().includes(q))
  })
}
