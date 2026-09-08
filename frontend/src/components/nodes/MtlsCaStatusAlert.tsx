import SettingsAlert from '@/components/settings/SettingsAlert'
import type { NodeMtlsStatus } from '@/types'

export default function MtlsCaStatusAlert({ status }: { status: NodeMtlsStatus }) {
  if (!status.writable) {
    return (
      <SettingsAlert variant="warning" title="mTLS: нет прав на каталог сертификатов">
        Панель не может записывать в <code className="text-xs">{status.mtls_dir}</code>. Запустите
        панель с правами на <code className="text-xs">/etc/adminpanelaz</code> или выдайте доступ
        до первого включения mTLS на узле.
      </SettingsAlert>
    )
  }
  if (status.ready) {
    return (
      <SettingsAlert variant="info" title="mTLS: CA готов">
        CA и клиентский сертификат панели созданы
        {status.agent_certs_count > 0 ? ` · сертификатов узлов: ${status.agent_certs_count}` : ''}.
        Каталог: <code className="text-xs">{status.mtls_dir}</code>
      </SettingsAlert>
    )
  }
  return (
    <SettingsAlert variant="info" title="mTLS: CA ещё не создан">
      При первом «Включить mTLS» на VPN-узле или «Отметить mTLS» на прокси панель создаст CA и
      сертификаты в <code className="text-xs">{status.mtls_dir}</code>. Для proxy_agent сертификаты
      агента ставятся вручную (docs/proxy-agent.md).
    </SettingsAlert>
  )
}
