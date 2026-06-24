---
name: format-quorum-api
description: Manage the format-quorum backend over its open HTTP API — format C++/Python code, and create/edit/delete/run formatting test cases, manage clang-format versions, and read/write the .clang-format & ruff.toml configs. Use whenever the user asks to add, change, mute, run, or remove tests on format-quorum (the clang-format / ruff playground at fq.alchemmist.xyz), to format a snippet through it, or to tweak its formatter config. The API needs no auth.
allowed-tools: Bash, Read, Edit
---

# format-quorum API

`format-quorum` is a clang-format / ruff config test-bench. The FastAPI backend
exposes an **open, unauthenticated** HTTP API. Use it to manage tests and format
code on the user's behalf.

- **Prod:** `https://fq.alchemmist.xyz` (live service, behind Caddy)
- **Local dev:** `http://localhost:3000`
- **Interactive docs:** `<base>/docs` · OpenAPI: `<base>/openapi.json`

Pick the base with the `FQ_BASE` env var. **Default to prod** when the user asks
to change "the tests" (that is the live service); use local only when they say so
or are developing locally.

> ⚠️ **Prod tests are the source of truth and live in a docker named volume.**
> Changes you make via the prod API persist across deploys but are **not** mirrored
> back into git. If the user wants a change tracked in the repo, also update
> `scripts/seed_baseline_tests.py` (and reseed) — see "Keeping git in sync" below.

## The helper

`scripts/fq.py` (next to this file) wraps every endpoint and handles the fiddly
parts (computing `expected` for lock tests, JSON encoding, base-URL). Prefer it
over hand-rolled curl. It reads `FQ_BASE` from the env.

```bash
FQ_BASE=https://fq.alchemmist.xyz python3 .claude/skills/format-quorum-api/scripts/fq.py <cmd> ...
```

Commands: `list`, `get <id>`, `format`, `add`, `update <id>`, `delete <id>`,
`run`, `get-config <lang>`, `put-config <lang>`. Run any with `-h` for flags.

## Test data model

A test is BEFORE (`input`) → AFTER (`expected`). Stored fields:

| field | meaning |
|-------|---------|
| `id` | server-assigned (hex); used in URLs and `#<id>` deep links |
| `name` | human title |
| `language` | `cpp` or `python` |
| `input` | the BEFORE code |
| `expected` | the AFTER code the test asserts |
| `muted` | if true the test shows **yellow** regardless of pass/fail — an accepted compromise / unfixable item |
| `note` | provenance / rationale (link the ticket or PR) |

Status when run: **pass** (`format(input) == expected`), **fail**, or **muted**.

**Conceptual modes** (a seeding convention, not stored):
- **lock** — `expected = format(input)`. A green regression guard for an agreed
  style. `fq.py add --mode lock` computes `expected` for you.
- **guard** — like lock, but `input` is the old *bad* form; proves the current
  config no longer produces it. Also `expected = format(input)`.
- **want** — `expected` is an author-written *desired* output the config does
  **not** yet achieve (an open issue). Stays red. You must supply `expected`.
- **muted** — set `muted: true` for unfixable/accepted items (🙈). Pair with a
  `want`-style desired so the diff documents the wish.

## Common tasks

List tests / find an id:
```bash
FQ_BASE=https://fq.alchemmist.xyz python3 .claude/skills/format-quorum-api/scripts/fq.py list
```

Format a snippet (BEFORE→AFTER preview before writing a test):
```bash
printf 'int *p;' | FQ_BASE=https://fq.alchemmist.xyz \
  python3 .claude/skills/format-quorum-api/scripts/fq.py format --lang cpp
# optional: --version 19.1.7
```

Add a **lock** test (expected computed from the live formatter):
```bash
printf 'int main(){return 0;}' > /tmp/in.cpp
FQ_BASE=https://fq.alchemmist.xyz python3 .claude/skills/format-quorum-api/scripts/fq.py \
  add --name "Style: braces" --lang cpp --mode lock --input-file /tmp/in.cpp \
  --note "AgreedX. https://st.yandex-team.ru/LOGS-5799"
```

Add a **want** / **muted** test (you provide the desired output):
```bash
FQ_BASE=https://fq.alchemmist.xyz python3 .claude/skills/format-quorum-api/scripts/fq.py \
  add --name "P9 (muted)" --lang python --mode want --muted \
  --input-file /tmp/in.py --expected-file /tmp/want.py --note "LOGS-5799 problem 9 🙈"
```

Edit, delete, run:
```bash
fq.py update <id> --muted            # mute an existing test
fq.py update <id> --expected-file f  # change the desired output
fq.py delete <id>
fq.py run                            # run all; add --lang cpp / --version 19.1.7
```

Read / write the formatter config (writes straight to the file formatting uses):
```bash
fq.py get-config cpp                 # or: python
cat new.clang-format | fq.py put-config cpp
```

## Bulk reseed

To rebuild the whole baseline from the canonical script (deletes all, recreates):
```bash
FQ_BASE=https://fq.alchemmist.xyz python3 scripts/seed_baseline_tests.py
```
This is destructive — only do it when the user wants the curated baseline, not
for incremental edits.

## Keeping git in sync

Prod and the repo are two stores; they don't auto-sync (see the warning above).
After changing prod tests on the user's request, ask whether they also want it in
git. If yes, mirror the change in `scripts/seed_baseline_tests.py`'s `CASES` and
commit (author **alchemmist**, no `Co-Authored-By` — repo commit convention).

## Raw endpoints (if you skip the helper)

`POST /api/format` · `GET/POST /api/tests` · `PUT/DELETE /api/tests/{id}` ·
`POST /api/tests/run` · `POST /api/tests/{id}/run` ·
`GET/POST /api/clang-versions` · `DELETE /api/clang-versions/{version}` ·
`GET/PUT /api/config/{lang}` · `GET /clang-format` · `GET /ruff.toml`.
clang-format default is `18.1.8`; other versions must be installed via
`POST /api/clang-versions` first (slow — pip-installs into a venv).
