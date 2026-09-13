import SettingsAlert from '@/components/settings/SettingsAlert'
import type { NodeMtlsStatus } from '@/types'

/** Only actionable states — a ready CA is not shown (avoids noise on Узлы). */
export default function MtlsCaStatusAlert({ status }: { status: NodeMtlsStatus }) {
  if (!status.writable) {
    return (
      <SettingsAlert variant="warning" title="mTLS: нет прав на каталог" className="py-3">
        Нельзя писать в <code className="text-xs">{status.mtls_dir}</code>. Выдайте доступ к{' '}
        <code className="text-xs">/etc/adminpanelaz</code> перед включением mTLS.
      </SettingsAlert>
    )
  }
  if (status.ready) {
    return null
  }
  return (
    <SettingsAlert variant="info" title="mTLS: CA ещё не создан" className="py-3">
      Создастся при первом «Включить mTLS» на узле. Каталог:{' '}
      <code className="text-xs">{status.mtls_dir}</code>
    </SettingsAlert>
  )
}
