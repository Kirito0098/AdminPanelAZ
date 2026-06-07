import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

interface LiveClockProps {
  className?: string
}

export default function LiveClock({ className }: LiveClockProps) {
  const [time, setTime] = useState('')

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('ru-RU'))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  return <span className={cn('mono text-xs text-muted-foreground', className)}>{time}</span>
}
