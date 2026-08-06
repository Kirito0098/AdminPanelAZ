import CidrScheduleCard from '@/components/routing/CidrScheduleCard'

export default function RoutingSettingsTab() {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold tracking-tight">Расписание</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Когда и как часто панель сама обновляет базу CIDR-провайдеров
        </p>
      </div>
      <CidrScheduleCard />
    </div>
  )
}
