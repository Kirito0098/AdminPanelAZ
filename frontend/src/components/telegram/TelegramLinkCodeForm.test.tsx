// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TelegramLinkCodeForm from './TelegramLinkCodeForm'

describe('TelegramLinkCodeForm', () => {
  afterEach(() => {
    cleanup()
  })

  it('asks for the current password before requesting a code', async () => {
    const onRequest = vi.fn(async () => true)
    render(<TelegramLinkCodeForm idPrefix="t" onRequest={onRequest} />)
    const button = screen.getByRole('button', { name: 'Получить код для привязки' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)

    const input = screen.getByLabelText('Текущий пароль') as HTMLInputElement
    expect(input.type).toBe('password')
    fireEvent.change(input, { target: { value: 'secret-1' } })
    fireEvent.click(button)

    await waitFor(() => expect(onRequest).toHaveBeenCalledWith('secret-1'))
    await waitFor(() => expect(input.value).toBe(''))
  })

  it('keeps the password when the request fails', async () => {
    const onRequest = vi.fn(async () => false)
    render(<TelegramLinkCodeForm idPrefix="t" onRequest={onRequest} />)
    const input = screen.getByLabelText('Текущий пароль') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Получить код для привязки' }))

    await waitFor(() => expect(onRequest).toHaveBeenCalled())
    expect(input.value).toBe('wrong')
  })
})
