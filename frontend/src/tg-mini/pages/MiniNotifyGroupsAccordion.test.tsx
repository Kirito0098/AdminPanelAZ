// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AdminNotifyEventItem, AdminNotifyGroupInfo } from '@/types'
import { MiniNotifyGroupsAccordion } from './Settings'

afterEach(() => {
  cleanup()
})

const EVENTS: AdminNotifyEventItem[] = [
  { key: 'user_cert_expiry_reminder', label: 'Напоминание о сертификате', enabled: true, group: 'owner_reminders' },
  { key: 'user_access_expiry_reminder', label: 'Напоминание о доступе', enabled: false, group: 'owner_reminders' },
  { key: 'login_success', label: 'Успешный вход', enabled: true, group: 'login' },
]

const OWNER_GROUP: AdminNotifyGroupInfo = {
  group: 'owner_reminders',
  title: 'Мои напоминания',
  icon: '🔔',
  keys: ['user_cert_expiry_reminder', 'user_access_expiry_reminder'],
}

const LOGIN_GROUP: AdminNotifyGroupInfo = {
  group: 'login',
  title: 'Входы',
  icon: '🔑',
  keys: ['login_success'],
}

function renderAccordion(groups: AdminNotifyGroupInfo[], events = EVENTS) {
  return render(
    <MiniNotifyGroupsAccordion
      groups={groups}
      events={events}
      eventToggles={Object.fromEntries(events.map((e) => [e.key, e.enabled]))}
      onToggleEvent={vi.fn()}
      onToggleGroup={vi.fn()}
    />,
  )
}

describe('MiniNotifyGroupsAccordion', () => {
  it('single group → group switch absent but event rows visible', () => {
    renderAccordion([OWNER_GROUP])
    expect(screen.queryByRole('switch', { name: /все события группы/ })).toBeNull()
    expect(screen.getByRole('switch', { name: 'Напоминание о сертификате' })).toBeDefined()
    expect(screen.getByRole('switch', { name: 'Напоминание о доступе' })).toBeDefined()
  })

  it('2+ groups → group switches present', () => {
    renderAccordion([OWNER_GROUP, LOGIN_GROUP])
    expect(screen.getByRole('switch', { name: 'Мои напоминания: все события группы' })).toBeDefined()
    expect(screen.getByRole('switch', { name: 'Входы: все события группы' })).toBeDefined()
    expect(screen.getByText('вкл 1/2')).toBeDefined()
  })

  it('legacy groups=[] → flat list without group switch', () => {
    renderAccordion([])
    expect(screen.queryByRole('switch', { name: /все события группы/ })).toBeNull()
    expect(screen.getByRole('switch', { name: 'Напоминание о сертификате' })).toBeDefined()
    expect(screen.getByRole('switch', { name: 'Успешный вход' })).toBeDefined()
  })
})
