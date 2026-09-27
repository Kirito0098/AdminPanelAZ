import { Suspense, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import ErrorBoundary from './ErrorBoundary'
import Spinner from './ui/Spinner'

function PageFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Spinner label="Загрузка…" />
    </div>
  )
}

export default function LazyPage({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return (
    <ErrorBoundary resetOn={pathname}>
      <Suspense fallback={<PageFallback />}>{children}</Suspense>
    </ErrorBoundary>
  )
}
