import PanelRebuildCard from '@/components/settings/PanelRebuildCard'
import PanelRestartCard from '@/components/settings/PanelRestartCard'

export default function PanelOpsTab() {
  return (
    <div className="space-y-4">
      <PanelRebuildCard />
      <PanelRestartCard />
    </div>
  )
}
