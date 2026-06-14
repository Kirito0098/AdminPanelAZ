import { useMemo } from 'react'
import { Bell, Bot, LogIn, Send, Smartphone } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import TelegramAlerts from '@/components/telegram/TelegramAlerts'
import TelegramDisableSection from '@/components/telegram/TelegramDisableSection'
import TelegramHero from '@/components/telegram/TelegramHero'
import TelegramOverviewCards from '@/components/telegram/TelegramOverviewCards'
import TelegramSettingsPanel from '@/components/telegram/TelegramSettingsPanel'
import { useTelegramSettings, type TelegramSection } from '@/components/telegram/useTelegramSettings'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const TELEGRAM_TABS: Array<{ id: TelegramSection; label: string; icon: typeof Send }> = [
  { id: 'setup', label: 'Подключение', icon: LogIn },
  { id: 'bot', label: 'Бот', icon: Send },
  { id: 'miniapp', label: 'Mini App', icon: Smartphone },
  { id: 'interactive', label: 'Интерактив', icon: Bot },
  { id: 'notify', label: 'Уведомления', icon: Bell },
]

const VALID_TABS = new Set(TELEGRAM_TABS.map((t) => t.id))

export default function TelegramPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tg = useTelegramSettings()

  const tab = useMemo(() => {
    const value = searchParams.get('tab') as TelegramSection | null
    return value && VALID_TABS.has(value) ? value : 'setup'
  }, [searchParams])

  const navigateTab = (next: TelegramSection) => {
    setSearchParams({ tab: next }, { replace: true })
  }

  return (
    <div className="space-y-5">
      <TelegramHero tg={tg} />

      <TelegramDisableSection />

      <TelegramOverviewCards tg={tg} loading={tg.loading} onNavigate={navigateTab} />

      <TelegramAlerts tg={tg} />

      <Tabs value={tab} onValueChange={(value) => navigateTab(value as TelegramSection)} className="space-y-4">
        <TabsList className="flex h-auto flex-wrap gap-1 bg-muted/50 p-1">
          {TELEGRAM_TABS.map((item) => (
            <TabsTrigger key={item.id} value={item.id} className="gap-1.5">
              <item.icon size={14} />
              <span className="hidden sm:inline">{item.label}</span>
              <span className="sm:hidden">{item.label.split(' ')[0]}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        {TELEGRAM_TABS.map((item) => (
          <TabsContent key={item.id} value={item.id}>
            <TelegramSettingsPanel tg={tg} activeTab={item.id} onNavigate={navigateTab} />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
