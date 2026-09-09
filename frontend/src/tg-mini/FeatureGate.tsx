import { Navigate } from 'react-router-dom'
import { useTgAuth } from '@/tg-mini/context/TgAuthContext'

interface FeatureGateProps {
  featureKey: string
  children: JSX.Element
}

export default function FeatureGate({ featureKey, children }: FeatureGateProps) {
  const { features, featuresReady } = useTgAuth()

  if (!featuresReady) {
    return null
  }

  if (!Boolean(features[featureKey])) {
    return <Navigate to="/" replace />
  }

  return children
}
