---
name: web-design-guidelines
description: "UI/a11y-чеклист по коду перед сдачей вёрстки."
metadata:
  author: vercel
  version: "1.0.0"
---

# Web Interface Guidelines

Review UI code against this checklist. It is the local copy of the Vercel Web Interface
Guidelines rules we actually enforce — no network fetch is needed. If the upstream list
changes, update this file deliberately.

## How to review

1. Read the files named by the user (or ask which files/pattern).
2. Check every item below against those files.
3. Report findings as terse `file:line — what breaks — how to fix` lines, worst first.
4. Skip items that do not apply; do not invent style preferences.

## Semantics and structure

- Native element over a div with handlers: `button`, `a href`, `label`, `dialog`.
- One `h1` per page, heading levels do not skip.
- Every input has a `<label>` or `aria-label`; placeholders are not labels.
- Lists are `ul`/`ol`, tables are `table` with `th` scope.
- Icons that carry meaning have `aria-label` or visible text.

## Keyboard and focus

- Everything clickable is reachable and operable by keyboard.
- Focus is visible (`:focus-visible`), never `outline: none` without a replacement.
- Focus order matches visual order; modal traps focus and restores it on close.
- `Esc` closes overlays; `Enter` submits the primary form action.
- Nested Radix menus/portals: check real clicks, not simulated ones.

## Navigation

- The current page or section is marked in markup (`aria-current="page"`), not only by color.
- URL reflects state: tabs, filters, pagination, open panel — back returns to the previous state.
- Navigation is `<a href>`/`<Link>` (Cmd/Ctrl+click, middle-click); `<button>` is for actions.
- Nav-heavy pages have a "skip to content" link; the sidebar is `<nav>` with a label when there is more than one.
- Mobile drawer: focus moves into it, `Esc` closes, focus returns to the trigger, body scroll is locked.
- Breadcrumbs only for 3+ levels; flat sections do not need them.
- Unsaved changes warn before navigation (`beforeunload` or router guard).

## Forms and errors

- Error text is tied to the field (`aria-describedby`), not only colored red.
- Server 422 messages are shown as returned; client does not re-derive limits.
- Disabled controls explain why; submit shows a pending state and blocks double submit.
- `autocomplete`, `type`, and `inputmode` match the data being entered.

## States

- Loading, empty, error, and partial states are designed, not left blank.
- Skeletons keep layout stable (no jump when data arrives).
- Destructive actions ask for confirmation and name the object.

## Visual and motion

- Contrast: text 4.5:1, large text and UI borders 3:1.
- Color is never the only signal — pair with text, icon, or position.
- `prefers-reduced-motion` disables non-essential animation.
- Tap targets at least 44×44 CSS px; spacing between adjacent targets.
- Long content truncates with `text-overflow` and keeps full value in a title/tooltip.

## Internationalization and text

- No hardcoded user-facing strings where the project uses a text source.
- Dates, times, and numbers go through the project timezone/locale helpers.
- Buttons say what happens (`Удалить ключ`), not `OK`/`Да`.

## Performance-adjacent UI rules

- Images have `width`/`height` or aspect-ratio; below-the-fold images are lazy.
- No layout thrash in render: measure in effects, not during render.
- Heavy widgets are code-split; charts do not block first paint.
