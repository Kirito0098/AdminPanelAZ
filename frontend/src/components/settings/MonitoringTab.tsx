import { Link } from 'react-router-dom'
import { MessageCircle } from 'lucide-react'
import MonitorSettingsCard from '@/components/settings/MonitorSettingsCard'
import AlertRulesCard from '@/components/settings/AlertRulesCard'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import { Button } from '@/components/ui/button'
import { useFeatureModules } from '@/context/FeatureModulesContext'

export default function MonitoringTab() {
  const { isEnabled } = useFeatureModules()

  return (
    <div className="space-y-4">
      <SettingsToolbar
        title="Мониторинг и оповещения"
        meta="CPU, RAM и свои правила — сообщения о превышении порогов приходят в Telegram"
        actions={
          <Button variant="outline" size="sm" className="gap-1.5" asChild>
            <Link to="/telegram">
              <MessageCircle size={14} />
              Настроить Telegram
            </Link>
          </Button>
        }
      />

      <MonitorSettingsCard />
      {isEnabled('alert_rules') && <AlertRulesCard />}
    </div>
  )
}
