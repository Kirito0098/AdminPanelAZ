# Ревью Telegram Mini App: найденные ошибки и нелогичные моменты

> Документ для изучения. Код **не менялся**. Здесь только анализ и предложения по исправлению.
> Файлы-источники:
> - Фронтенд: `frontend/src/tg-mini/api.ts`, `App.tsx`, `context/TgAuthContext.tsx`,
>   `layout/MiniShell.tsx`, `pages/{Dashboard,Configs,Nodes,Warper,Cidr,Settings,TelegramSettings}.tsx`,
>   `frontend/src/types.ts`, `frontend/src/vite-env.d.ts`.
> - Бэкенд: `backend/app/routers/tg_mini.py`, `backend/app/services/tg_mini_status.py`.

## Краткий итог

| # | Проблема | Серьёзность | Где |
|---|----------|-------------|-----|
| 1 | `/dashboard` утечка данных: обычный user/viewer видит ВСЕХ клиентов сервера | Критично | `tg_mini.py` `mini_dashboard` |
| 2 | Истёкший JWT не обрабатывается на страницах данных (нет перехвата 401) | Важно | `api.ts` `tgFetch`, `TgAuthContext.tsx` |
| 3 | Наивный UTC timestamp → неправильное время на клиенте | Важно | `tg_mini.py` `mini_dashboard`, `Dashboard.tsx`, `Nodes.tsx` |
| 4 | QR-ссылка: одноразовый токен сразу «сжигается», QR не показывается, clipboard падает | Важно | `Configs.tsx` `handleQrLink` |
| 5 | Маршруты `/warper` и `/cidr` не защищены `isAdmin` на фронте (в отличие от `/nodes`) | Важно | `App.tsx`, `Warper.tsx`, `Cidr.tsx` |
| 6 | `total_configs` на дашборде ≠ числу конфигов на странице «Конфиги» для админа | Важно | `tg_mini.py` `mini_dashboard` vs `mini_configs` |
| 7 | Статус WARP: в зелёный блок вываливается весь сырой Python-dict; цвет всегда «success» | Важно | `tg_mini_status.py`, `Warper.tsx` |
| 8 | CIDR: метка «Последнее обновление» показывает статус-строку, а не дату | Мелочь | `Cidr.tsx` |
| 9 | Несогласованная обработка ошибок (`instanceof Error` vs `ApiError`) | Мелочь | `Warper.tsx`, `Cidr.tsx` |
| 10 | Коллизия имён: компонент и тип `TelegramSettings` в одном модуле | Мелочь | `TelegramSettings.tsx` |
| 11 | `error` не сбрасывается в начале ряда обработчиков → старая ошибка «висит» | Мелочь | `Settings.tsx`, `TelegramSettings.tsx` |
| 12 | `replaceNode` дважды вызывает `setNodes` при активации | Мелочь | `Nodes.tsx` |
| 13 | `auth_max_age` молча клампится (30..86400), UI без валидации | Мелочь | `tg_mini.py`, `TelegramSettings.tsx` |
| 14 | Диалог конфига при `files.length===0` пустой, без сообщения | Мелочь | `Configs.tsx` |
| 15 | JWT в `localStorage` (XSS-риск) — стоит зафиксировать как осознанный компромисс | Наблюдение | `api.ts` |

---

## 1. Критично: `/dashboard` отдаёт всех клиентов сервера любому пользователю

### Симптом
Эндпоинт `mini_dashboard` защищён только `Depends(get_current_user)` (любая роль), но возвращает
**серверные** данные: список всех подключённых OpenVPN-клиентов (с `common_name`) и всех WireGuard-пиров
(с именами/ключами/трафиком). То есть обычный `user`/`viewer` видит клиентов **других** пользователей.

Сравните: на странице «Конфиги» (`mini_configs`) для не-админа стоит фильтр
`VpnConfig.owner_id == current_user.id`, а на дашборде такого фильтра для списков клиентов нет.

