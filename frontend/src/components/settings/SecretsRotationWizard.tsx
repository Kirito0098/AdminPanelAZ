import { useEffect, useState } from 'react'
import { KeyRound, RefreshCw } from 'lucide-react'
import {
  ApiError,
  applySecretsRotation,
  getSecretsRotationCatalog,
  previewSecretsRotation,
} from '@/api/client'
import SettingsAlert from '@/components/settings/SettingsAlert'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Spinner from '@/components/ui/Spinner'
import { useNotifications } from '@/context/NotificationContext'
import type { SecretRotationItem, SecretRotationPreview } from '@/types'

type WizardStep = 'select' | 'configure' | 'preview' | 'confirm' | 'done'

export default function SecretsRotationWizard() {
  const { success, error: notifyError } = useNotifications()
  const [catalog, setCatalog] = useState<SecretRotationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [step, setStep] = useState<WizardStep>('select')
  const [selected, setSelected] = useState<SecretRotationItem | null>(null)
  const [customValue, setCustomValue] = useState('')
  const [preview, setPreview] = useState<SecretRotationPreview | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [busy, setBusy] = useState(false)
  const [applyResult, setApplyResult] = useState<string[]>([])

  const loadCatalog = async () => {
    try {
      setCatalog(await getSecretsRotationCatalog())
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка загрузки секретов')
    }
  }

  useEffect(() => {
    setLoading(true)
    loadCatalog().finally(() => setLoading(false))
  }, [])

  const resetWizard = () => {
    setStep('select')
    setSelected(null)
    setCustomValue('')
    setPreview(null)
    setConfirmText('')
    setApplyResult([])
  }

  const closeWizard = () => {
    if (busy) return
    setWizardOpen(false)
    resetWizard()
  }

  const handleSelect = (item: SecretRotationItem) => {
    setSelected(item)
    setCustomValue('')
    setPreview(null)
    setConfirmText('')
    setStep(item.auto_generate ? 'configure' : 'configure')
  }

  const handlePreview = async () => {
    if (!selected) return
    setBusy(true)
    try {
      const result = await previewSecretsRotation(
        selected.secret_id,
        selected.auto_generate && !customValue.trim() ? undefined : customValue.trim() || undefined,
      )
      setPreview(result)
      setStep('preview')
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка предпросмотра')
    } finally {
      setBusy(false)
    }
  }

  const handleApply = async () => {
    if (!preview) return
    setBusy(true)
    try {
      const result = await applySecretsRotation({
        secret_id: preview.secret_id,
        new_value: preview.new_value,
        preview_token: preview.preview_token,
        confirm: confirmText,
      })
      setApplyResult(result.next_steps)
      success(result.message)
      setStep('done')
      await loadCatalog()
    } catch (err) {
      notifyError(err instanceof ApiError ? err.message : 'Ошибка применения')
    } finally {
      setBusy(false)
    }
  }

  const stepTitle = (() => {
    switch (step) {
      case 'select':
        return 'Ротация секретов'
      case 'configure':
        return selected?.label ?? 'Настройка'
      case 'preview':
        return 'Предпросмотр изменений'
      case 'confirm':
        return 'Подтверждение записи'
      case 'done':
        return 'Готово'
      default:
        return 'Ротация секретов'
    }
  })()

  const stepDescription = (() => {
    switch (step) {
      case 'select':
        return 'Выберите секрет для ротации. Запись выполняется только после явного подтверждения.'
      case 'configure':
        return selected?.auto_generate
          ? 'Сгенерируйте новое значение или вставьте своё.'
          : 'Вставьте новый токен из @BotFather.'
      case 'preview':
        return 'Проверьте предупреждения и изменения перед записью.'
      case 'confirm':
        return `Введите «${preview?.confirm_phrase ?? 'ROTATE'}» для записи в .env или БД.`
      case 'done':
        return 'Секрет обновлён. Выполните шаги ниже.'
      default:
        return undefined
    }
  })()

  if (loading) {
    return <Spinner label="Загрузка секретов..." className="py-4" />
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound size={18} />
            Ротация секретов
          </CardTitle>
          <CardDescription>
            Пошаговый мастер для SECRET_KEY, NODE_AGENT_API_KEY и токена Telegram-бота — с предпросмотром и
            подтверждением (без тихой перезаписи .env)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <SettingsAlert variant="info" title="Безопасный flow">
            предпросмотр → подтверждение → запись. Подробнее см. SECURITY.md в репозитории.
          </SettingsAlert>
          <div className="grid gap-3 sm:grid-cols-3">
            {catalog.map((item) => (
              <div key={item.secret_id} className="rounded-md border p-3 text-sm">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="font-medium">{item.label}</span>
                  <Badge variant={item.configured ? 'default' : 'secondary'}>
                    {item.configured ? 'задан' : 'не задан'}
                  </Badge>
                </div>
                <p className="text-xs text-muted-foreground">{item.description}</p>
                <p className="mt-2 font-mono text-xs text-muted-foreground">{item.masked_current}</p>
              </div>
            ))}
          </div>
          <Button onClick={() => setWizardOpen(true)}>
            <RefreshCw size={16} />
            Открыть мастер ротации
          </Button>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={wizardOpen}
        onOpenChange={(open) => (open ? setWizardOpen(true) : closeWizard())}
        title={stepTitle}
        description={stepDescription}
        icon={KeyRound}
        confirmLabel={
          step === 'select'
            ? 'Далее'
            : step === 'configure'
              ? 'Предпросмотр'
              : step === 'preview'
                ? 'К подтверждению'
                : step === 'confirm'
                  ? 'Записать'
                  : 'Закрыть'
        }
        cancelLabel="Отмена"
        destructive={step === 'confirm'}
        loading={busy}
        onConfirm={async () => {
          if (step === 'select') {
            if (!selected) {
              notifyError('Выберите секрет')
              return
            }
            setStep('configure')
            return
          }
          if (step === 'configure') {
            await handlePreview()
            return
          }
          if (step === 'preview') {
            setStep('confirm')
            return
          }
          if (step === 'confirm') {
            await handleApply()
            return
          }
          closeWizard()
        }}
        className="max-w-xl"
        alert={
          preview?.requires_relogin && (step === 'preview' || step === 'confirm')
            ? {
                variant: 'warning',
                title: 'Потребуется повторный вход',
                children:
                  'После смены SECRET_KEY все JWT-сессии станут недействительны. Сохраните работу и будьте готовы войти заново.',
              }
            : undefined
        }
      >
        {step === 'select' && (
          <div className="space-y-2 py-2">
            {catalog.map((item) => (
              <label
                key={item.secret_id}
                className={`flex cursor-pointer gap-3 rounded-md border p-3 text-sm ${
                  selected?.secret_id === item.secret_id ? 'border-primary bg-primary/5' : ''
                }`}
              >
                <input
                  type="radio"
                  name="secret"
                  checked={selected?.secret_id === item.secret_id}
                  onChange={() => handleSelect(item)}
                  className="mt-1"
                />
                <div>
                  <div className="font-medium">{item.label}</div>
                  <div className="text-xs text-muted-foreground">{item.description}</div>
                  <div className="mt-1 font-mono text-xs">{item.masked_current}</div>
                </div>
              </label>
            ))}
          </div>
        )}

        {step === 'configure' && selected && (
          <div className="space-y-4 py-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setStep('select')}>
              ← Назад
            </Button>
            {selected.auto_generate ? (
              <>
                <SettingsAlert variant="info">
                  Оставьте поле пустым — будет сгенерировано случайное значение ({selected.label}).
                </SettingsAlert>
                <div className="space-y-2">
                  <Label htmlFor="secret-custom">Или вставьте своё значение</Label>
                  <Input
                    id="secret-custom"
                    type="password"
                    autoComplete="off"
                    value={customValue}
                    onChange={(e) => setCustomValue(e.target.value)}
                    placeholder="Опционально"
                  />
                </div>
              </>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="tg-token">Новый Telegram bot token</Label>
                <Input
                  id="tg-token"
                  type="password"
                  autoComplete="off"
                  value={customValue}
                  onChange={(e) => setCustomValue(e.target.value)}
                  placeholder="123456789:ABCdef..."
                />
              </div>
            )}
          </div>
        )}

        {step === 'preview' && preview && (
          <div className="space-y-4 py-2 text-sm">
            <Button type="button" variant="ghost" size="sm" onClick={() => setStep('configure')}>
              ← Назад
            </Button>
            <div className="grid gap-2 rounded-md border p-3">
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Текущее</span>
                <span className="font-mono">{preview.masked_current}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-muted-foreground">Новое</span>
                <span className="font-mono">{preview.masked_new_value}</span>
              </div>
            </div>
            {preview.env_change && (
              <div className="rounded-md border p-3 text-xs">
                <p className="font-medium">Запись в файл</p>
                <p className="mt-1 font-mono text-muted-foreground">{preview.env_change.path}</p>
                <p className="mt-1">
                  {preview.env_change.key}={preview.env_change.masked_new_value}
                </p>
              </div>
            )}
            {preview.storage === 'db' && (
              <SettingsAlert variant="info">Значение будет записано в БД панели (AppSetting).</SettingsAlert>
            )}
            {preview.warnings.length > 0 && (
              <SettingsAlert variant="warning" title="Предупреждения">
                <ul className="list-disc space-y-1 pl-4">
                  {preview.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </SettingsAlert>
            )}
          </div>
        )}

        {step === 'confirm' && preview && (
          <div className="space-y-4 py-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setStep('preview')}>
              ← Назад
            </Button>
            <SettingsAlert variant="danger" title="Необратимая запись">
              Будет изменён <strong>{preview.label}</strong>. Автоматической отмены нет — только ручная
              повторная ротация.
            </SettingsAlert>
            <div className="space-y-2">
              <Label htmlFor="confirm-rotate">
                Введите «{preview.confirm_phrase}» для подтверждения
              </Label>
              <Input
                id="confirm-rotate"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={preview.confirm_phrase}
                autoComplete="off"
              />
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="space-y-3 py-2 text-sm">
            {applyResult.length > 0 && (
              <SettingsAlert variant="info" title="Следующие шаги">
                <ul className="list-disc space-y-1 pl-4">
                  {applyResult.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </SettingsAlert>
            )}
          </div>
        )}
      </ConfirmDialog>
    </>
  )
}
