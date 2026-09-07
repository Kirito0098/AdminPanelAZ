import { apiFetch } from './http'

export async function getClientPolicies(clients: string) {
  const params = new URLSearchParams({ clients })
  return apiFetch<Record<string, import('../types').ClientPoliciesResponseEntry>>(
    `/client-access/policies?${params}`,
  )
}

export async function openvpnTempBlock(clientName: string, days: number) {
  return apiFetch('/client-access/openvpn/temp-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days }),
  })
}

export async function openvpnUnblock(clientName: string) {
  return apiFetch('/client-access/openvpn/unblock', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function openvpnPermanentBlock(clientName: string) {
  return apiFetch('/client-access/openvpn/permanent-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgSetExpiry(clientName: string, days: number, extend = false) {
  return apiFetch('/client-access/wireguard/set-expiry', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days, extend }),
  })
}

export async function wgTempBlock(clientName: string, days: number) {
  return apiFetch('/client-access/wireguard/temp-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days }),
  })
}

export async function wgUnblock(clientName: string) {
  return apiFetch('/client-access/wireguard/unblock', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgPermanentBlock(clientName: string) {
  return apiFetch('/client-access/wireguard/permanent-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function awg2TempBlock(clientName: string, days: number) {
  return apiFetch('/client-access/amneziawg2/temp-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName, days }),
  })
}

export async function awg2Unblock(clientName: string) {
  return apiFetch('/client-access/amneziawg2/unblock', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function awg2PermanentBlock(clientName: string) {
  return apiFetch('/client-access/amneziawg2/permanent-block', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function openvpnSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return apiFetch('/client-access/openvpn/set-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({
      client_name: clientName,
      limit_value: limitValue,
      limit_unit: limitUnit,
      limit_period_days: limitPeriodDays ?? null,
    }),
  })
}

export async function openvpnClearTrafficLimit(clientName: string) {
  return apiFetch('/client-access/openvpn/clear-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function wgSetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return apiFetch('/client-access/wireguard/set-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({
      client_name: clientName,
      limit_value: limitValue,
      limit_unit: limitUnit,
      limit_period_days: limitPeriodDays ?? null,
    }),
  })
}

export async function wgClearTrafficLimit(clientName: string) {
  return apiFetch('/client-access/wireguard/clear-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function awg2SetTrafficLimit(
  clientName: string,
  limitValue: number,
  limitUnit = 'MB',
  limitPeriodDays?: number | null,
) {
  return apiFetch('/client-access/amneziawg2/set-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({
      client_name: clientName,
      limit_value: limitValue,
      limit_unit: limitUnit,
      limit_period_days: limitPeriodDays ?? null,
    }),
  })
}

export async function awg2ClearTrafficLimit(clientName: string) {
  return apiFetch('/client-access/amneziawg2/clear-traffic-limit', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}

export async function openvpnDisconnect(clientName: string) {
  return apiFetch('/client-access/openvpn/disconnect', {
    method: 'POST',
    body: JSON.stringify({ client_name: clientName }),
  })
}
