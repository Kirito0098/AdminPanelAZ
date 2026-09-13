import SettingsAlert from '@/components/settings/SettingsAlert'
import DocsLink from '@/components/shared/DocsLink'
import { DOCS } from '@/lib/docsUrls'
import type { Node } from '@/types'
import { isProxyNode } from './nodeKind'
import { isWrongVersionSslError } from './nodeHelpers'

export default function NodeConnectionErrorAlert({
  node,
  lastError,
}: {
  node: Node
  lastError: string
}) {
  const isProxy = isProxyNode(node)
  if (isWrongVersionSslError(lastError)) {
    return (
      <SettingsAlert variant="warning" title="Несовпадение протокола (SSL)">
        {node.mtls_enabled ? (
          <>
            Панель подключается по HTTPS, а узел отвечает по HTTP. Временно отключите глобальный{' '}
            <code className="text-xs">NODE_AGENT_MTLS_ENABLED</code> в <code className="text-xs">.env</code>{' '}
            или сбросьте флаг mTLS для узла вручную.
          </>
        ) : isProxy ? (
          <>
            Узел отвечает по HTTPS (mTLS), а панель — по HTTP. Нажмите{' '}
            <strong>«Отметить mTLS»</strong> в меню узла после ручной настройки сертификатов
            proxy_agent. <DocsLink href={DOCS.proxyAgent} label="Инструкция proxy_agent" />
          </>
        ) : (
          <>
            Узел отвечает по HTTPS (mTLS), а панель — по HTTP. Нажмите{' '}
            <strong>«Включить mTLS»</strong> в меню узла или отключите mTLS на node agent.
          </>
        )}
      </SettingsAlert>
    )
  }
  return (
    <SettingsAlert variant="danger" title="Ошибка связи">
      {lastError}
    </SettingsAlert>
  )
}
