import { Link } from 'react-router-dom'
import { MessageCircle } from 'lucide-react'
import MonitorSettingsCard from '@/components/settings/MonitorSettingsCard'
import AlertRulesCard from '@/components/settings/AlertRulesCard'
import { SettingsToolbar } from '@/components/settings/SettingsChrome'
import { Button } from '@/components/ui/button'

export default function MonitoringTab() {
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
      <AlertRulesCard />
    </div>
  )
}
