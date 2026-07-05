export const TG_MINI_NO_INIT_DATA =
  'Откройте через кнопку «Открыть Mini App» в боте. Если ошибка повторяется — в BotFather укажите домен панели и URL Mini App из раздела Telegram.'

export function getTelegramWebApp() {
  return window.Telegram?.WebApp ?? null
}

type TgWebApp = NonNullable<ReturnType<typeof getTelegramWebApp>>

/** initData from WebApp API or launch URL (#tgWebAppData=…). */
export function resolveTelegramInitData(tg: TgWebApp | null | undefined): string {
  const direct = tg?.initData?.trim()
  if (direct) return direct

  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : ''
  if (hash) {
    const fromHash = new URLSearchParams(hash).get('tgWebAppData')?.trim()
    if (fromHash) return fromHash
  }

  const fromSearch = new URLSearchParams(window.location.search).get('tgWebAppData')?.trim()
  if (fromSearch) return fromSearch

  return ''
}

export async function waitForTelegramInitData(tg: TgWebApp | null): Promise<string> {
  tg?.ready()
  tg?.expand()

  const delays = [0, 50, 100, 200, 400, 700, 1200]
  for (const delay of delays) {
    if (delay > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay))
    }
    const initData = resolveTelegramInitData(tg)
    if (initData) return initData
  }

  return ''
}
