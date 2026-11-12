import { Navigate } from 'react-router-dom'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'

interface AdminGateProps {
  children: JSX.Element
}

/** Admin-only screen: a non-admin is redirected before the page mounts. */
export default function AdminGate({ children }: AdminGateProps) {
  const { isAdmin } = useTgAuth()

  if (!isAdmin) {
    return <Navigate to="/configs" replace />
  }

  return children
}
