import { describe, expect, it } from 'vitest'
import { isHaSyncTaskFailed, parseHaSyncTaskResult } from '@/lib/haSyncSummary'
import type { BackgroundTask } from '@/types'

function task(output: unknown, overrides: Partial<BackgroundTask> = {}): BackgroundTask {
  return {
    id: 't1',
    task_type: 'node_sync_setup',
    status: 'completed',
    message: 'Настройка HA завершилась с ошибками',
    output: output === undefined ? null : JSON.stringify(output),
    ...overrides,
  } as BackgroundTask
}

const failedPush = {
  success: false,
  restored: [{ node_id: 3, node_name: 'replica-ok' }],
  failed: [
    {
      node_id: 2,
      node_name: 'replica-bad',
      failed_step: 'restart_openvpn',
      failed_step_label: 'перезапуск OpenVPN',
      error: 'unit failed',
    },
  ],
}

describe('parseHaSyncTaskResult', () => {
  it('lists failed replicas with their step first and reports an error', () => {
    const view = parseHaSyncTaskResult(task({ shared_domain: { success: true, updated: [] }, push_full: failedPush }))

    expect(view?.variant).toBe('error')
    expect(view?.title).toBe('Настройка HA завершилась с ошибками')
    expect(view?.sections[0].items).toEqual([
      expect.objectContaining({
        nodeName: 'replica-bad',
        text: 'Ошибка на шаге «перезапуск OpenVPN»',
        status: 'error',
        details: ['unit failed'],
      }),
    ])
  })

  it('shows a replica that failed before any other section', () => {
    const view = parseHaSyncTaskResult(
      task({
        success: false,
        failed: [{ node_id: 2, node_name: 'replica-bad', failed_step: 'restore_replica', error: 'boom' }],
        restored: [],
      }, { task_type: 'node_sync_push_full', message: 'Push full: ошибки на 1 из 1 реплик' }),
    )

    expect(view?.variant).toBe('error')
    expect(view?.title).toBe('Push full: ошибки на 1 из 1 реплик')
    expect(view?.sections).toHaveLength(1)
    expect(view?.sections[0].items[0].text).toBe('Ошибка на шаге «restore_replica»')
  })

  it('keeps the success title when every replica synced', () => {
    const view = parseHaSyncTaskResult(
      task(
        { shared_domain: { success: true, domain: 'vpn.example', updated: [] }, push_full: { success: true, restored: [{ node_id: 3 }] } },
        { message: 'HA-группа настроена и проверена' },
      ),
    )

    expect(view?.title).toBe('HA-группа настроена: vpn.example')
    expect(view?.variant).toBe('success')
  })
})

describe('isHaSyncTaskFailed', () => {
  it('detects failures inside a completed task', () => {
    expect(isHaSyncTaskFailed(task({ push_full: failedPush }))).toBe(true)
    expect(isHaSyncTaskFailed(task({ shared_domain: { success: false }, push_full: { success: true } }))).toBe(true)
    expect(isHaSyncTaskFailed(task({ success: false, failed: [] }))).toBe(true)
    expect(isHaSyncTaskFailed(task(undefined, { status: 'failed' }))).toBe(true)
  })

  it('accepts successful tasks', () => {
    expect(isHaSyncTaskFailed(task({ shared_domain: { success: true }, push_full: { success: true } }))).toBe(false)
    expect(isHaSyncTaskFailed(task({ domain: 'vpn.example', updated: [] }))).toBe(false)
    expect(isHaSyncTaskFailed(task(undefined))).toBe(false)
  })
})
