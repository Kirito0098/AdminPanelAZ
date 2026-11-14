import type { FormEvent, ReactNode } from 'react'
import { Loader2, Save } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { parseBoundedInt } from '@/lib/boundedInt'

export const QUOTA_MAX = 1000
export const RATE_MAX = 100
export const WINDOW_MIN_MINUTES = 1
export const WINDOW_MAX_MINUTES = 1440

export interface SelfServiceLimitsValues {
  quota: string
  rateMax: string
  windowMinutes: string
}

export interface ParsedSelfServiceLimits {
  quota: number | null
  rateMax: number | null
  windowMinutes: number | null
}

/** Round a stored window (seconds) to the minutes shown in the form. */
export function windowMinutesFromSeconds(seconds: number): string {
  return String(Math.max(WINDOW_MIN_MINUTES, Math.round(seconds / 60)))
}

export function parseSelfServiceLimits(values: SelfServiceLimitsValues): ParsedSelfServiceLimits {
  return {
    quota: parseBoundedInt(values.quota, 0, QUOTA_MAX),
    rateMax: parseBoundedInt(values.rateMax, 0, RATE_MAX),
    windowMinutes: parseBoundedInt(values.windowMinutes, WINDOW_MIN_MINUTES, WINDOW_MAX_MINUTES),
  }
}

interface FieldSpec {
  key: keyof SelfServiceLimitsValues
  id: string
  label: string
  hint?: string
  min: number
  max: number
}

const PANEL_FIELDS: FieldSpec[] = [
  {
    key: 'quota',
    id: 'limitQuotaDefault',
    label: 'Квота конфигов по умолчанию',
    hint: 'Для пользователей без своей квоты. 0 — без лимита.',
    min: 0,
    max: QUOTA_MAX,
  },
  {
    key: 'rateMax',
    id: 'limitCreateRateMax',
    label: 'Созданий за окно',
    hint: 'Сколько конфигов пользователь создаст подряд. 0 — без ограничения.',
    min: 0,
    max: RATE_MAX,
  },
  {
    key: 'windowMinutes',
    id: 'limitCreateRateWindow',
    label: 'Окно, минут',
    hint: `От ${WINDOW_MIN_MINUTES} до ${WINDOW_MAX_MINUTES} (сутки).`,
    min: WINDOW_MIN_MINUTES,
    max: WINDOW_MAX_MINUTES,
  },
]

const MINI_FIELDS: FieldSpec[] = [
  { key: 'quota', id: 'limit-quota', label: 'Квота по умолчанию', min: 0, max: QUOTA_MAX },
  { key: 'rateMax', id: 'limit-rate-max', label: 'Созданий за окно', min: 0, max: RATE_MAX },
  {
    key: 'windowMinutes',
    id: 'limit-rate-window',
    label: 'Окно создания, мин',
    min: WINDOW_MIN_MINUTES,
    max: WINDOW_MAX_MINUTES,
  },
]

const PANEL_FOOTNOTE =
  'Счётчик созданий хранится в памяти панели и обнуляется при её перезапуске. На администраторов лимиты не действуют.'
const MINI_FOOTNOTE = 'Счётчики хранятся в памяти панели и обнуляются при перезапуске.'
const MINI_GROUP_HINT = 'Создание конфигов обычными пользователями. 0 — без лимита.'

interface SelfServiceLimitsFormProps {
  values: SelfServiceLimitsValues
  onChange: (values: SelfServiceLimitsValues) => void
  onSave: () => void
  /** Disables the inputs and the save button while a save is in flight. */
  disabled?: boolean
  /** Mobile layout for the Mini App: taller inputs, short labels, submit button in a form. */
  compact?: boolean
  /** Extra fields rendered between the limits and the footnote. */
  children?: ReactNode
}

/**
 * Self-service limit fields shared by the admin panel and the Mini App.
 * Both callers keep their own loading/saving API calls and feedback texts.
 */
export default function SelfServiceLimitsForm({
  values,
  onChange,
  onSave,
  disabled = false,
  compact = false,
  children,
}: SelfServiceLimitsFormProps) {
  const fields = compact ? MINI_FIELDS : PANEL_FIELDS

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSave()
  }

  const content = (
    <>
      <div className={compact ? 'space-y-3' : undefined}>
        <div
          className={
            compact
              ? 'grid grid-cols-1 gap-3 min-[380px]:grid-cols-3'
              : 'grid gap-3 sm:grid-cols-3'
          }
        >
          {fields.map((field) => (
            <div key={field.key} className={compact ? 'space-y-2' : 'space-y-1.5'}>
              <Label htmlFor={field.id}>{field.label}</Label>
              <Input
                id={field.id}
                type="number"
                inputMode="numeric"
                min={field.min}
                max={field.max}
                value={values[field.key]}
                onChange={(e) => onChange({ ...values, [field.key]: e.target.value })}
                disabled={disabled}
                className={compact ? 'h-11' : undefined}
              />
              {field.hint && <p className="text-xs text-muted-foreground">{field.hint}</p>}
            </div>
          ))}
        </div>
        {compact && (
          <p className="text-xs leading-relaxed text-muted-foreground">{MINI_GROUP_HINT}</p>
        )}
      </div>
      {children}
      <p
        className={
          compact
            ? 'text-xs leading-relaxed text-muted-foreground'
            : 'text-xs text-muted-foreground'
        }
      >
        {compact ? MINI_FOOTNOTE : PANEL_FOOTNOTE}
      </p>
      {compact ? (
        <Button type="submit" className="gap-1.5" disabled={disabled}>
          {disabled ? <Loader2 size={16} className="animate-spin" aria-hidden /> : null}
          Сохранить лимиты
        </Button>
      ) : (
        <Button type="button" size="sm" onClick={onSave} disabled={disabled}>
          <Save size={15} />
          {disabled ? 'Сохранение...' : 'Сохранить лимиты'}
        </Button>
      )}
    </>
  )

  if (compact) {
    return (
      <form className="space-y-4" onSubmit={submit}>
        {content}
      </form>
    )
  }

  return <div className="space-y-3">{content}</div>
}
