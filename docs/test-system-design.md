# Formatting test system — design

A lightweight "golden test" suite for the formatter config: each test pins a
problematic snippet (BEFORE) against the output it *should* produce (AFTER).
Running the suite against the current config shows, IDE-style, what the config
already achieves and what it doesn't — the same shape as the LOGS-5799 problem
table (problem → desired result → ✅/🔴/🙈).

## Test model

```jsonc
{
  "id": "uuid",
  "name": "1. Brace after class definition",
  "language": "cpp",        // "cpp" | "python"
  "input": "...",           // BEFORE — the problematic fragment
  "expected": "...",        // AFTER — the desired formatted output
  "muted": false,           // conscious compromise / revisit later
  "note": "",               // optional context (e.g. why muted, ticket link)
  "created_at": "ISO-8601"
}
```

`expected` is **author-written desired output**, not a snapshot of what the
formatter currently emits. That is what makes a red test meaningful: it means
"the config does not yet format this the way we want."

## Statuses

A run formats `input` with the current config and a single chosen clang-format
version, then compares with `expected`:

| Condition                         | status | colour |
|-----------------------------------|--------|--------|
| `actual == expected`              | pass   | green  |
| `actual != expected`, not muted   | fail   | red    |
| `muted` (regardless of pass/fail) | muted  | yellow |

Muted tests never count toward the red failure total — they are known
compromises kept visible. Comparison is exact except the final trailing newline
is normalised on both sides.

## Storage

JSON files, one per test, under `backend/tests/<language>/<id>.json`, committed
to git so the baseline suite is version-controlled. The directory is
bind-mounted into the container (`./backend/tests:/app/tests`), so tests added
through the UI are written straight back into the repo and can be committed.

## Backend API

| Method | Path                     | Purpose                                   |
|--------|--------------------------|-------------------------------------------|
| GET    | `/api/tests`             | list all tests (metadata)                 |
| POST   | `/api/tests`             | create a test                             |
| GET    | `/api/tests/{id}`        | read one                                  |
| PUT    | `/api/tests/{id}`        | update (incl. toggling `muted`)           |
| DELETE | `/api/tests/{id}`        | delete                                    |
| POST   | `/api/tests/run`         | run all; body `{language?, clangVersion?}`|
| POST   | `/api/tests/{id}/run`    | run a single test                         |

`run` returns per-test results (`status`, `actual`, `expected`, `error?`) plus a
summary `{ total, passed, failed, muted }`. One clang-format version applies to
the whole run (selected in the UI, defaulting to the built-in version).

## Frontend (Gravity UI)

A header toggle switches between **Playground** (the existing formatter) and
**Tests**. The Tests view:

- a **Run all** button + language filter + clang-format version for the run;
- a summary line (passed / failed / muted) with coloured counts;
- a list of tests with a coloured status dot (green/red/yellow), expandable to
  three panes — BEFORE / desired AFTER / actual — with the diff highlight reused
  from the playground;
- a **mute** toggle per test;
- an **add test** form (BEFORE → AFTER), including "grab the current playground
  input" as a shortcut.

## Decisions (confirmed)

- Storage: per-test JSON files in git, bind-mounted. ✅
- Version: one clang-format version per run (not per-test). ✅
- UI: header Playground/Tests toggle (not a separate route). ✅
