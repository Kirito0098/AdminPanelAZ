# Безопасность AdminPanelAZ

Рекомендации для развёртывания панели в сети (LAN / интернет).

## Перед публикацией

1. **Режим production** — в `backend/.env`:
   ```env
   APP_ENV=production
   SECRET_KEY=<openssl rand -hex 32>
   DEFAULT_ADMIN_PASSWORD=<надёжный пароль, не admin>
   BEHIND_NGINX=true
   ENFORCE_HTTPS=true
   CORS_ORIGINS=https://panel.example.com
   REFRESH_TOKEN_COOKIE_SECURE=true
   ```
2. **Node agent** — в `backend/node_agent.env`:
   ```env
   NODE_AGENT_MODE=prod
   NODE_AGENT_API_KEY=<openssl rand -hex 32>
   NODE_AGENT_ALLOWED_IPS=10.0.0.5/32
   ```
   Ограничьте доступ к порту агента (9100) firewall: только IP панели управления.
3. **Смените пароль** `admin/admin` при первом входе (или задайте `DEFAULT_ADMIN_PASSWORD` до первого запуска).
4. **Nginx + HTTPS** — `./scripts/nginx-setup.sh` (шаблон уже добавляет HSTS и базовые заголовки).
5. **2FA** — включите в Настройки → Безопасность для учётной записи администратора.

## Переменные окружения (панель)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_ENV` | `development` | `production` включает проверку секретов и усиленную политику паролей |
| `SECRET_KEY` | *(слабый)* | JWT и шифрование API-ключей узлов; **обязателен** в production (≥32 символа) |
| `REQUIRE_PRODUCTION_SECRETS` | `true` | Отказ запуска при слабых секретах в production |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | TTL access JWT (короткий) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | TTL refresh-токена (httpOnly cookie) |
| `REFRESH_TOKEN_COOKIE_SECURE` | `false` | Cookie только по HTTPS (включите в production) |
| `REFRESH_TOKEN_COOKIE_SAMESITE` | `lax` | SameSite для refresh cookie |
| `ENFORCE_PASSWORD_POLICY` | `false` | Принудительная политика паролей (буквы+цифры, min длина) |
| `MIN_PASSWORD_LENGTH` | `8` | Минимальная длина пароля (в production / при `ENFORCE_PASSWORD_POLICY`) |
| `AUTH_RATE_LIMIT_ENABLED` | `true` | Лимит попыток входа по IP |
| `AUTH_RATE_LIMIT_MAX_ATTEMPTS` | `10` | Попыток за окно |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `300` | Окно лимита (сек) |
| `AUTH_RATE_LIMIT_BACKEND` | `memory` | `memory` или `redis` (для нескольких uvicorn workers) |
| `REDIS_URL` | *(пусто)* | URL Redis при `AUTH_RATE_LIMIT_BACKEND=redis` |
| `API_RATE_LIMIT_ENABLED` | `true` | Глобальный лимит запросов к `/api/*` по IP |
| `API_RATE_LIMIT_MAX_REQUESTS` | `120` | Запросов за окно на IP |
| `API_RATE_LIMIT_WINDOW_SECONDS` | `60` | Окно глобального лимита (сек) |
| `API_RATE_LIMIT_BACKEND` | `memory` | `memory` или `redis` (для нескольких uvicorn workers) |
| `SECURITY_HEADERS_ENABLED` | `true` | X-Frame-Options, CSP, HSTS (за nginx) |
| `ENFORCE_HTTPS` | `false` | Редирект HTTP→HTTPS (если `X-Forwarded-Proto` не https) |
| `HSTS_MAX_AGE` | `31536000` | Заголовок Strict-Transport-Security |
| `CONTENT_SECURITY_POLICY` | *(см. config.py)* | CSP для SPA; при необходимости ослабьте для dev |
| `AUDIT_LOG_ENABLED` | `true` | Журнал чувствительных действий (`/api/logs/actions`) |
| `CORS_ORIGINS` | localhost | Список origin через запятую |
| `BEHIND_NGINX` | `false` | Доверять `X-Forwarded-For` от `TRUSTED_PROXY_IPS` |
| `TRUSTED_PROXY_IPS` | `127.0.0.1,::1` | IP reverse proxy |
| `NODE_AGENT_MTLS_ENABLED` | `false` | **Deprecated** — режим mTLS задаётся per-node (`nodes.mtls_enabled` в БД). Глобальный флаг оставлен только для legacy backfill при миграции |
| `NODE_AGENT_MTLS_CA_CERT` | `/etc/adminpanelaz/mtls/ca.crt` | CA для проверки сертификата агента (создаётся панелью при первом включении mTLS) |
| `NODE_AGENT_MTLS_CLIENT_CERT` | `/etc/adminpanelaz/mtls/panel.crt` | Клиентский сертификат панели |
| `NODE_AGENT_MTLS_CLIENT_KEY` | `/etc/adminpanelaz/mtls/panel.key` | Ключ клиентского сертификата |
| `NODE_API_KEY_ROTATION_DAYS` | `0` | Автоматическая ротация ключей узлов (0 = выкл) |
| `NODE_API_KEY_ROTATION_CHECK_HOURS` | `24` | Интервал проверки расписания ротации |

