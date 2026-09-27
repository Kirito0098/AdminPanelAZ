// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/http'
import { notify } from '@/test/nodePageHarness'
import type { SiteDiagnosticsCheck, SiteDiagnosticsReport } from '@/types'
import RunbookTab from './RunbookTab'

const api = vi.hoisted(() => ({
  runSiteDiagnostics: vi.fn(),
  closeIpAccess: vi.fn(),
}))

vi.mock('@/api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/client')>()),
  ...api,
}))
vi.mock('@/context/NotificationContext', async () => (await import('@/test/nodePageHarness')).notificationModule)

const ACTION = { id: 'close_ip_access', label: 'Закрыть доступ по IP' }

const nginxOk: SiteDiagnosticsCheck = { status: 'ok', title: 'nginx -t успешно', category: 'nginx' }

function ipCheck(overrides: Partial<SiteDiagnosticsCheck> = {}): SiteDiagnosticsCheck {
  return {
    id: 'ip_access',
    status: 'warn',
    title: 'Панель открывается по IP сервера',
    category: 'nginx',
    detail: 'Нужно закрыть порты: 80 (HTTP), 443 (HTTPS).',
    action: ACTION,
    ...overrides,
  }
}

function report(check: SiteDiagnosticsCheck): SiteDiagnosticsReport {
  const checks = [nginxOk, check]
  const warn = checks.filter((c) => c.status === 'warn').length
  const summaryCheck: SiteDiagnosticsCheck = {
    status: warn ? 'warn' : 'ok',
    title: warn ? 'Диагностика завершена с предупреждениями' : 'Диагностика: критических проблем не найдено',
    category: 'summary',
    detail: `ok=${checks.length - warn}, warn=${warn}, fail=0`,
  }
  const results = [...checks, summaryCheck]
  const warnTotal = results.filter((c) => c.status === 'warn').length
  return {
    success: true,
    install_dir: '/opt/AdminPanelAZ',
    service_name: 'adminpanelaz',
    summary: { ok: results.length - warnTotal, warn: warnTotal, fail: 0, has_failures: false },
    steps: [
      { id: 'systemd', title: 'Systemd', description: '', status: 'ok', checks: [] },
      {
        id: 'nginx',
        title: 'Nginx reverse-proxy',
        description: '',
        status: warn ? 'warn' : 'ok',
        checks,
      },
      { id: 'summary', title: 'Итог', description: '', status: summaryCheck.status, checks: [summaryCheck] },
    ],
    results,
    recommended_commands: [],
  }
}

async function runDiagnostics() {
  render(<RunbookTab />)
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Запустить диагностику' }))
  })
  if (!screen.queryByText('nginx -t успешно')) {
    await act(async () => {
      fireEvent.click(screen.getByText('Nginx reverse-proxy'))
    })
  }
}

describe('RunbookTab: «Закрыть доступ по IP»', () => {
  beforeEach(() => {
    api.runSiteDiagnostics.mockResolvedValue(report(ipCheck()))
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows the action button on a warn check with an action', async () => {
    await runDiagnostics()

    expect(screen.getByRole('button', { name: 'Закрыть доступ по IP' })).toBeTruthy()
  })

  it('hides the button when the check is ok or has no action', async () => {
    api.runSiteDiagnostics.mockResolvedValue(
      report(ipCheck({ status: 'ok', title: 'Запросы по IP сервера отклоняются', action: undefined })),
    )
    await runDiagnostics()
    expect(screen.getByText('Запросы по IP сервера отклоняются')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Закрыть доступ по IP' })).toBeNull()

    cleanup()
    api.runSiteDiagnostics.mockResolvedValue(report(ipCheck({ action: undefined })))
    await runDiagnostics()
    expect(screen.getByText('Панель открывается по IP сервера')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Закрыть доступ по IP' })).toBeNull()
  })

  it('asks for confirmation and does nothing on cancel', async () => {
    await runDiagnostics()

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть доступ по IP' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/без перезапуска/)).toBeTruthy()
    expect(within(dialog).getByText(/рукопожатие/)).toBeTruthy()

    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }))
    })
    expect(api.closeIpAccess).not.toHaveBeenCalled()
  })

  it('calls the API on confirm, notifies and replaces the check in place', async () => {
    api.closeIpAccess.mockResolvedValue({
      success: true,
      status: 'installed',
      changed: true,
      message: 'Доступ к панели по IP сервера закрыт — nginx перечитал конфигурацию',
      check: ipCheck({
        status: 'ok',
        title: 'Запросы по IP сервера отклоняются',
        detail: 'Панель открывается только по своему домену.',
        action: undefined,
      }),
    })
    await runDiagnostics()

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть доступ по IP' }))
    const dialog = await screen.findByRole('dialog')
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Закрыть доступ' }))
    })

    expect(api.closeIpAccess).toHaveBeenCalledTimes(1)
    expect(notify.success).toHaveBeenCalledWith('Доступ к панели по IP сервера закрыт — nginx перечитал конфигурацию')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('Запросы по IP сервера отклоняются')).toBeTruthy()
    expect(screen.queryByText('Панель открывается по IP сервера')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Закрыть доступ по IP' })).toBeNull()
    expect(screen.queryByText(/Серьёзных сбоев нет, но стоит обратить внимание/)).toBeNull()
    expect(screen.getByText(/Критических проблем не найдено\. Панель и окружение/)).toBeTruthy()
    expect(screen.getByText('Диагностика: критических проблем не найдено')).toBeTruthy()
    expect(api.runSiteDiagnostics).toHaveBeenCalledTimes(1)
  })

  it('shows the API error and keeps the check', async () => {
    api.closeIpAccess.mockRejectedValue(
      new ApiError('Не удалось закрыть доступ по IP: Сервер по умолчанию не прошёл nginx -t', 500),
    )
    await runDiagnostics()

    fireEvent.click(screen.getByRole('button', { name: 'Закрыть доступ по IP' }))
    const dialog = await screen.findByRole('dialog')
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Закрыть доступ' }))
    })

    expect(notify.error).toHaveBeenCalledWith('Не удалось закрыть доступ по IP: Сервер по умолчанию не прошёл nginx -t')
    expect(screen.getByText('Панель открывается по IP сервера')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Закрыть доступ по IP' })).toBeTruthy()
  })
})
