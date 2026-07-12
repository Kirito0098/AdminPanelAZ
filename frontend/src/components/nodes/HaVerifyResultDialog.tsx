import { AlertTriangle, CheckCircle2, Lightbulb, Server, XCircle } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { HaVerifyFileGroup, HaVerifyResultVariant, HaVerifyResultView } from '@/lib/haVerifySummary'
import { cn } from '@/lib/utils'

const variantStyles: Record<
  HaVerifyResultVariant,
  { icon: typeof CheckCircle2; iconClass: string; badge: 'default' | 'secondary' }
> = {
  success: {
    icon: CheckCircle2,
    iconClass: 'text-emerald-600 dark:text-emerald-400',
    badge: 'default',
  },
  warning: {
    icon: AlertTriangle,
    iconClass: 'text-amber-600 dark:text-amber-400',
    badge: 'secondary',
  },
}

type HaVerifyResultDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: HaVerifyResultView | null
}

function VerifyFileGroupList({ group }: { group: HaVerifyFileGroup }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-foreground">{group.label}</p>
      <ul
        className={cn(
          'space-y-1 rounded-md border bg-background/70 p-2',
          group.files.length > 6 && 'max-h-36 overflow-y-auto',
        )}
      >
        {group.files.map((file) => (
          <li key={file.filename} className="text-xs leading-snug">
            <span className="font-mono text-foreground">{file.filename}</span>
            {file.title ? (
              <span className="mt-0.5 block text-[11px] text-muted-foreground">{file.title}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function HaVerifyResultDialog({ open, onOpenChange, result }: HaVerifyResultDialogProps) {
  if (!result) return null

  const { icon: HeaderIcon, iconClass, badge } = variantStyles[result.variant]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(90dvh,40rem)] max-w-2xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 space-y-3 border-b px-6 py-5 text-left">
          <DialogTitle className="flex items-start gap-3 pr-8 text-left text-lg leading-snug">
            <HeaderIcon className={cn('mt-0.5 h-5 w-5 shrink-0', iconClass)} />
            <span className="min-w-0">{result.title}</span>
          </DialogTitle>
          <DialogDescription className="text-left leading-relaxed">{result.description}</DialogDescription>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={badge} className="w-fit">
              {result.variant === 'success' ? 'Готово' : 'Требует внимания'}
            </Badge>
            <Badge variant="outline" className="w-fit font-normal">
              {result.domain}
            </Badge>
          </div>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <section className="mb-4 rounded-lg border bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Что проверялось
            </p>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {result.checkedSummary.map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600/70 dark:text-emerald-400/70" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>

          {result.primaryProfileIssues?.length ? (
            <section className="mb-4 space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Основной узел
              </p>
              <ul className="space-y-2">
                {result.primaryProfileIssues.map((mismatch, index) => (
                  <li
                    key={`primary-profile-${mismatch.title}-${index}`}
                    className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3"
                  >
                    <p className="text-sm font-medium text-foreground">{mismatch.title}</p>
                    {mismatch.details.length ? (
                      <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
                        {mismatch.details.map((detail) => (
                          <li key={detail}>{detail}</li>
                        ))}
                      </ul>
                    ) : null}
                    {mismatch.hint ? (
                      <p className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-amber-800 dark:text-amber-200">
                        <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>{mismatch.hint}</span>
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {result.replicas.length ? (
            <ul className="space-y-3">
              {result.replicas.map((replica) => (
                <li key={replica.nodeName} className="rounded-lg border bg-muted/20 p-4">
                  <div className="flex items-start gap-3">
                    {replica.ok ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                    )}
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex items-center gap-1.5 text-sm font-medium">
                          <Server className="h-3.5 w-3.5 text-muted-foreground" />
                          Реплика: {replica.nodeName}
                        </span>
                        <Badge variant={replica.online ? 'outline' : 'destructive'} className="text-[10px]">
                          {replica.online ? 'доступна' : 'недоступна'}
                        </Badge>
                      </div>

                      <p className="text-sm text-foreground">{replica.summary}</p>

                      {replica.checkedItems?.length ? (
                        <ul className="space-y-0.5 text-xs text-muted-foreground">
                          {replica.checkedItems.map((item) => (
                            <li key={item}>✓ {item}</li>
                          ))}
                        </ul>
                      ) : null}

                      {!replica.ok ? (
                        <ul className="space-y-2">
                          {replica.mismatches.map((mismatch, index) => (
                            <li
                              key={`${replica.nodeName}-${mismatch.title}-${index}`}
                              className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3"
                            >
                              <p className="text-sm font-medium text-foreground">{mismatch.title}</p>
                              {mismatch.details.length ? (
                                <ul className="mt-1 space-y-0.5 text-sm text-muted-foreground">
                                  {mismatch.details.map((detail) => (
                                    <li key={detail}>{detail}</li>
                                  ))}
                                </ul>
                              ) : null}
                              {mismatch.fileGroups?.length ? (
                                <div className="mt-2 space-y-2">
                                  {mismatch.fileGroups.map((group) => (
                                    <VerifyFileGroupList key={group.label} group={group} />
                                  ))}
                                </div>
                              ) : null}
                              {mismatch.hint ? (
                                <p className="mt-2 flex items-start gap-1.5 text-xs leading-relaxed text-amber-800 dark:text-amber-200">
                                  <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                                  <span>{mismatch.hint}</span>
                                </p>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Нет данных по репликам.</p>
          )}

          {result.nextStep ? (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm leading-relaxed text-foreground">
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <p>
                <span className="font-medium">Дальше: </span>
                {result.nextStep}
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter className="shrink-0 border-t px-6 py-4 sm:justify-end">
          <Button type="button" onClick={() => onOpenChange(false)}>
            Закрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
