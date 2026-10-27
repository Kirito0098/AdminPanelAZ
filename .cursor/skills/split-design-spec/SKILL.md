---
name: split-design-spec
description: >
  Splits a monolithic design doc under docs/superpowers/specs/ into a dated
  folder of section files plus README index, and labels each piece as already
  shipped (reuse), to-build, partial, or separate-delivery after checking the
  codebase. Use when the user asks to «разбить спек», «разложить дизайн по
  папкам», «split design spec», or to prepare a large
  docs/superpowers/specs/*-design.md for staged planning.
---

# Split design spec into a folder

Turn one large `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` into a
folder the user can plan and implement stage-by-stage. Do **not** invent new
design — only redistribute and label against the current codebase.

## When

- User names a design file (or «этот спек») and asks to split / разложить / разбить.
- Spec is hard to plan as one unit (many stages, reuse of existing modules).

## Output layout

```text
docs/superpowers/specs/YYYY-MM-DD-<topic>/
  README.md                 # index, delivery stages, status legend
  ALREADY-SHIPPED.md        # what exists in code today (verified)
  00-overview.md            # problem, goal, decisions, non-goals
  NN-<slug>.md              # one file per top-level ## section (or stage)
docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md
  → short stub pointing at the folder (keep the old path as a redirect)
```

Rules:

1. Folder name = basename without `-design.md` (e.g. `2026-10-18-user-provisioning`).
2. Keep the original date in the folder name; do not invent a new date.
3. One file per `##` section **or** per delivery stage — whichever the user can plan from. Prefer stages when the doc has a «Delivery stages» section; put shared pieces (data model, decisions) in `00-overview.md` + numbered design files.
4. Each part file starts with YAML frontmatter (see below).
5. Do not delete content. Every paragraph from the monolith must appear in exactly one part file (except the stub).
6. After a successful split, replace the monolith with a stub (template below). Keep a copy as `YYYY-MM-DD-<topic>/_monolith.md` only if the user asks; default is stub + parts, no monolith duplicate.

## Frontmatter on every part file

```yaml
---
title: <short title>
stage: 1 | 2 | 3 | 4 | shared | separate
status: reuse | partial | to-build | separate-delivery
depends_on: []          # other part filenames in this folder
target_release: "2.26.6"  # from the design header, or empty
---
```

Status meanings:

| Status | Meaning |
|--------|---------|
| `reuse` | Already in the repo; this stage only wires/extends it. List concrete paths in the body. |
| `partial` | Core exists; listed gaps are still to-build. |
| `to-build` | Not implemented; this is new work. |
| `separate-delivery` | Out of the main stage train (e.g. install.sh / scenario presets). |

## README.md required sections

1. **Meta** — date, target release, branch, link to stub path.
2. **Status legend** — the four statuses above.
3. **Parts** — table: file | stage | status | one-line purpose.
4. **Delivery stages** — from the design, with which files belong to each stage.
5. **How to plan next** — «pick one stage folder/file → writing-plans»; do not implement from README alone.

## ALREADY-SHIPPED.md

Verify against the codebase (prefer codebase-memory graph `search_graph` / `get_file_outline`, else grep). Table columns:

| Capability | Where in code | Used by stages | Notes |
|------------|---------------|----------------|-------|

Only list items that **exist today**. Gaps go in the relevant part file under `### Gaps (to-build)`, not here.

If the design already has an «existing pieces» table, start from it, then confirm each row still resolves to a real symbol/file. Drop or fix stale rows.

## Stub template (replaces the monolith)

```markdown
# Design: <title>

> **Разложен по папкам:** [./YYYY-MM-DD-<topic>/](./YYYY-MM-DD-<topic>/)
>
> Читать с [README.md](./YYYY-MM-DD-<topic>/README.md). Что уже в коде —
> [ALREADY-SHIPPED.md](./YYYY-MM-DD-<topic>/ALREADY-SHIPPED.md).

Date: YYYY-MM-DD  
Target release: **X.Y.Z**  
Status: split — edit files inside the folder, not this stub.
```

## Workflow

Copy and track:

```text
Split progress:
- [ ] 1. Read monolith; list ## headings and Delivery stages
- [ ] 2. Confirm target release / date from header
- [ ] 3. Build ALREADY-SHIPPED.md (verify symbols in code)
- [ ] 4. Write 00-overview.md + part files with frontmatter
- [ ] 5. Write README.md index
- [ ] 6. Replace monolith with stub
- [ ] 7. Show user the folder tree and status summary; ask which stage to plan
```

### Mapping content → files

- Header + Problem + Goal + Decisions + Non-goals → `00-overview.md`
- Numbered design sections → `01-…`, `02-…` (slug from heading, ASCII, hyphens)
- Testing / Feedback gate / Delivery stages → either `99-testing-and-delivery.md` or fold Testing into README and keep Delivery stages only in README
- Cross-links inside the folder use relative paths (`[API](03-api.md)`)

### Status assignment (mandatory)

For each part file, set `status` after checking code:

1. If the section says «reuse X» / «already exists» → verify → `reuse` or `partial`.
2. If the section is new behaviour with no matching module → `to-build`.
3. If Delivery stages mark it «separate delivery» → `separate-delivery`.
4. Never mark `reuse` without a path or symbol that exists now.

## Project notes (AdminPanelAZ)

- Specs live under `docs/superpowers/` (gitignored in GitHub; synced to Gitea agent repo). Do not commit them to `origin`.
- Register nothing in GitHub CI. After creating this skill itself, add a row to `.cursor/rules/use-skills.mdc` if missing.
- Do not start `writing-plans` or implementation until the user picks a stage.

## Done when

- Folder exists with README + ALREADY-SHIPPED + parts covering 100% of monolith content.
- Monolith path is a stub.
- Chat reply shows the tree and a short status table; asks which stage to plan next.
