import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ShieldOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Spinner from '@/components/ui/Spinner'
import { useFeatureModules } from '@/context/FeatureModulesContext'

interface FeatureGuardRouteProps {
  feature: string
  children: ReactNode
}

export default function FeatureGuardRoute({ feature, children }: FeatureGuardRouteProps) {
  const { isEnabled, loading } = useFeatureModules()

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner label="Проверка модулей..." />
      </div>
    )
  }

  if (!isEnabled(feature)) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldOff size={18} />
            Раздел отключён
          </CardTitle>
          <CardDescription>Администратор отключил этот модуль в настройках панели.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="secondary">
            <Link to="/">На главную</Link>
          </Button>
        </CardContent>
      </Card>
    )
  }

  return <>{children}</>
}
