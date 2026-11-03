import TelegramSettingsPanel from '@/components/telegram/TelegramSettingsPanel'
import { useTelegramSettings } from '@/components/telegram/useTelegramSettings'
import BellNotifyMatrix from '@/components/settings/BellNotifyMatrix'

export default function NotificationsSection() {
  const tg = useTelegramSettings()

  return (
    <div className="space-y-4">
      <TelegramSettingsPanel tg={tg} activeTab="notify" />
      <BellNotifyMatrix />
    </div>
  )
}
