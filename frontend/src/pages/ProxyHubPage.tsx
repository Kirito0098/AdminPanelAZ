import { Navigate } from 'react-router-dom'
import ProxyHubView from '@/components/proxy/ProxyHubView'
import { useAuth } from '@/context/AuthContext'

export default function ProxyHubPage() {
  const { user } = useAuth()

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  return <ProxyHubView />
}
