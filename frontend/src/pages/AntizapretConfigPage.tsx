import { Navigate } from 'react-router-dom'
import AntizapretConfigTab from '@/components/routing/AntizapretConfigTab'
import { useAuth } from '@/context/AuthContext'

export default function AntizapretConfigPage() {
  const { user } = useAuth()

  if (user?.role !== 'admin') {
    return <Navigate to="/routing" replace />
  }

  return <AntizapretConfigTab />
}
