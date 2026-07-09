import type { BackgroundTask } from '@/types'

/** Пояснение в карточке обновления / пересборки. */
export const UPDATE_LONG_RUNNING_NOTICE =
  'Обновление может занять от нескольких минут до 15–20 минут на слабом сервере — особенно этап сборки интерфейса (npm run build:all). ' +
  'В это время процессор и память сервера загружены почти полностью. Не закрывайте вкладку и не запускайте процесс повторно.'

/** Текст в диалоге подтверждения. */
export const UPDATE_CONFIRM_DURATION_NOTICE =
  'Процесс может занять продолжительное время (до 15–20 минут на слабом VPS). Не прерывайте его и не запускайте повторно.'

/** Заголовок блока про ложную ошибку опроса. */
export const UPDATE_POLL_BUSY_ALERT_TITLE = 'Если появилась «Ошибка опроса» с HTML-кодом'

/** Пояснение ложной ошибки опроса во время сборки. */
export const UPDATE_POLL_BUSY_ALERT_BODY =
  'Скорее всего сервер сейчас занят сборкой проекта и временно не отвечает на запросы статуса — это нормально для слабых VPS. ' +
  'Ничего не предпринимайте: не нажимайте «Применить обновление» снова и не перезагружайте сервер. ' +
  'Подождите 5–15 минут, обновите страницу (F5) и проверьте, совпали ли хеши «Установлено» и «На сервере» в этом разделе.'

/** Короткое уведомление при срабатывании опроса во время сборки. */
export const UPDATE_POLL_BUSY_TOAST =
  'Сервер, вероятно, занят сборкой интерфейса и временно не отвечает. Подождите 5–15 минут, обновите страницу и проверьте версии — повторно обновление запускать не нужно.'

export function isLikelyBuildBusyPollError(
  message: string,
  task?: BackgroundTask | null,
): boolean {
  const text = message.toLowerCase()
  const pollError = text.includes('ошибка опроса') || text.includes('ошибка отслеживания')
  const htmlBody = text.includes('<!doctype') || text.includes('<html')
  const stage = (task?.progress_stage || task?.message || '').toLowerCase()
  const inBuildPhase =
    (task?.progress_percent != null && task.progress_percent >= 50) ||
    stage.includes('сборка') ||
    stage.includes('build')

  return (pollError && htmlBody) || (pollError && inBuildPhase)
}

export function resolveUpdateTaskErrorMessage(
  message: string,
  task?: BackgroundTask | null,
): string {
  if (isLikelyBuildBusyPollError(message, task)) {
    return UPDATE_POLL_BUSY_TOAST
  }
  return task?.error || task?.message || message
}