### Текущий код
```361:388:backend/app/routers/tg_mini.py
@router.get("/dashboard")
def mini_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    adapter = get_active_adapter(db)
    ovpn = adapter.parse_openvpn_status()
    wg = adapter.parse_wireguard_status()
    ...
        "openvpn_clients": [c.model_dump() if hasattr(c, "model_dump") else c.__dict__ for c in ovpn[:20]],
        "wireguard_peers": [ ... for p in wg[:20] ],
```

### Предлагаемая правка
Вариант A (рекомендуется): для не-админа отдавать только агрегированные счётчики, а списки
`openvpn_clients` / `wireguard_peers` оставлять пустыми (или фильтровать по своим конфигам).
Вариант B: вынести подробные списки в отдельный admin-only эндпоинт, а `/dashboard` оставить со счётчиками.

---

## 2. Важно: истёкший JWT не обрабатывается на страницах данных

### Симптом
Токен кладётся в `localStorage` и используется бессрочно. Повторная авторизация делается только если
токена **нет** (`if (!cached)`). Когда JWT протухает по сроку, страницы (`Dashboard`, `Configs`, `Nodes`…)
получают 401 и просто показывают «Ошибка загрузки» — без очистки токена и без авто-реавторизации.
Чинится только полной перезагрузкой Mini App.

### Текущий код
```45:52:frontend/src/tg-mini/context/TgAuthContext.tsx
    const cached = getTgToken()
    if (!cached) {
      const auth = await tgAuth(tg.initData)
      setTgToken(auth.access_token)
    }
    await loadSettings()
```
В `tgFetch` нет глобальной реакции на 401:
```40:57:frontend/src/tg-mini/api.ts
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    ...
    throw new ApiError(detail, response.status)
  }
```

### Предлагаемая правка
В `tgFetch` при `response.status === 401`: очистить токен (`clearTgToken()`) и попробовать одну авто-реавторизацию
через `tg.initData`, затем повторить запрос; при повторном 401 — пробросить ошибку и перевести контекст в `error`.

---

## 3. Важно: наивный UTC timestamp → неверное локальное время

### Симптом
Бэкенд формирует время как `datetime.utcnow().isoformat()` — **без** таймзоны и без суффикса `Z`.
Фронтенд делает `new Date(value).toLocaleString()`, и JS трактует строку без TZ как **локальное** время.
Итог: «Обновлено» на дашборде (и `last_seen_at`/«Контакт» на узлах, если время naive) смещено на величину
часового пояса пользователя.

### Текущий код
```387:387:backend/app/routers/tg_mini.py
        "timestamp": datetime.utcnow().isoformat(),
```
```128:128:frontend/src/tg-mini/pages/Dashboard.tsx
        <p className="text-xs text-muted-foreground">Обновлено: {new Date(data.timestamp).toLocaleString()}</p>
```

### Предлагаемая правка
На бэке отдавать TZ-aware ISO (`datetime.now(timezone.utc).isoformat()`, даёт `+00:00`) — тогда `new Date`
корректно сдвинет в локальное. Либо на фронте явно интерпретировать как UTC.

---

## 4. Важно: QR-ссылка одноразовая, но сразу «сжигается» и QR не показывается

### Симптом
`handleQrLink` создаёт одноразовую ссылку (`max_downloads`), копирует её в буфер **и тут же** открывает
через `openLink`. Открытие на том же устройстве тратит единственную загрузку — скопированная ссылка
становится бесполезной. Плюс кнопка называется «QR-ссылка», но QR-код нигде не рендерится.
И `navigator.clipboard.writeText` в in-app браузере Telegram часто недоступен/кидает исключение — тогда
показывается «Ошибка создания ссылки», хотя ссылка уже создана.

