import SettingsAlert from '@/components/settings/SettingsAlert'
import { useNode } from '@/context/NodeContext'

export default function HaReplicaBanner() {
  const { activeNodeHa } = useNode()
  if (activeNodeHa?.role !== 'replica') return null

  const primaryLabel = activeNodeHa.primary_node_name
    ? ` («${activeNodeHa.primary_node_name}»)`
    : ''

  return (
    <SettingsAlert variant="warning" title="HA: узел replica — только просмотр">
      Активный узел — <strong>replica</strong> в группе «{activeNodeHa.group_name}» ({activeNodeHa.shared_domain}
      ). Создание и изменение клиентов, файлов конфигурации, маршрутизации и списков AntiZapret доступно только на
      primary{primaryLabel}. Переключите активный узел в шапке или на странице «Узлы».
    </SettingsAlert>
  )
}
