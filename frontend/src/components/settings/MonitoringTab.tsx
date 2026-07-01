import MonitorSettingsCard from '@/components/settings/MonitorSettingsCard'
import AlertRulesCard from '@/components/settings/AlertRulesCard'
import SettingsAlert from '@/components/settings/SettingsAlert'

export default function MonitoringTab() {
  return (
    <div className="space-y-4">
      <SettingsAlert variant="info" title="Куда приходят уведомления">
        Сообщения о нагрузке и срабатывании правил отправляются в Telegram — настройте бота в разделе «Telegram».
      </SettingsAlert>
      <MonitorSettingsCard />
      <AlertRulesCard />
    </div>
  )
}
