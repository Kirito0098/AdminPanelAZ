# Локальная GeoIP (MaxMind GeoLite2)

NOC и мониторинг показывают город и провайдера клиента по IP. По умолчанию используется внешний сервис **ip-api.com**. Если загрузить локальные MMDB-файлы MaxMind, панель переключается на **офлайн lookup** и не зависит от ip-api.

## Зачем это нужно

- NOC стабильно показывает геолокацию при блокировке или недоступности ip-api.com
- Меньше внешних HTTP-запросов при большом числе подключений
- ISP (провайдер) подтягивается из GeoLite2-ASN, если файл ASN тоже загружен

## Требуемые файлы

Положите базы в каталог **`data/geoip/`** относительно корня репозитория (или `/opt/AdminPanelAZ/data/geoip/` на сервере):

| Файл | Назначение |
|------|------------|
| `GeoLite2-City.mmdb` | Город и страна (**обязательно** для offline-режима) |
| `GeoLite2-ASN.mmdb` | Провайдер / AS (**рекомендуется**) |

Пути можно переопределить через `.env` (`GEOIP_CITY_MMDB_PATH`, `GEOIP_ASN_MMDB_PATH`), см. `backend/app/config.py`.

## Скачивание GeoLite2

1. Зарегистрируйтесь на [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) (бесплатный аккаунт).
2. В личном кабинете создайте **License Key**.
3. Скачайте архивы **GeoLite2 City** и **GeoLite2 ASN** (формат **GeoIP2 / GeoLite2 Binary (.mmdb)**).
4. Распакуйте и переименуйте файлы:

```bash
sudo mkdir -p /opt/AdminPanelAZ/data/geoip
sudo cp GeoLite2-City_*/GeoLite2-City.mmdb /opt/AdminPanelAZ/data/geoip/
sudo cp GeoLite2-ASN_*/GeoLite2-ASN.mmdb /opt/AdminPanelAZ/data/geoip/
sudo chown -R "$(stat -c '%U' /opt/AdminPanelAZ)":"$(stat -c '%G' /opt/AdminPanelAZ)" /opt/AdminPanelAZ/data/geoip
```

5. Перезапустите панель:

```bash
sudo systemctl restart adminpanelaz
```

## Проверка в UI

**Настройки → Обслуживание** — блок **GeoIP**:

- **loaded** — локальная City MMDB загружена, NOC не обращается к ip-api
- **fallback ip-api** — файлы отсутствуют или City MMDB не прочитана; используется ip-api.com

Там же отображаются пути к файлам и наличие City/ASN на диске.

## Обновление баз

MaxMind публикует обновления GeoLite2 регулярно. Замените `.mmdb` в `data/geoip/` и перезапустите панель. Автообновление в панели не реализовано — настройте cron на сервере при необходимости.

## Поведение lookup

- Приватные и служебные IP (10.x, loopback и т.д.) не геолокируются.
- Если City MMDB загружена, batch lookup в NOC **не вызывает** ip-api.
- Если City MMDB нет — fallback на ip-api (как раньше).

Реализация: `backend/app/services/geoip_local.py`, `backend/app/services/ip_geo.py`.