### Текущий код
```84:98:frontend/src/tg-mini/pages/Configs.tsx
  const handleQrLink = async () => {
    ...
      const link = await getTgQrLink(activeConfig.id, selectedPath)
      await navigator.clipboard.writeText(link.url)
      setMessage('Ссылка скопирована в буфер обмена')
      window.Telegram?.WebApp.openLink(link.url)
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Ошибка создания ссылки')
    }
```

### Предлагаемая правка
Определиться с одним действием: либо открыть ссылку (без копирования), либо показать сам QR-код в диалоге
(одноразовый токен сканируют на другом устройстве). Копирование делать через `try/catch` отдельно, чтобы его
сбой не маскировался под «ошибку создания ссылки».

---

## 5. Важно: `/warper` и `/cidr` не защищены `isAdmin` на фронте

### Симптом
В `App.tsx` маршруты `nodes/warper/cidr` зарегистрированы всегда. `Nodes.tsx` корректно редиректит не-админа
(`<Navigate to="/" replace />`), а `Warper.tsx` и `Cidr.tsx` такой проверки не делают — они просто дёргают
admin-only API и показывают 403-ошибку. Поведение несогласованное (хотя вкладки и скрыты, прямой hash-переход
открывает экран с ошибкой вместо редиректа).

### Текущий код
```16:24:frontend/src/tg-mini/App.tsx
          <Route element={<MiniShell />}>
            <Route index element={<Dashboard />} />
            <Route path="configs" element={<Configs />} />
            <Route path="nodes" element={<Nodes />} />
            <Route path="warper" element={<Warper />} />
            <Route path="cidr" element={<Cidr />} />
```
`Warper.tsx` и `Cidr.tsx` не импортируют `useTgAuth` и не имеют guard.

### Предлагаемая правка
Добавить в `Warper.tsx`/`Cidr.tsx` тот же guard, что в `Nodes.tsx` (`if (!isAdmin) return <Navigate to="/" replace />`),
либо завернуть admin-маршруты в общий `RequireAdmin`-роут.

---

## 6. Важно: `total_configs` на дашборде ≠ списку «Конфиги» для админа

### Симптом
На дашборде число конфигов всегда считается **только по своему** `owner_id` — даже для админа.
А на странице «Конфиги» админ видит **все** конфиги узла. Для админа цифра на карточке «Конфигов» занижена
и не совпадает с реальным списком.

### Текущий код
```367:371:backend/app/routers/tg_mini.py
    configs = (
        db.query(VpnConfig)
        .filter(VpnConfig.node_id == node.id, VpnConfig.owner_id == current_user.id)
        .count()
    )
```
против
```391:397:backend/app/routers/tg_mini.py
def mini_configs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    node = get_active_node(db)
    query = db.query(VpnConfig).filter(VpnConfig.node_id == node.id)
    if current_user.role.value != "admin":
        query = query.filter(VpnConfig.owner_id == current_user.id)
```

### Предлагаемая правка
Согласовать логику: для админа считать все конфиги узла (та же ветка `if role != admin`), для остальных — свои.

---

## 7. Важно: в статус WARP вываливается весь сырой dict + цвет всегда зелёный

### Симптом
На экране «WARP» вместо короткого статуса показывается **весь сырой словарь** ответа агента одной
зелёной простынёй (см. скриншот):
`Статус: {'version': '1.4.2', 'remote_version': '1.4.2', 'update_available': False, ... 'traffic_today': '↑ 0 B ↓ 0 B'}`.

Причина на бэке: `status_text` берётся как `raw_status.get("status") or raw_status.get("mode") or str(raw_status)`.
В реальном ответе агента **нет** ключа `status` и нет верхнеуровневого `mode` (есть `outbound_mode`, `singbox.enabled`
и т.п.), поэтому срабатывает ветка `str(raw_status)` — и в поле уходит весь dict.

Вдобавок на фронте блок статуса всегда имеет класс `is-success` (зелёный), даже если WARP выключен/сломан:
на скриншоте `vpn_warp: False`, `warp_rules_active: False`, `traffic_today: 0 B`, но плашка зелёная.

