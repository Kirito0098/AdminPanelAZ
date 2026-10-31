// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import NotificationCard from './NotificationCard'
import type { NotificationItem } from '@/api/notifications'

const item: NotificationItem = {
  id: 81,
  category: 'nodes',
  level: 'info',
  event_type: 'node_offline',
  title: 'Узел недоступен',
  message: 'Узел: nl-2',
  created_at: new Date().toISOString(),
  action_payload: null,
  details: [
    { label: 'Кто', value: 'Claymore' },
    { label: 'Объект', value: 'ivan' },
    { label: 'Узел', value: 'Test_serv' },
  ],
  state: { read: false, hidden: false, snoozed_until: null },
}

function pointerSequence(element: HTMLElement) {
  fireEvent.pointerDown(element, { button: 0, ctrlKey: false, pointerType: 'mouse' })
  fireEvent.pointerUp(element, { button: 0, pointerType: 'mouse' })
  fireEvent.click(element)
}

afterEach(cleanup)

describe('NotificationCard', () => {
  it('opens the actions menu on the page', async () => {
    const onMarkRead = vi.fn()
    render(
      <MemoryRouter>
        <NotificationCard item={item} onMarkRead={onMarkRead} />
      </MemoryRouter>,
    )

    pointerSequence(screen.getByLabelText('Действия с уведомлением'))

    fireEvent.click(await screen.findByText('Отметить прочитанным'))
    expect(onMarkRead).toHaveBeenCalledWith(81)
  })

  it('has no nested menu inside the bell popover: an inline «mark read» button instead', async () => {
    const onMarkRead = vi.fn()
    render(
      <MemoryRouter>
        <DropdownMenu open>
          <DropdownMenuTrigger asChild>
            <button type="button">bell</button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <NotificationCard item={item} compact onMarkRead={onMarkRead} />
          </DropdownMenuContent>
        </DropdownMenu>
      </MemoryRouter>,
    )

    // Вложенное меню Radix внутри меню закрывается вместе с внешним — в колоколе его быть не должно.
    expect(screen.queryByLabelText('Действия с уведомлением')).toBeNull()

    fireEvent.click(screen.getByLabelText('Отметить прочитанным'))
    expect(onMarkRead).toHaveBeenCalledWith(81)
  })

  it('hides the inline button for already read items', () => {
    render(
      <MemoryRouter>
        <NotificationCard
          item={{ ...item, state: { read: true, hidden: false, snoozed_until: null } }}
          compact
          onMarkRead={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.queryByLabelText('Отметить прочитанным')).toBeNull()
  })
})


