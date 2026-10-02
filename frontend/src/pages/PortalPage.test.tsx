// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PortalClientEntry, PortalMetaResponse } from '@/api/portal'
import PortalPage from './PortalPage'

const portalApi = vi.hoisted(() => ({
  fetchPublicPortalMeta: vi.fn(),
  redeemPublicPortalCode: vi.fn(),
}))

vi.mock('@/api/portal', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/portal')>()),
  ...portalApi,
}))

function client(nodeId: number, name: string): PortalClientEntry {
  return {
    node_id: nodeId,
    client_name: name,
    protocols: ['wireguard'],
    files: [
      {
        path: `/p/${name}.conf`,
        label: `${name} WireGuard`,
        filename: `${name}.conf`,
        vpn_type: 'wireguard',
        download_url: `https://portal.example.com/${name}`,
      },
    ],
  }
}

function userMeta(nodes: { node_id: number; label: string; clients: PortalClientEntry[] }[]): PortalMetaResponse {
  return { kind: 'user', brand_title: 'VPN', unlock_codes_enabled: false, nodes }
}

async function renderPortal(meta: PortalMetaResponse) {
  portalApi.fetchPublicPortalMeta.mockResolvedValue(meta)
  render(
    <MemoryRouter initialEntries={['/p/u_tok']}>
      <Routes>
        <Route path="/p/:token" element={<PortalPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Подключение')
}

describe('PortalPage node picker', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('hides both switchers for one node with one profile', async () => {
    await renderPortal(userMeta([{ node_id: 1, label: 'NL', clients: [client(1, 'alice')] }]))
    expect(screen.queryByText('Сервер')).toBeNull()
    expect(screen.queryByText('Профили пользователя')).toBeNull()
    expect(screen.getByText('alice')).toBeTruthy()
  })

  it('shows the server switcher for two nodes and switches profile files', async () => {
    await renderPortal(
      userMeta([
        { node_id: 2, label: 'Германия', clients: [client(2, 'bob')] },
        { node_id: 1, label: 'Финляндия', clients: [client(1, 'alice')] },
      ]),
    )
    expect(screen.getByText('Сервер')).toBeTruthy()
    expect(screen.queryByText('Профили пользователя')).toBeNull()
    expect(screen.getByText('Германия · bob')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Финляндия' }))

    expect(screen.getByText('Финляндия · alice')).toBeTruthy()
    expect(screen.getByText('alice.conf')).toBeTruthy()
    expect(screen.queryByText('bob.conf')).toBeNull()
  })

  it('shows only the profile switcher for one node with two profiles', async () => {
    await renderPortal(userMeta([{ node_id: 1, label: 'NL', clients: [client(1, 'alice'), client(1, 'bob')] }]))
    expect(screen.queryByText('Сервер')).toBeNull()
    expect(screen.getByText('Профили пользователя')).toBeTruthy()
    expect(screen.getByText(/Доступно профилей: 2/)).toBeTruthy()
  })

  it('hides both switchers for a client link', async () => {
    await renderPortal({
      kind: 'client',
      brand_title: 'VPN',
      unlock_codes_enabled: false,
      ...client(3, 'dave'),
    })
    expect(screen.queryByText('Сервер')).toBeNull()
    expect(screen.queryByText('Профили пользователя')).toBeNull()
  })

  it('shows the empty state when there are no nodes', async () => {
    await renderPortal(userMeta([]))
    expect(screen.getByText('Нет профилей')).toBeTruthy()
  })
})