## Переменные окружения (node agent)

| Переменная | Описание |
|------------|----------|
| `NODE_AGENT_API_KEY` | Секрет в заголовке `X-Node-Key`; ≥24 символа в prod |
| `NODE_AGENT_ALLOWED_IPS` | Опциональный allowlist IP/CIDR панели |
| `NODE_AGENT_MODE` | `prod` — строгая проверка API-ключа при старте |
| `NODE_AGENT_MTLS_ENABLED` | `true` — TLS с проверкой клиентского сертификата панели |
| `NODE_AGENT_MTLS_SERVER_CERT` | Сертификат сервера агента |
| `NODE_AGENT_MTLS_SERVER_KEY` | Ключ сервера агента |
| `NODE_AGENT_MTLS_CA_CERT` | CA для проверки клиента (панели) |
| `NODE_AGENT_ENV_FILE` | Путь к env-файлу для сохранения ключа при ротации |

## Уже реализовано в панели

- JWT access + refresh-токены (httpOnly cookie, ротация при refresh)
- TOTP 2FA для администраторов (настройка, резервные коды)
- Rate limit auth: in-memory или Redis (fallback на memory)
- Global API rate limit: per-IP sliding window на `/api/*` (исключения: health, ip-blocked); public route download — 30/min
- robots.txt и security.txt (RFC 9116), X-Robots-Tag noindex для чувствительных путей
- Per-node mTLS панель ↔ node agent (включение из UI «Узлы» → «Включить mTLS»)
- Ротация `NODE_AGENT_API_KEY` (вручную на странице Узлы, автоматически по расписанию)
- JWT (bcrypt пароли, роли admin/user/viewer)
- IP-ограничение и блокировка сканеров (настройки → Безопасность)
- Капча после неудачных попыток входа
- Аудит: вход, смена пароля, 2FA, пользователи, узлы, бэкапы, настройки безопасности
- Шифрование API-ключей узлов (Fernet от `SECRET_KEY`)
- Публичная QR-загрузка: одноразовые токены, TTL, опциональный PIN

## Frontend

- Access-токен в `localStorage`; refresh — httpOnly cookie (`credentials: 'include'`)
- Автообновление access-токена перед истечением и при 401
- Telegram OAuth: токен передаётся в URL hash (`#token=`), не в query string

## mTLS: per-node включение из панели

По умолчанию панель и node agent работают по **HTTP** + `X-Node-Key`. Для каждого удалённого узла mTLS включается отдельно:

