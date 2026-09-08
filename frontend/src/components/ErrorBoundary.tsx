import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

type Props = {
  children: ReactNode
  /** Optional label for the failed section (shown in the fallback). */
  label?: string
}

type State = {
  error: Error | null
  resetKey: number
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: 0 }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error boundary caught', error, info.componentStack)
  }

  private handleReload = () => {
    this.setState({ error: null })
    window.location.reload()
  }

  private handleRetry = () => {
    this.setState((s) => ({ error: null, resetKey: s.resetKey + 1 }))
  }

  render() {
    if (!this.state.error) {
      return <Fragment key={this.state.resetKey}>{this.props.children}</Fragment>
    }

    const section = this.props.label ? ` (${this.props.label})` : ''

    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 px-4 text-center">
        <p className="text-base font-medium text-foreground">Не удалось отобразить раздел{section}</p>
        <p className="max-w-md text-sm text-muted-foreground">
          Произошла ошибка в интерфейсе. Можно попробовать снова или перезагрузить страницу.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button type="button" variant="outline" onClick={this.handleRetry}>
            Попробовать снова
          </Button>
          <Button type="button" onClick={this.handleReload}>
            Перезагрузить
          </Button>
        </div>
      </div>
    )
  }
}
