import { apiFetch } from './http'
import type { OpenVpnTuningState } from '@/types'

export async function getOpenVpnTuning(): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning')
}

export async function applyOpenVpnTuning(duplicate: boolean, logs: boolean): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning', {
    method: 'PUT',
    body: JSON.stringify({ duplicate, logs }),
  })
}

export async function applyOpenVpnMtu(values: {
  openvpn?: number | null
  wireguard?: number | null
}): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning/mtu', {
    method: 'PUT',
    body: JSON.stringify({ openvpn: values.openvpn ?? null, wireguard: values.wireguard ?? null }),
  })
}

export async function applyOpenVpnDco(enabled: boolean): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning/dco', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}

export async function applyOpenVpnProtocols(units: Record<string, boolean>): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning/protocols', {
    method: 'PUT',
    body: JSON.stringify({ units }),
  })
}

export async function applyOpenVpnPatch(algorithm: number): Promise<OpenVpnTuningState> {
  return apiFetch<OpenVpnTuningState>('/openvpn-tuning/patch', {
    method: 'POST',
    body: JSON.stringify({ algorithm }),
  })
}