1. Добавьте узел на странице **«Узлы»** (IP, порт, API-ключ) — соединение по HTTP.
2. Убедитесь, что health **online**.
3. В меню узла выберите **«Включить mTLS»** — панель сгенерирует CA (один раз), клиентский сертификат панели и серверный сертификат узла, доставит bundle на node agent по HTTP (bootstrap) и перезапустит агент.
4. После перезапуска панель проверяет health по **HTTPS** с клиентским сертификатом.

Смешанный режим поддерживается: узел 1 на mTLS, узел 2 на HTTP — оба работают одновременно.

| Настройка | Назначение |
|-----------|------------|
| `nodes.mtls_enabled` (БД) | HTTP или HTTPS для **конкретного** узла |
| `NODE_AGENT_MTLS_*_CERT/KEY` в `.env` панели | Пути к CA и клиентскому сертификату панели (после первого включения mTLS) |
| `NODE_AGENT_MTLS_ENABLED` в `.env` | **Deprecated** — только legacy backfill при миграции |

Сертификаты на панели: `/etc/adminpanelaz/mtls/` (`ca.crt`, `panel.crt`, `panel.key`, `nodes/{id}/agent.crt`).

### Ручная генерация (legacy / отладка)

> Ручная настройка через `scripts/generate-mtls-certs.sh` устарела — используйте кнопку в UI.

```bash
sudo chmod +x scripts/generate-mtls-certs.sh
sudo ./scripts/generate-mtls-certs.sh /etc/adminpanelaz/mtls
```

Затем включите переменные в `backend/.env` и `backend/node_agent.env` (см. вывод скрипта) и перезапустите панель и node agent. Для новых установок предпочтительнее per-node включение из панели.

## Rate limit при нескольких uvicorn workers

По умолчанию лимиты (**auth** и **global API**) хранят счётчики **в памяти процесса** (`*_RATE_LIMIT_BACKEND=memory`). Это нормально, если uvicorn запущен с **одним worker** (`UVICORN_WORKERS=1`).

**Workers** — это отдельные процессы uvicorn, которые параллельно принимают HTTP-запросы. При `--workers N > 1` каждый процесс имеет **свой** in-memory счётчик. Злоумышленник может обойти лимит, отправляя запросы так, чтобы они попадали на разные workers (round-robin балансировка на уровне ОС).

**Redis** — общее хранилище счётчиков: все workers читают и пишут в один Redis, поэтому лимит соблюдается суммарно по IP.

| Ситуация | Что использовать |
|----------|------------------|
| 1 worker (по умолчанию) | `AUTH_RATE_LIMIT_BACKEND=memory`, `API_RATE_LIMIT_BACKEND=memory` — достаточно |
| workers > 1 (systemd / prod) | `AUTH_RATE_LIMIT_BACKEND=redis`, `API_RATE_LIMIT_BACKEND=redis` и `REDIS_URL=redis://127.0.0.1:6379/0` |

Пример для production с несколькими workers в `backend/.env`:

```env
UVICORN_WORKERS=4
AUTH_RATE_LIMIT_BACKEND=redis
API_RATE_LIMIT_BACKEND=redis
REDIS_URL=redis://127.0.0.1:6379/0
```

Мастер `install.sh` подскажет это при выборе workers > 1.

## Рекомендации по развёртыванию

1. Панель слушает только `127.0.0.1:8000`, наружу — **только Nginx** (HTTPS-порт по выбору, по умолчанию 443).
2. Firewall: закрыть порты backend и node agent с интернета; открыть HTTPS и HTTP для ACME (порты задаются в мастере установки).
3. Регулярные бэкапы БД (`/var/backups/adminpanelaz`).
4. Включите IP allowlist в настройках безопасности для админ-доступа.
5. При `UVICORN_WORKERS > 1` используйте `AUTH_RATE_LIMIT_BACKEND=redis` и `API_RATE_LIMIT_BACKEND=redis` (см. раздел выше).
