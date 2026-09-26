import { useState } from 'react'
import { ApiError } from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/context/AuthContext'
import { useNode } from '@/context/NodeContext'
import { useNotifications } from '@/context/NotificationContext'
import { canReturnToShownNode } from '@/lib/expectedNode'

export default function ActiveNodeChangedBanner() {
  const { user } = useAuth()
  const { activeNode, activeNodeChangedElsewhere, adoptActiveNodeChangedElsewhere, activate, nodes } = useNode()
  const { error: notifyError } = useNotifications()
  const [busy, setBusy] = useState(false)

  if (!activeNode || !activeNodeChangedElsewhere) return null

  const keepShownNode = () => {
    setBusy(true)
    void activate(activeNode.id)
      .catch((err) => notifyError(err instanceof ApiError ? err.message : 'Ошибка активации узла'))
      .finally(() => setBusy(false))
  }

  return (
    <SettingsAlert variant="warning" title="Активный узел сменён в другом месте" className="mb-4">
      <p>
        Сейчас активен <strong>«{activeNodeChangedElsewhere.name}»</strong>: его выбрали в другой вкладке, в
        Telegram-боте или это сделал другой администратор. Эта вкладка показывает{' '}
        <strong>«{activeNode.name}»</strong>, и изменения из неё не применяются, пока вы не выберете узел.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={adoptActiveNodeChangedElsewhere} disabled={busy}>
          Перейти на «{activeNodeChangedElsewhere.name}»
        </Button>
        {user?.role === 'admin' && canReturnToShownNode(activeNode.id, nodes) && (
          <Button size="sm" variant="outline" onClick={keepShownNode} disabled={busy}>
            Вернуть «{activeNode.name}»
          </Button>
        )}
      </div>
    </SettingsAlert>
  )
}
