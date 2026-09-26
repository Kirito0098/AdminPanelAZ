import { ServerCrash } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function ServerUnavailableScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex min-h-dscreen items-center justify-center bg-background p-4">
      <div role="alert" className="w-full max-w-md space-y-4 text-center">
        <ServerCrash className="mx-auto h-10 w-10 text-muted-foreground" />
        <h1 className="text-lg font-semibold">Панель недоступна</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button onClick={onRetry}>Повторить</Button>
      </div>
    </div>
  )
}
