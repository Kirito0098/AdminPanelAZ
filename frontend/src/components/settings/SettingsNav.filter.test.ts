// frontend/src/components/settings/SettingsNav.filter.test.ts
import { describe, expect, it } from 'vitest'
import { User, Users } from 'lucide-react'
import { filterNavGroupsByQuery, type SettingsNavGroup } from './SettingsNav'

const SAMPLE: SettingsNavGroup[] = [
  {
    label: 'Личное',
    items: [
      {
        id: 'personal',
        label: 'Мой профиль',
        icon: User,
        description: 'Тема, пароль, Telegram',
      },
    ],
  },
  {
    label: 'Кто может войти',
    adminOnly: true,
    items: [
      {
        id: 'users',
        label: 'Пользователи',
        icon: Users,
        description: 'Учётные записи панели',
        settingsTab: 'users',
        adminOnly: true,
      },
    ],
  },
]

describe('filterNavGroupsByQuery', () => {
  it('returns groups unchanged for empty query', () => {
    expect(filterNavGroupsByQuery(SAMPLE, '')).toEqual(SAMPLE)
    expect(filterNavGroupsByQuery(SAMPLE, '   ')).toEqual(SAMPLE)
  })

  it('matches label case-insensitively', () => {
    const result = filterNavGroupsByQuery(SAMPLE, 'профиль')
    expect(result).toHaveLength(1)
    expect(result[0].items.map((i) => i.id)).toEqual(['personal'])
  })

  it('matches description', () => {
    const result = filterNavGroupsByQuery(SAMPLE, 'учётные')
    expect(result).toHaveLength(1)
    expect(result[0].items[0].id).toBe('users')
  })

  it('drops empty groups', () => {
    expect(filterNavGroupsByQuery(SAMPLE, 'нет-такого-раздела')).toEqual([])
  })
})
