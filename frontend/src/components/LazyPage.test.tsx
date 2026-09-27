// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LazyPage from './LazyPage'

const reloadOnChunkError = vi.hoisted(() => vi.fn(() => false))

vi.mock('@/lib/lazyWithRetry', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/lazyWithRetry')>()),
  reloadOnChunkError,
}))

function Boom(): never {
  throw new Error('boom')
}

function ChunkBoom(): never {
  throw new TypeError('Failed to fetch dynamically imported module: https://panel/assets/LogsPage-1.js')
}

function Nav() {
  return (
    <nav>
      <Link to="/a">to-a</Link>
      <Link to="/b">to-b</Link>
      <Link to="/a?tab=2">to-a-query</Link>
      <Link to="/settings/general">to-general</Link>
      <Link to="/settings/security">to-security</Link>
    </nav>
  )
}

describe('LazyPage error boundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    reloadOnChunkError.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('resets when the pathname changes: the next page renders normally', () => {
    render(
      <MemoryRouter initialEntries={['/a']}>
        <Nav />
        <Routes>
          <Route path="/a" element={<LazyPage><Boom /></LazyPage>} />
          <Route path="/b" element={<LazyPage><p>Страница B</p></LazyPage>} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('Не удалось отобразить раздел')).toBeTruthy()

    fireEvent.click(screen.getByText('to-b'))

    expect(screen.getByText('Страница B')).toBeTruthy()
    expect(screen.queryByText('Не удалось отобразить раздел')).toBeNull()
  })

  it('does not remount the page when only the query string changes', () => {
    let mounts = 0
    function Page() {
      useEffect(() => {
        mounts += 1
      }, [])
      return <p>Страница A</p>
    }

    render(
      <MemoryRouter initialEntries={['/a']}>
        <Nav />
        <Routes>
          <Route path="/a" element={<LazyPage><Page /></LazyPage>} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('to-a-query'))

    expect(screen.getByText('Страница A')).toBeTruthy()
    expect(mounts).toBe(1)
  })

  it('does not remount a healthy page when a route param changes', () => {
    let mounts = 0
    function Settings() {
      useEffect(() => {
        mounts += 1
      }, [])
      return <p>Настройки</p>
    }

    render(
      <MemoryRouter initialEntries={['/settings/general']}>
        <Nav />
        <Routes>
          <Route path="/settings/:section?" element={<LazyPage><Settings /></LazyPage>} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByText('to-security'))

    expect(screen.getByText('Настройки')).toBeTruthy()
    expect(mounts).toBe(1)
  })

  it('hands chunk-load errors to the guarded reload and keeps the fallback when blocked', () => {
    render(
      <MemoryRouter initialEntries={['/a']}>
        <Routes>
          <Route path="/a" element={<LazyPage><ChunkBoom /></LazyPage>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(reloadOnChunkError).toHaveBeenCalledTimes(1)
    expect(reloadOnChunkError.mock.calls[0]).toEqual([expect.objectContaining({ name: 'TypeError' })])
    expect(screen.getByText('Не удалось отобразить раздел')).toBeTruthy()
    expect(screen.getByText('Попробовать снова')).toBeTruthy()
    expect(screen.getByText('Перезагрузить')).toBeTruthy()
  })
})
