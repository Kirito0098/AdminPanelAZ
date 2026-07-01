import { Link } from 'react-router-dom'
import { Activity, BellRing, MessageCircle } from 'lucide-react'
import MonitorSettingsCard from '@/components/settings/MonitorSettingsCard'
import AlertRulesCard from '@/components/settings/AlertRulesCard'
import { Button } from '@/components/ui/button'

export default function MonitoringTab() {
  return (
    <div className="grid gap-4 md:grid-cols-2 md:items-start">
      <div className="relative overflow-hidden rounded-xl border bg-gradient-to-br from-primary/5 via-card to-card p-4 md:col-span-2">
        <div className="pointer-events-none absolute -left-6 top-0 h-28 w-28 rounded-full bg-violet-500/10 blur-2xl" />
        <div className="pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-amber-500/10 blur-2xl" />
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Activity size={18} className="text-primary" />
              Мониторинг и оповещения
            </div>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Панель отслеживает нагрузку на сервер и ваши условия. Когда что-то выходит за порог — приходит
              сообщение в Telegram.
            </p>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5 rounded-full border bg-card/80 px-2.5 py-1">
                <Activity size={12} className="text-amber-500" />
                CPU и RAM
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border bg-card/80 px-2.5 py-1">
                <BellRing size={12} className="text-violet-500" />
                Свои правила
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border bg-card/80 px-2.5 py-1">
                <MessageCircle size={12} className="text-primary" />
                Доставка в Telegram
              </span>
            </div>
          </div>
          <Button variant="outline" size="sm" className="shrink-0 gap-1.5" asChild>
            <Link to="/telegram">
              <MessageCircle size={14} />
              Настроить Telegram
            </Link>
          </Button>
        </div>
      </div>

      <MonitorSettingsCard />
      <AlertRulesCard />
    </div>
  )
}
