import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useProgress } from '../context/ProgressContext'

export default function RouteProgress() {
  const location = useLocation()
  const { startGlobal, doneGlobal } = useProgress()

  useEffect(() => {
    startGlobal()
    const timer = setTimeout(doneGlobal, 400)
    return () => {
      clearTimeout(timer)
      doneGlobal()
    }
  }, [location.pathname, startGlobal, doneGlobal])

  return null
}
