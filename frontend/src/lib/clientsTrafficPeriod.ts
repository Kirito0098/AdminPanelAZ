import { createStorage } from './safeStorage'

export const CLIENTS_TRAFFIC_PERIODS = ['1', '7', '30', '90', 'all'] as const
export type ClientsTrafficPeriod = (typeof CLIENTS_TRAFFIC_PERIODS)[number]

export const DEFAULT_CLIENTS_TRAFFIC_PERIOD: ClientsTrafficPeriod = '30'

export const CLIENTS_TRAFFIC_PERIOD_OPTIONS: { value: ClientsTrafficPeriod; label: string }[] = [
  { value: '1', label: '1 день' },
  { value: '7', label: '7 дней' },
  { value: '30', label: '30 дней' },
  { value: '90', label: '90 дней' },
  { value: 'all', label: 'всё время' },
]

const storage = createStorage('clients-traffic-period')

export function loadClientsTrafficPeriod(): ClientsTrafficPeriod {
  return (
    storage.readChoice('period', CLIENTS_TRAFFIC_PERIODS) ?? DEFAULT_CLIENTS_TRAFFIC_PERIOD
  )
}

export function saveClientsTrafficPeriod(period: ClientsTrafficPeriod) {
  storage.write('period', period)
}
