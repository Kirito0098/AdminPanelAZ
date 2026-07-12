import { AlertTriangle, CheckCircle2, MinusCircle, Server, XCircle } from 'lucide-react'
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
import type { HaSyncItemStatus, HaSyncResultVariant, HaSyncResultView } from '@/lib/haSyncSummary'
import { cn } from '@/lib/utils'

const variantStyles: Record<
  HaSyncResultVariant,
  { icon: typeof CheckCircle2; iconClass: string; badge: 'default' | 'secondary' | 'destructive' }
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
  error: {
    icon: XCircle,
    iconClass: 'text-destructive',
    badge: 'destructive',
  },
}

const itemStatusStyles: Record<HaSyncItemStatus, { icon: typeof CheckCircle2; className: string }> = {
  success: {
    icon: CheckCircle2,
    className: 'text-emerald-600 dark:text-emerald-400',
  },
  warning: {
    icon: AlertTriangle,
    className: 'text-amber-600 dark:text-amber-400',
  },
  error: {
    icon: XCircle,
    className: 'text-destructive',
  },
  skipped: {
    icon: MinusCircle,
    className: 'text-muted-foreground',
  },
}

type HaSyncResultDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: HaSyncResultView | null
}

export default function HaSyncResultDialog({ open, onOpenChange, result }: HaSyncResultDialogProps) {
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
          {result.description ? (
            <DialogDescription className="text-left">{result.description}</DialogDescription>
          ) : null}
          <Badge variant={badge} className="w-fit">
            {result.variant === 'success'
              ? 'Успешно'
              : result.variant === 'warning'
                ? 'С предупреждениями'
                : 'Ошибка'}
          </Badge>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {result.sections.length ? (
            <div className="space-y-5">
              {result.sections.map((section) => (
                <section key={section.title} className="space-y-2">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{section.title}</h3>
                    {section.description ? (
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                        {section.description}
                      </p>
                    ) : null}
                  </div>
                  <ul className="space-y-2">
                    {section.items.map((item, index) => {
                      const { icon: ItemIcon, className } = itemStatusStyles[item.status]
                      return (
                        <li
                          key={`${section.title}-${item.nodeName}-${index}`}
                          className="rounded-lg border bg-muted/20 p-3"
                        >
                          <div className="flex items-start gap-3">
                            <ItemIcon className={cn('mt-0.5 h-4 w-4 shrink-0', className)} />
                            <div className="min-w-0 flex-1 space-y-1.5">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="inline-flex items-center gap-1.5 text-sm font-medium">
                                  <Server className="h-3.5 w-3.5 text-muted-foreground" />
                                  {item.nodeName}
                                </span>
                              </div>
                              <p className="text-sm text-foreground">{item.text}</p>
                              {item.explanation ? (
                                <p className="text-xs leading-relaxed text-muted-foreground">
                                  {item.explanation}
                                </p>
                              ) : null}
                              {item.details?.length ? (
                                <ul className="space-y-0.5 rounded-md bg-background/60 px-2 py-1.5 text-xs text-muted-foreground">
                                  {item.details.map((detail) => (
                                    <li key={detail}>{detail}</li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {result.description || 'Операция завершена без детального отчёта.'}
            </p>
          )}
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
