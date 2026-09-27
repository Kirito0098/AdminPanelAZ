import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import ServerUnavailableScreen from './ServerUnavailableScreen'
import Spinner from './ui/Spinner'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading, unavailable, retry } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-dscreen items-center justify-center bg-background">
        <Spinner label="Загрузка..." />
      </div>
    )
  }
  if (!user && unavailable) return <ServerUnavailableScreen message={unavailable} onRetry={() => void retry()} />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}
