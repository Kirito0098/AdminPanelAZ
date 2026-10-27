---
name: ponytail-review
description: >
  Code review focused exclusively on over-engineering. Finds what to delete:
  reinvented standard library, unneeded dependencies, speculative abstractions,
  dead flexibility, duplicated validation. One line per finding: location, what
  to cut, what replaces it. Use before committing a feature or refactor, when
  the user says "review for over-engineering", "what can we delete", "is this
  over-engineered", "simplify review", or invokes /ponytail-review. Complements
  correctness and security review; this one only hunts complexity.
source: https://github.com/DietrichGebert/ponytail (MIT), adapted for AdminPanelAZ
---

Review the diff for unnecessary complexity. One line per finding: location, what
to cut, what replaces it. The diff's best outcome is getting shorter.

Default scope: `git diff` of uncommitted changes, or the commits of the current
task on the `release/…` branch if the tree is clean. Read the touched code and its
callers before judging; a short diff you don't understand is not a finding.

## Format

`file:L<a>-<b>: <tag>: <what to cut>. <replacement>.`

Tags:

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does (browser, HTML input attrs, FastAPI/Pydantic validation). Name the feature.
- `reuse:` equivalent helper, util, or pattern already in this repo. Name the path.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `dup:` same rule enforced twice where one layer is enough (e.g. client-side bounds duplicating a Pydantic `Field(ge, le)` that already returns 422). Say which layer stays and what the UX cost is.
- `shrink:` same logic, fewer lines. Show the shorter form.

## Examples

✅ `api/foo.ts:L12-38: stdlib: 27-line date formatter. Intl.DateTimeFormat, 1 line.`

✅ `services/x.py:L18-29: reuse: _get_setting_int duplicates app_setting_store._get_setting + int(). Import the existing one.`

✅ `repo.py:L88: yagni: AbstractRepository with one implementation. Inline it until a second one exists.`

✅ `Form.tsx:L40-60: dup: bounds re-checked in JS; API already returns 422 with a message. Drop client check, show err.message (cost: error appears after request).`

❌ "This class might be more complex than necessary, have you considered…" — vague, no location, no replacement.

## Scoring

End with: `net: -<N> lines possible.`

If there is nothing to cut, say `Lean already. Ship.` and stop.

## Boundaries (this project)

- Scope is over-engineering only. Correctness, security, performance → `systematic-debugging` / `review-security`, not here.
- Never flag for deletion: tests of critical paths (list in `.cursor/rules/use-skills.mdc`), input validation at trust boundaries (API schemas, auth, node agent, webhooks), error handling that prevents data loss, accessibility attributes.
- Defensive checks on trusted internal values are findings (`dup:` or `delete:`): `getattr(model, "column", default)` on an existing ORM column, `isinstance` on our own return values, `?.`/`??` on non-optional TS fields, `except Exception: pass`. See `.cursor/rules/lean-code.mdc`.
- Things that look dead but aren't: middleware `dispatch`, Pydantic validators, SQLAlchemy relationships, monkeypatch seams used by tests, `__all__` re-exports.
- Code written in the current task: apply the findings yourself before saying "готово", then re-run the checks. Code that existed before the task: list only — the user decides what to cut.
