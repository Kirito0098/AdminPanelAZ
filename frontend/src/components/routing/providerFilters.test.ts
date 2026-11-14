import { describe, expect, it } from 'vitest'

import { filterProviders, type FilterableProvider } from './providerFilters'

interface TestProvider extends FilterableProvider {
  filename: string
  name: string
  category: string
  description?: string
  enabled?: boolean
  tags?: string[]
}

const PROVIDERS: TestProvider[] = [
  {
    filename: 'akamai-ips.txt',
    name: 'Akamai',
    category: 'cdn',
    description: 'CDN и защита от DDoS',
    enabled: true,
    tags: ['streaming', 'enterprise'],
  },
  {
    filename: 'digitalocean-ips.txt',
    name: 'DigitalOcean',
    category: 'cloud',
    description: 'Облачный хостинг',
    enabled: false,
    tags: ['hosting', 'gaming'],
  },
  {
    filename: 'hetzner-ips.txt',
    name: 'Hetzner',
    category: 'hosting',
    enabled: true,
    tags: [],
  },
]

const names = (providers: ReadonlyArray<FilterableProvider>) => providers.map((p) => p.name)

const tagsOf = (provider: FilterableProvider) => {
  const source = PROVIDERS.find((p) => p.filename === provider.filename)
  return source?.tags
}

describe('filterProviders', () => {
  it('returns every provider for an empty or blank query', () => {
    expect(filterProviders(PROVIDERS)).toHaveLength(3)
    expect(filterProviders(PROVIDERS, { query: '' })).toHaveLength(3)
    expect(filterProviders(PROVIDERS, { query: '   ' })).toHaveLength(3)
  })

  it('matches by name ignoring case', () => {
    expect(names(filterProviders(PROVIDERS, { query: 'akamai' }))).toEqual(['Akamai'])
    expect(names(filterProviders(PROVIDERS, { query: 'AKAMAI' }))).toEqual(['Akamai'])
    expect(names(filterProviders(PROVIDERS, { query: ' digital ' }))).toEqual(['DigitalOcean'])
  })

  it('matches by filename and its slug', () => {
    expect(names(filterProviders(PROVIDERS, { query: 'digitalocean-ips.txt' }))).toEqual([
      'DigitalOcean',
    ])
    expect(names(filterProviders(PROVIDERS, { query: 'hetzner' }))).toEqual(['Hetzner'])
  })

  it('matches by description', () => {
    expect(names(filterProviders(PROVIDERS, { query: 'ddos' }))).toEqual(['Akamai'])
  })

  it('matches by tag through tagsOf', () => {
    expect(names(filterProviders(PROVIDERS, { query: 'gaming', tagsOf }))).toEqual([
      'DigitalOcean',
    ])
    expect(names(filterProviders(PROVIDERS, { query: 'enterprise', tagsOf }))).toEqual(['Akamai'])
  })

  it('matches by category slug and its Russian label', () => {
    expect(names(filterProviders(PROVIDERS, { query: 'cloud' }))).toEqual(['DigitalOcean'])
    expect(names(filterProviders(PROVIDERS, { query: 'облако' }))).toEqual(['DigitalOcean'])
  })

  it('filters by category', () => {
    expect(names(filterProviders(PROVIDERS, { category: 'cdn' }))).toEqual(['Akamai'])
    expect(names(filterProviders(PROVIDERS, { category: 'all' }))).toHaveLength(3)
  })

  it('filters by status with never as the default', () => {
    const statuses: Record<string, string> = {
      'akamai-ips.txt': 'ok',
      'digitalocean-ips.txt': 'error',
    }
    const statusOf = (provider: FilterableProvider) => statuses[provider.filename]

    expect(names(filterProviders(PROVIDERS, { status: 'ok', statusOf }))).toEqual(['Akamai'])
    expect(names(filterProviders(PROVIDERS, { status: 'error', statusOf }))).toEqual([
      'DigitalOcean',
    ])
    expect(names(filterProviders(PROVIDERS, { status: 'never', statusOf }))).toEqual(['Hetzner'])
    expect(names(filterProviders(PROVIDERS, { status: 'never' }))).toHaveLength(3)
  })

  it('combines quick filters with query and category', () => {
    const statusOf = (provider: FilterableProvider) =>
      provider.filename === 'digitalocean-ips.txt' ? 'error' : 'ok'

    expect(names(filterProviders(PROVIDERS, { quickFilter: 'enabled' }))).toEqual([
      'Akamai',
      'Hetzner',
    ])
    expect(names(filterProviders(PROVIDERS, { quickFilter: 'disabled' }))).toEqual([
      'DigitalOcean',
    ])
    expect(names(filterProviders(PROVIDERS, { quickFilter: 'errors', statusOf }))).toEqual([
      'DigitalOcean',
    ])
    expect(
      names(filterProviders(PROVIDERS, { query: 'digital', quickFilter: 'enabled' })),
    ).toEqual([])
    expect(
      names(filterProviders(PROVIDERS, { category: 'cloud', quickFilter: 'errors', statusOf })),
    ).toEqual(['DigitalOcean'])
  })

  it('runs needsCompile and needsDeploy predicates only for their quick filters', () => {
    const needsCompile = (provider: FilterableProvider) => provider.name === 'Hetzner'

    expect(names(filterProviders(PROVIDERS, { quickFilter: 'needs_compile', needsCompile }))).toEqual(
      ['Hetzner'],
    )
    expect(names(filterProviders(PROVIDERS, { needsCompile }))).toHaveLength(3)
  })
})