### Текущий код
```17:22:backend/app/services/tg_mini_status.py
    if isinstance(raw_status, dict):
        status_text = raw_status.get("status") or raw_status.get("mode") or str(raw_status)
        status_data = raw_status
    else:
        status_text = str(raw_status)
        status_data = {"status": status_text}
```
```53:53:frontend/src/tg-mini/pages/Warper.tsx
        <div className="tg-mini-status is-success mt-3">Статус: {data?.status ?? '—'}</div>
```

### Предлагаемая правка
1. На бэке формировать человекочитаемый статус из реальных полей (например, `outbound_mode`, `singbox.running`,
   `vpn_warp`/`antizapret_warp`, `update_available`), а не `str(raw_status)`. Сырой словарь уже отдаётся
   отдельным полем `raw` — его и использовать для подробностей.
2. На фронте показывать ключевые поля списком (Режим, sing-box, WARP вкл/выкл, Трафик сегодня, Версия/обновление),
   а класс плашки выбирать по фактическому состоянию (success/warning/error), а не хардкодить `is-success`.

---

## 8. Мелочь: CIDR — метка «Последнее обновление» показывает статус, а не дату

### Симптом
Под подписью «Последнее обновление» выводится `last_refresh_status` (строка вида `success`/`failed`),
а фактическое время завершения — под «Завершено» (`last_refresh_finished`). Подписи вводят в заблуждение.

### Текущий код
```56:63:frontend/src/tg-mini/pages/Cidr.tsx
          <div>
            <dt>Последнее обновление</dt>
            <dd>{data?.last_refresh_status ?? '—'}</dd>
          </div>
          <div>
            <dt>Завершено</dt>
            <dd>{data?.last_refresh_finished ?? '—'}</dd>
          </div>
```

### Предлагаемая правка
Переименовать первую метку в «Статус обновления», вторую оставить «Завершено» (дата).

---

## 9. Мелочь: несогласованная обработка ошибок

### Симптом
`Warper.tsx` и `Cidr.tsx` используют `err instanceof Error`, тогда как остальные страницы — `err instanceof ApiError`.
Сообщения формируются по-разному; единообразие потеряно.

### Текущий код
```17:18:frontend/src/tg-mini/pages/Warper.tsx
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки')
```

### Предлагаемая правка
Привести к единому стилю — использовать `ApiError`, как в `Dashboard.tsx`/`Configs.tsx`/`Nodes.tsx`.

---

## 10. Мелочь: коллизия имён `TelegramSettings`

### Симптом
В `pages/TelegramSettings.tsx` одновременно импортируется **тип** `TelegramSettings` из `@/types` и объявляется
**компонент** с тем же именем. Сейчас работает (типы и значения в TS — разные пространства имён), но это хрупко
и путает при чтении.

### Текущий код
```13:15:frontend/src/tg-mini/pages/TelegramSettings.tsx
import type { TelegramSettings } from '@/types'
...
export default function TelegramSettings() {
```

### Предлагаемая правка
Переименовать тип при импорте (`import type { TelegramSettings as TelegramSettingsDto }`) или назвать
компонент `TelegramSettingsCard`.

---

## 11. Мелочь: `error` не сбрасывается в начале обработчиков

### Симптом
В `Settings.tsx` (`handleSaveNotify`, `handleTestNotify`) и `TelegramSettings.tsx` (`handleTest`) сбрасывается
`message`, но не `error`. После прошлой ошибки и нового успеха старый красный текст ошибки остаётся на экране
рядом с зелёным сообщением об успехе.

### Текущий код
```52:57:frontend/src/tg-mini/pages/Settings.tsx
  const handleTestNotify = async () => {
    setTesting(true)
    setMessage(null)
    try {
      const result = await testTgAdminNotify()
      setMessage(result.message)
```

### Предлагаемая правка
В начале каждого обработчика добавить `setError(null)` (как уже сделано в `handleSave` у `TelegramSettings`).

