import MonitorSettingsCard from '@/components/settings/MonitorSettingsCard'
import AlertRulesCard from '@/components/settings/AlertRulesCard'

export default function MonitoringTab() {
  return (
    <div className="space-y-4">
      <MonitorSettingsCard />
      <AlertRulesCard />
    </div>
  )
}
