/// <reference types="vite/client" />

interface TelegramAuthUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
  auth_date: number
  hash: string
}

interface TelegramWebApp {
  ready: () => void
  expand: () => void
  close: () => void
  openLink: (url: string) => void
  shareUrl?: (url: string, text?: string) => void
  MainButton?: {
    isVisible?: boolean
  }
  onEvent: (eventType: string, callback: () => void) => void
  HapticFeedback?: {
    notificationOccurred: (type: 'error' | 'success' | 'warning') => void
    selectionChanged?: () => void
  }
  initData: string
  initDataUnsafe: Record<string, unknown>
  themeParams: Record<string, string | undefined>
  colorScheme: 'light' | 'dark'
  platform?: string
}

interface Window {
  onTelegramAuth?: (user: TelegramAuthUser) => void
  Telegram?: {
    WebApp: TelegramWebApp
  }
}
