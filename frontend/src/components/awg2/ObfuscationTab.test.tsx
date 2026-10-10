// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within, type RenderResult } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { nodeState, notify, resetNodeState, testNode } from '@/test/nodePageHarness'
import type { Awg2HealthResponse, Awg2ObfuscationResponse, Node } from '@/types'
import ObfuscationTab from './ObfuscationTab'

const api = vi.hoisted(() => ({
  getAwg2Obfuscation: vi.fn(),
  regenerateAwg2Obfuscation: vi.fn(),
  applyAwg2Obfuscation: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NodeContext', async () => (await import('@/test/nodePageHarness')).nodeContextModule)
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)

const health = { installed: true } as Awg2HealthResponse
const secondNode = { ...testNode, id: 2, name: 'second' } as Node
const firstNodeProfile: Awg2ObfuscationResponse = {
  preset: 'high',
  template: 'tls',
  fp: 'firefox',
  mtu: 1300,
  host: 'one.example',
}

const hostInput = () => screen.getByLabelText('Host (опционально)') as HTMLInputElement
const mtuInput = () => screen.getByLabelText('MTU (опционально)') as HTMLInputElement

async function mount(): Promise<RenderResult> {
  const result = render(<ObfuscationTab health={health} />)
  await act(async () => {})
  return result
}

async function switchNode(result: RenderResult, node: Node) {
  nodeState.activeNode = node
  result.rerender(<ObfuscationTab health={health} />)
  await act(async () => {})
}

describe('ObfuscationTab', () => {
  beforeEach(() => {
    resetNodeState()
    nodeState.activeNode = testNode
    api.getAwg2Obfuscation.mockResolvedValue(firstNodeProfile)
    api.regenerateAwg2Obfuscation.mockResolvedValue({ preset: 'low', reimport_required: true })
    api.applyAwg2Obfuscation.mockResolvedValue({ ...firstNodeProfile, reimport_required: true })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('asks before regenerate and does nothing on cancel', async () => {
    await mount()

    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/переимпортируют конфиги/)).toBeTruthy()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }))
    })

    expect(api.regenerateAwg2Obfuscation).not.toHaveBeenCalled()
  })

  it('regenerates after confirmation', async () => {
    await mount()

    fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }))
    const dialog = await screen.findByRole('dialog')
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Перегенерировать' }))
    })

    expect(api.regenerateAwg2Obfuscation).toHaveBeenCalledTimes(1)
    expect(notify.success).toHaveBeenCalledWith('Профиль обфускации перегенерирован')
  })

  it('applies the form only after confirmation', async () => {
    await mount()

    fireEvent.click(screen.getByRole('button', { name: 'Применить' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Применить preset high?')).toBeTruthy()
    expect(api.applyAwg2Obfuscation).not.toHaveBeenCalled()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Применить' }))
    })

    expect(api.applyAwg2Obfuscation).toHaveBeenCalledWith({
      preset: 'high',
      template: 'tls',
      mtu: 1300,
      host: 'one.example',
      fp: 'firefox',
    })
  })

  it('resets the form when the node changes', async () => {
    api.getAwg2Obfuscation.mockResolvedValueOnce(firstNodeProfile).mockResolvedValueOnce({ preset: 'low' })
    const result = await mount()
    expect(hostInput().value).toBe('one.example')

    await switchNode(result, secondNode)

    expect(hostInput().value).toBe('')
    expect(mtuInput().value).toBe('')
  })

  it('ignores a late answer for the previous node', async () => {
    let resolveFirst: (value: Awg2ObfuscationResponse) => void = () => {}
    api.getAwg2Obfuscation
      .mockReturnValueOnce(
        new Promise<Awg2ObfuscationResponse>((resolve) => {
          resolveFirst = resolve
        }),
      )
      .mockResolvedValueOnce({})
    const result = await mount()

    await switchNode(result, secondNode)
    await act(async () => {
      resolveFirst(firstNodeProfile)
    })

    expect(hostInput().value).toBe('')
    expect(mtuInput().value).toBe('')
  })
})
