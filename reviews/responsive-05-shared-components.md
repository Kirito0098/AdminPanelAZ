# План 05: общие responsive-компоненты (опционально)

> **Приоритет:** после P0 страниц  
> **Цель:** убрать дублирование table/card паттерна

## Зачем

Сейчас каждая страница вручную делает:
```tsx
<div className="lg:hidden">{cards}</div>
<div className="hidden lg:block overflow-x-auto">{table}</div>
```

Это приводит к разным порогам (`md` / `lg` / `xl`) и пропущенным таблицам.

## Предлагаемые компоненты

| Компонент | Путь | Назначение |
|-----------|------|------------|
| `ResponsiveDataView` | `components/shared/ResponsiveDataView.tsx` | breakpoint + mobile/desktop slots |
| `ToolbarButton` | `components/shared/ToolbarButton.tsx` | icon + short/full label |
| `PageSectionHeader` | `components/shared/PageSectionHeader.tsx` | title + actions flex-wrap |
| `MobileSettingsSectionPicker` | `components/settings/...` | из Prompt 1 settings |

## API sketch — ResponsiveDataView

```tsx
<ResponsiveDataView
  breakpoint="lg"  // default lg
  mobile={<CardList />}
  desktop={<DataTable />}
/>
```

## Промпт — создать ResponsiveDataView

```
Прочитай reviews/responsive-05-shared-components.md.

Создай frontend/src/components/shared/ResponsiveDataView.tsx:
- props: breakpoint?: 'md' | 'lg' | 'xl' (default 'lg'), mobile: ReactNode, desktop: ReactNode
- рендерит mobile below breakpoint, desktop at/above
- используй matchMedia или Tailwind hidden/block classes

Мигрируй один пилот: MonitoringConnectionsList.tsx на ResponsiveDataView.
npm run build. Добавь краткий JSDoc.
```

## Промпт — миграция страниц на ResponsiveDataView

```
После создания ResponsiveDataView, мигрируй по одной странице:
1. TrafficPage main list
2. NodesPage
3. LogsPage action logs

По одному PR/промпту. Сохранить визуал идентичным.
```

## Статус: ⬜ Не начато
