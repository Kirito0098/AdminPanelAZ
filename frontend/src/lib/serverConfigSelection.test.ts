import { describe, expect, it } from 'vitest'

import {
  defaultStepSelection,
  hasNginxRisk,
  isSnippetIntegration,
  nginxRiskNotes,
  sanitizeStepSelection,
} from './serverConfigSelection'
import type { NginxImpact, ServerConfigPreview, ServerConfigStep } from '@/types'

const steps: ServerConfigStep[] = [
  { key: 'apt', label: 'Пакеты', available: true },
  { key: 'systemd', label: 'Службы', available: true },
  { key: 'nginx', label: 'Nginx', available: true },
  { key: 'firewall', label: 'Firewall', available: true },
  { key: 'ddns', label: 'DDNS', available: false, reason: 'DDNS не настроен' },
]

function impact(patch: Partial<NginxImpact> = {}): NginxImpact {
  return {
    nginx_seen: true,
    panel_domain: 'panel.example.test',
    vhosts: [],
    foreign_locations: [],
    global_changes: [],
    warnings: [],
    status_openvpn: null,
    ...patch,
  }
}

function preview(nginxImpact: NginxImpact): ServerConfigPreview {
  return {
    sections: { add: [], change: [], recheck: [], keep: [], remove: [], effect: [] },
    details: {},
    pending: 1,
    steps,
    nginx_impact: nginxImpact,
  }
}

describe('defaultStepSelection', () => {
  it('selects every available step on a clean dedicated setup', () => {
    expect(defaultStepSelection(preview(impact()))).toEqual(['apt', 'systemd', 'nginx', 'firewall'])
  })

  it('skips nginx when the panel vhost holds foreign locations', () => {
    const selection = defaultStepSelection(
      preview(
        impact({
          foreign_locations: [{ path: '/status/', project: 'status-openvpn' }],
        }),
      ),
    )
    expect(selection).not.toContain('nginx')
    expect(selection).toEqual(['apt', 'systemd', 'firewall'])
  })

  it('skips nginx when the panel is included through a snippet', () => {
    const selection = defaultStepSelection(
      preview(
        impact({
          integration_mode: 'subpath_snippet',
          panel_vhost: 'vpn.example.test',
          panel_snippet_includes: ['/etc/nginx/snippets/adminpanelaz-https.conf'],
        }),
      ),
    )
    expect(selection).not.toContain('nginx')
  })

  it('detects snippet integrations even when the mode field is missing', () => {
    expect(
      isSnippetIntegration(
        impact({ panel_snippet_includes: ['/etc/nginx/snippets/adminpanelaz.conf'] }),
      ),
    ).toBe(true)
    expect(isSnippetIntegration(impact({ integration_mode: 'dedicated_vhost' }))).toBe(false)
  })
})

describe('sanitizeStepSelection', () => {
  it('drops unavailable and unknown steps', () => {
    expect(sanitizeStepSelection(['apt', 'ddns', 'gone'], steps)).toEqual(['apt'])
  })
})

describe('nginxRiskNotes', () => {
  it('explains snippet and foreign-location risk with values from the payload', () => {
    const notes = nginxRiskNotes(
      impact({
        integration_mode: 'subpath_snippet',
        panel_vhost: 'vpn.example.test',
        foreign_locations: [{ path: '/status/', project: 'status-openvpn' }],
      }),
    )
    expect(notes).toHaveLength(2)
    expect(notes[0]).toContain('snippet')
    expect(notes[1]).toContain('/status/')
    expect(notes[1]).toContain('status-openvpn')
  })

  it('reports no risk for a dedicated clean vhost', () => {
    expect(hasNginxRisk(impact())).toBe(false)
    expect(nginxRiskNotes(impact())).toEqual([])
  })
})
