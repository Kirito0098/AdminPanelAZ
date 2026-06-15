import { useCallback, useEffect, useState } from 'react'
import { getTgWarperStatus } from '@/tg-mini/api'
import Spinner from '@/components/ui/Spinner'
import { Button } from '@/components/ui/button'
import type { TgMiniWarperStatus } from '@/types'

export default function Warper() {
  const [data, setData] = useState<TgMiniWarperStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await getTgWarperStatus())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="tg-mini-center">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <div className="tg-mini-card tg-mini-error-panel">
        <p>{error}</p>
        <Button type="button" size="sm" onClick={() => void load()}>
          Повторить
        </Button>
      </div>
    )
  }

  return (
    <div className="tg-mini-stack">
      <section className="tg-mini-card">
        <h2 className="tg-mini-section-title">AZ-WARP</h2>
        <p className="tg-mini-muted">Узел: {data?.node_name}</p>
        <p className="tg-mini-muted">{data?.node_host}</p>
        <div className="tg-mini-status is-success mt-3">Статус: {data?.status ?? '—'}</div>
      </section>
      <Button type="button" variant="outline" onClick={() => void load()}>
        Обновить
      </Button>
    </div>
  )
}