---

## 12. Мелочь: `replaceNode` дважды вызывает `setNodes`

### Симптом
При активации узла сначала `setNodes` мапит обновлённый узел, затем сразу ещё раз мапит все узлы, проставляя
`is_active`. Первый вызов избыточен.

### Текущий код
```72:83:frontend/src/tg-mini/pages/Nodes.tsx
  const replaceNode = (updated: TgMiniNode) => {
    setNodes((current) => current.map((node) => (node.id === updated.id ? updated : node)))
    if (updated.is_active) {
      setActiveNodeId(updated.id)
      setNodes((current) =>
        current.map((node) => ({ ...node, is_active: node.id === updated.id })),
      )
    }
  }
```

### Предлагаемая правка
Объединить в один `setNodes`: смержить `updated` и пересчитать `is_active` за один проход.

---

## 13. Мелочь: `auth_max_age` молча клампится, поле без валидации

### Симптом
Бэк ограничивает значение диапазоном `max(30, min(max_age, 86400))`, но UI этого не показывает: введёшь 100000 —
сохранится 86400 без предупреждения. Поле «Max age» — обычный текст, без `type=number`/min/max.

### Текущий код
```87:88:backend/app/routers/tg_mini.py
    if abs(int(time.time()) - int(auth_date_raw)) > max(30, min(max_age, 86400)):
```
```116:123:frontend/src/tg-mini/pages/TelegramSettings.tsx
            <Label htmlFor="auth-max-age">Max age (сек)</Label>
            <Input id="auth-max-age" value={authMaxAge} onChange={(e) => setAuthMaxAge(e.target.value)} />
```

### Предлагаемая правка
Сделать поле `type="number"` с `min=30 max=86400` и подсказкой о допустимом диапазоне.

---

## 14. Мелочь: диалог конфига при `files.length === 0` пустой

### Симптом
Если файлы загрузились без ошибки, но список пуст, в диалоге не показывается ни `select`, ни абзац для одного
файла, ни сообщение «нет файлов» — только заголовок и неактивные кнопки (`selectedPath` пустой → всё disabled).

### Текущий код
```142:159:frontend/src/tg-mini/pages/Configs.tsx
              {files.length > 1 && ( <select ... /> )}
              {files.length === 1 && ( <p ...>{...}</p> )}
              {message && <p className="text-sm">{message}</p>}
```

### Предлагаемая правка
Добавить ветку `files.length === 0 && <p>Файлы не найдены</p>`.

---

## 15. Наблюдение: JWT в `localStorage`

### Симптом
Токен хранится в `localStorage` (`TOKEN_KEY = 'tg_token'`) — при XSS он легко угоняется и переживает
закрытие приложения. Для Mini App это распространённый компромисс, но стоит зафиксировать решение осознанно.

### Текущий код
```18:30:frontend/src/tg-mini/api.ts
const TOKEN_KEY = 'tg_token'
export function setTgToken(token: string): void { localStorage.setItem(TOKEN_KEY, token) }
```

### Предлагаемая правка
Как минимум — связать с пунктом #2 (очистка/ротация по 401). Опционально — рассмотреть хранение токена только
в памяти (re-auth через `initData` при каждом запуске Mini App дешёвый).

---

## Дополнительно (косметика, на ваше усмотрение)

- `Dashboard.tsx`: в строке WireGuard суммарный трафик (`transfer_rx + transfer_tx`) красится в `text-emerald-500`,
  как будто это индикатор «online». Без подписи это вводит в заблуждение — стоит либо подписать «трафик», либо
  не использовать «успешный» зелёный цвет для нейтрального числа.
- `MiniShell.tsx`: для статуса `no-telegram` нет кнопки «Повторить» (есть только для `error`). Если приложение
  открыли вне Telegram — это ок, но если `initData` не успел инициализироваться, перезапуск возможен только вручную.
