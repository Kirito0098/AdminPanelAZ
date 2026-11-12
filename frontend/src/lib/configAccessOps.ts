import { createPortalLink, revokePortalLink, rotatePortalLink } from '@/api/portal'
import {
  awg2PermanentBlock,
  awg2TempBlock,
  awg2Unblock,
  openvpnPermanentBlock,
  openvpnTempBlock,
  openvpnUnblock,
  wgPermanentBlock,
  wgTempBlock,
  wgUnblock,
} from '@/api/vpnAccess'
import type { VpnConfig, VpnType } from '@/types'

export type ConfigAccessTarget = Pick<VpnConfig, 'client_name' | 'vpn_type'>

interface BlockOps {
  tempBlock: (clientName: string, days: number) => Promise<unknown>
  permanentBlock: (clientName: string) => Promise<unknown>
  unblock: (clientName: string) => Promise<unknown>
}

const BLOCK_OPS: Record<VpnType, BlockOps> = {
  openvpn: {
    tempBlock: openvpnTempBlock,
    permanentBlock: openvpnPermanentBlock,
    unblock: openvpnUnblock,
  },
  wireguard: {
    tempBlock: wgTempBlock,
    permanentBlock: wgPermanentBlock,
    unblock: wgUnblock,
  },
  amneziawg2: {
    tempBlock: awg2TempBlock,
    permanentBlock: awg2PermanentBlock,
    unblock: awg2Unblock,
  },
}

export async function tempBlockConfig(config: ConfigAccessTarget, days: number): Promise<void> {
  await BLOCK_OPS[config.vpn_type].tempBlock(config.client_name, days)
}

export async function permanentBlockConfig(config: ConfigAccessTarget): Promise<void> {
  await BLOCK_OPS[config.vpn_type].permanentBlock(config.client_name)
}

export async function unblockConfig(config: ConfigAccessTarget): Promise<void> {
  await BLOCK_OPS[config.vpn_type].unblock(config.client_name)
}

/** Создаёт ссылку портала и сразу кладёт её в буфер — общий шаг карточки и диалога. */
export async function copyConfigPortalLink(clientName: string): Promise<string> {
  const link = await createPortalLink(clientName)
  await navigator.clipboard.writeText(link.url)
  return link.url
}

/** Перевыпускает ссылку портала и сразу кладёт её в буфер. */
export async function rotateConfigPortalLink(clientName: string): Promise<string> {
  const link = await rotatePortalLink(clientName)
  await navigator.clipboard.writeText(link.url)
  return link.url
}

export async function revokeConfigPortalLink(clientName: string): Promise<void> {
  await revokePortalLink(clientName)
}
