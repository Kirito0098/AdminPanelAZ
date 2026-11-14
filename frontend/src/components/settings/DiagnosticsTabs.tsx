import { Activity, Server } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import RunbookTab from '@/components/settings/RunbookTab'
import ServerConfigTab from '@/components/settings/ServerConfigTab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFeatureModules } from '@/context/FeatureModulesContext'

const TRIGGER_CLASS =
  'gap-1.5 data-[state=active]:bg-primary/5 data-[state=active]:text-foreground data-[state=active]:ring-1 data-[state=active]:ring-primary/20'

export default function DiagnosticsTabs() {
  const { isEnabled } = useFeatureModules()
  const [searchParams, setSearchParams] = useSearchParams()

  if (!isEnabled('system_updates')) return <RunbookTab />

  const tab = searchParams.get('tab') === 'server' ? 'server' : 'run'
  const setTab = (value: string) =>
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev)
        if (value === 'server') params.set('tab', 'server')
        else params.delete('tab')
        return params
      },
      { replace: true },
    )

  return (
    <Tabs value={tab} onValueChange={setTab} className="space-y-4">
      <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1 rounded-lg bg-muted/50 p-1 sm:inline-flex sm:w-auto">
        <TabsTrigger value="run" className={TRIGGER_CLASS}>
          <Activity size={16} aria-hidden />
          Диагностика запуска
        </TabsTrigger>
        <TabsTrigger value="server" className={TRIGGER_CLASS}>
          <Server size={16} aria-hidden />
          Настройки сервера
        </TabsTrigger>
      </TabsList>
      <TabsContent value="run" className="mt-0 focus-visible:outline-none">
        <RunbookTab />
      </TabsContent>
      <TabsContent value="server" className="mt-0 focus-visible:outline-none">
        <ServerConfigTab />
      </TabsContent>
    </Tabs>
  )
}
