# Settings Hub (упрощение навигации настроек)

**Дата:** 2026-09-12  
**Статус:** approved design  
**Ветка:** `feature/client-portal`  
**Подход:** Settings hub (вариант A) — без hover-flyout; клик «Настройки» → `/settings`

**Референсы (Lazyweb):**  
https://www.lazyweb.com/agentic-search/aa756b10-1bf8-48c5-ada3-4d331a46532c  
(Linear / Clay / CommandBar / Campsite / Midday / Coda — hub + secondary nav, не command-palette-only)

## Контекст

Левый сайдбар и hover-flyout `SettingsSidebarSection` дублируют длинный список разделов. Flyout на desktop тяжёлый (portal, позиционирование, delay close); на mobile — отдельный expand. Пользователь уже выбирает раздел дважды: в flyout и снова на странице через mobile picker / заголовок.

Маршруты уже есть: `/settings` и `/settings/:section` (`SettingsPage`). Сейчас пустой `/settings` **редиректит** на `defaultSection` (`personal` / первый доступный) — хаба нет.

## Цели

1. Один вход в настройки из основного меню: **Настройки** → хаб `/settings`.  
2. Убрать hover-flyout (и связанный portal/hover state).  
3. На хабе — поиск + группы разделов (как в `SettingsNav` / `getVisibleNavGroups`).  
4. На `/settings/:section` — sticky secondary nav слева + контент справа (desktop); mobile — существующий `MobileSettingsSectionPicker`.  
5. Deep-links и feature-gates не ломать.

## Не цели / вне скоупа

- Глобальный command palette (⌘K).  
- Упрощение остальных пунктов левого сайдбара (операции, конфиг, VPN-модули).  
- Переименование / слияние settings-секций.  
- Backend / API изменения.  
- Переделка внутреннего layout отдельных табов (Backup, FeatureToggles и т.д.).

## Решения (зафиксировано)

| Тема | Решение |
|------|---------|
| Общий UX | **A — Settings hub**, не palette-only и не «только свернуть flyout» |
| Клик «Настройки» | `NavLink` на `/settings`, **без** flyout |
| Источник групп | `SETTINGS_NAV_GROUPS` / `getVisibleNavGroups` + `SECTION_META` |
| Поиск | Фильтр по `label` + `description`; один паттерн на хабе и в secondary nav |
| Feature toggles | Как сейчас: скрывать недоступные items через `isSettingsTabEnabled` / `isEnabled` |
| Неадмин | В меню «Мой профиль» можно оставить `/settings/personal`; хаб при открытии `/settings` показывает только доступные (личное) или сразу ведёт на personal — предпочтительно **хаб с одним пунктом**, без лишнего редиректа с корня, если корень осмысленен |
| Restart баннер | Без изменений |

## UX

### Основной сайдбар

- Админ, группа «Система»: пункт **Настройки** с иконкой Settings → `/settings`.  
  Active: pathname starts with `/settings`.  
- Удалить использование hover-flyout / `createPortal` списка разделов из сайдбара.  
- Компонент `SettingsSidebarSection` либо упростить до одного `NavLink`, либо удалить и встроить ссылку в `Layout` рядом с остальными `NAV_GROUPS` items.  
- Неадмин: без изменений смысла — «Мой профиль» → `/settings/personal` (или `/settings`, если хаб однопунктовый; предпочтение: сохранить прямой deep-link на personal).

### Хаб `/settings` (нет `section` в URL)

- Заголовок: «Настройки» (+ NodeBadge как сейчас на странице настроек).  
- Описание: коротко, без отсылки к «боковому меню Система» для списка разделов (текст обновить).  
- Поле поиска (placeholder вроде «Найти раздел…»).  
- Ниже — группы (`getVisibleNavGroups`): заголовок группы + список ссылок на `/settings/:id` с иконкой, `label`, `description`.  
- Пустой фильтр: «Ничего не найдено» + кнопка/действие сброса запроса.  
- **Не** редиректить сразу на `defaultSection` при пустом `sectionParam` (меняет текущее поведение `Navigate`).

### Страница раздела `/settings/:section`

- Desktop (ширина ≥ lg, согласовать с существующим `lg:` / `1023px` breakpoint панели):  
  - слева sticky secondary nav: поиск + те же группы/items (компактнее, чем хаб);  
  - справа: заголовок секции (`SECTION_META`) + контент таба.  
- Mobile: secondary nav скрыт; остаётся `MobileSettingsSectionPicker` (+ опционально ссылка «Все настройки» → `/settings`).  
- Невалидный / недоступный `section`: redirect на `/settings` или на `defaultSection` — **предпочтительно `/settings`**, чтобы хаб объяснял доступные разделы.  
- Feature-gated deep-link: тот же redirect.

### Поиск (детали)

- Case-insensitive substring по `label` и `description` из nav item / `SECTION_META`.  
- Фильтр применяется **внутри** видимых (уже feature/role-filtered) items.  
- Состояние поиска: локальный `useState` на хабе и на section page (не в URL в v1).  
- Группа без совпадений после фильтра — не показывать заголовок группы.

## Архитектура / файлы

| Файл | Изменение |
|------|-----------|
| `SettingsSidebarSection.tsx` | Упростить до NavLink **или** удалить |
| `Layout.tsx` | Подключить пункт «Настройки» → `/settings`; убрать flyout wiring |
| `SettingsPage.tsx` | Ветка hub vs section; layout secondary nav; убрать auto-redirect с пустого `/settings` |
| `SettingsNav.tsx` | Источник правды групп; при необходимости экспорт хелперов фильтра |
| Новый компонент (напр. `SettingsHub.tsx` / `SettingsSecondaryNav.tsx`) | Рендер групп + поиск; переиспользование на хабе и в secondary |
| `MobileSettingsSectionPicker.tsx` | Минимальные правки при необходимости (ссылка на хаб) |
| `settingsLabels` / copy | Обновить description заголовка страницы |

Роутинг: существующие routes без новых backend paths.

## Feature gates

Без изменений контракта: `isSectionAvailable` / `getVisibleNavGroups` продолжают скрывать items. Хаб и secondary nav показывают только видимое. Тоггл `panel_ops` и прочие settings tabs — как после expand feature toggles.

## Тестирование

- Ручное: нет hover-flyout; `/settings` — хаб; клик раздела → контент; поиск фильтрует; сброс.  
- Deep-link `/settings/modules` и т.д. открывает таб.  
- Выключенный модуль: пункт скрыт; URL недоступной секции → `/settings`.  
- Mobile: picker работает; secondary nav не дублирует хаос.  
- Неадмин: доступ только к personal.  
- `tsc` / существующие frontend checks зелёные.

## Критерии готовности

1. В левом меню нет списка всех settings-разделов и нет hover-flyout.  
2. `/settings` — хаб с поиском и группами.  
3. `/settings/:section` — secondary nav (desktop) + контент; mobile picker сохранён.  
4. Deep-links и feature/role visibility работают.  
5. Нет регрессии загрузки табов (users/settings fetches по `activeSection`).  
6. `tsc` ок.

## Порядок реализации (высокоуровнево)

1. Общий UI: компонент списка групп + поиск.  
2. Хаб в `SettingsPage` при отсутствии section.  
3. Secondary nav на section page; mobile path.  
4. Заменить flyout в сайдбаре на NavLink `/settings`.  
5. Redirects для invalid/unavailable section → `/settings`.  
6. Copy, ручная проверка, changelog.
