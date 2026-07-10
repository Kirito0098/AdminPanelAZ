import { CheckCircle2, ExternalLink, Loader2, Rocket } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { PUBLISH_RESTART_WAIT_NOTICE } from '@/components/settings/publishWizardUi'

export type PublishAwaitDialogState = {
  accessUrl: string
  status: 'running' | 'completed' | 'failed'
  message?: string
  restartCommand?: string
  allowDismissWhileRunning?: boolean
}

interface PublishAwaitDialogProps {
  state: PublishAwaitDialogState | null
  onDismiss: () => void
}

export default function PublishAwaitDialog({ state, onDismiss }: PublishAwaitDialogProps) {
  if (!state) return null

  const closable = state.status !== 'running' || state.allowDismissWhileRunning === true
  const accessUrl = state.accessUrl.trim()

  const handleOpenChange = (open: boolean) => {
    if (!open && closable) onDismiss()
  }

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-lg"
        hideClose={!closable}
        onPointerDownOutside={(event) => {
          if (!closable) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (!closable) event.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {state.status === 'running' && <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />}
            {state.status === 'completed' && <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-500" />}
            {state.status === 'failed' && <Rocket className="h-5 w-5 shrink-0 text-destructive" />}
            {state.status === 'running' && 'Публикация запущена'}
            {state.status === 'completed' && 'Публикация завершена'}
            {state.status === 'failed' && 'Не удалось запустить публикацию'}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {state.status === 'running'
              ? 'Дождитесь завершения и откройте новый адрес панели'
              : state.message || 'Статус публикации панели'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm leading-relaxed">
          {state.status === 'running' && (
            <>
              <p>{state.message || 'Настройки применяются на сервере. Это может занять несколько минут.'}</p>
              {accessUrl ? (
                <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5">
                  <p className="text-xs text-muted-foreground">Перейдите по адресу:</p>
                  <p className="mt-1 break-all font-mono text-sm text-primary">{accessUrl}</p>
                </div>
              ) : null}
              <p className="text-muted-foreground">{PUBLISH_RESTART_WAIT_NOTICE}</p>
              <p className="text-xs text-muted-foreground">
                {state.allowDismissWhileRunning
                  ? 'Связь с сервером могла прерваться при перезапуске — откройте адрес выше через несколько минут.'
                  : 'Пока идёт публикация, это окно нельзя закрыть. Если связь прервалась — просто откройте адрес выше через несколько минут.'}
              </p>
            </>
          )}

          {state.status === 'completed' && (
            <>
              <p>{state.message || 'Публикация успешно завершена.'}</p>
              {state.restartCommand ? (
                <p className="rounded-lg border bg-muted/30 px-3 py-2 font-mono text-xs">{state.restartCommand}</p>
              ) : null}
              {accessUrl ? (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5">
                  <p className="text-xs text-muted-foreground">Откройте панель по адресу:</p>
                  <p className="mt-1 break-all font-mono text-sm text-primary">{accessUrl}</p>
                </div>
              ) : null}
              <p className="text-muted-foreground">{PUBLISH_RESTART_WAIT_NOTICE}</p>
            </>
          )}

          {state.status === 'failed' && (
            <p className="text-destructive">{state.message || 'Попробуйте ещё раз через минуту.'}</p>
          )}
        </div>

        {closable && (
          <DialogFooter className="gap-2 sm:gap-0">
            {state.status === 'completed' && accessUrl ? (
              <Button asChild>
                <a href={accessUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={16} />
                  Открыть панель
                </a>
              </Button>
            ) : null}
            <Button type="button" variant={state.status === 'completed' ? 'outline' : 'default'} onClick={onDismiss}>
              {state.status === 'completed' ? 'Закрыть' : 'Понятно'}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
