// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import AdminGate from '@/tg-mini/AdminGate'

const auth = vi.hoisted(() => ({ isAdmin: false }))

vi.mock('@/tg-mini/context/TgAuthContext', () => ({ useTgAuth: () => auth }))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/configs" element={<p>configs-page</p>} />
        <Route
          path="/clients"
          element={
            <AdminGate>
              <p>clients-page</p>
            </AdminGate>
          }
        />
        <Route
          path="/requests"
          element={
            <AdminGate>
              <p>requests-page</p>
            </AdminGate>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('AdminGate', () => {
  it('redirects a non-admin to configs without mounting the admin page', () => {
    auth.isAdmin = false

    renderAt('/clients')

    expect(screen.queryByText('clients-page')).toBeNull()
    expect(screen.getByText('configs-page')).toBeTruthy()
  })

  it('renders the admin page for an admin', () => {
    auth.isAdmin = true

    renderAt('/requests')

    expect(screen.getByText('requests-page')).toBeTruthy()
  })
})
