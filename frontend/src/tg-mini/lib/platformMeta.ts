import { Laptop, Monitor, Smartphone, Terminal } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { InstallPlatform } from '@/types'

export const INSTALL_PLATFORMS: Array<{ value: InstallPlatform; label: string }> = [
  { value: 'ios', label: 'iOS' },
  { value: 'android', label: 'Android' },
  { value: 'windows', label: 'Windows' },
  { value: 'mac', label: 'macOS' },
  { value: 'linux', label: 'Linux' },
]

export const PLATFORM_ICONS: Record<InstallPlatform, LucideIcon> = {
  ios: Smartphone,
  android: Smartphone,
  windows: Monitor,
  mac: Laptop,
  linux: Terminal,
}

export function guessInstallPlatform(): InstallPlatform {
  const tg = window.Telegram?.WebApp?.platform?.toLowerCase()
  if (tg === 'ios') return 'ios'
  if (tg === 'android') return 'android'
  if (tg === 'macos') return 'mac'
  if (tg === 'tdesktop' || tg === 'web' || tg === 'weba') return 'windows'
  if (tg === 'linux') return 'linux'
  return 'android'
}
