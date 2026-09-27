import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { reloadOnChunkError } from '@/lib/lazyWithRetry'

type Props = {
  children: ReactNode
  /** Optional label for the failed section (shown in the fallback). */
  label?: string
  /** A caught error is cleared when this value changes (e.g. the route pathname). */
  resetOn?: unknown
}

type State = {
  error: Error | null
  resetKey: number
  resetOn: unknown
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: 0, resetOn: this.props.resetOn }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    if (Object.is(props.resetOn, state.resetOn)) return null
    return { error: null, resetOn: props.resetOn }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error boundary caught', error, info.componentStack)
    reloadOnChunkError(error)
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
