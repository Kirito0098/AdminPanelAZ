import { useState, type FormEvent } from 'react'
import { Link2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface TelegramLinkCodeFormProps {
  idPrefix: string
  disabled?: boolean
  onRequest: (currentPassword: string) => Promise<boolean>
}

export default function TelegramLinkCodeForm({ idPrefix, disabled = false, onRequest }: TelegramLinkCodeFormProps) {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const inputId = `${idPrefix}-link-code-password`

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!password) return
    setLoading(true)
    try {
      if (await onRequest(password)) setPassword('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(event) => void handleSubmit(event)}>
      <div className="space-y-1.5 sm:w-64">
        <Label htmlFor={inputId}>Текущий пароль</Label>
        <Input
          id={inputId}
          type="password"
          autoComplete="current-password"
          value={password}
          disabled={disabled || loading}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>
      <Button type="submit" variant="secondary" className="gap-1.5" disabled={disabled || loading || !password}>
        <Link2 size={16} />
        {loading ? 'Создание…' : 'Получить код для привязки'}
      </Button>
    </form>
  )
}
