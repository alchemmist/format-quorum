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
`run`, `get-config <lang>`, `put-config <lang>`, `config-history <lang>`,
`config-rollback <lang> <seq>`, `whatif`. Run any with `-h` for flags.

**Config is versioned.** `put-config` doesn't overwrite — it records a new
version (with `--author` / `--message`). `config-history` lists every version
with its patch; `config-rollback <lang> <seq>` restores an earlier one (`seq 0`
= the original base). So a bad config edit is always reversible.

**cpp configs are per clang-format version.** Each installed clang-format
version keeps its own `.clang-format` (its own history/rollbacks) — the point of
a newer version is its new options. Target one with `--clang-version X.Y.Z` on
`get-config` / `put-config` / `config-history` / `config-rollback` (omit = the
default version). A newly added version's config is copied once from the default
version's current config. python has a single config (no version).

**`whatif`** answers "config patch → which tests pass/fail" in one call without
touching the stored config — the server runs the suite live vs candidate and
diffs them. Use it to check a tuning hypothesis or a config edit's blast radius:

```bash
# does AlignAfterOpenBracket: DontAlign fix test P7, and what does it break?
fq.py whatif --version 18.1.8 --set AlignAfterOpenBracket=DontAlign --target P7
# combine overrides, or try a whole file with --config-file
fq.py whatif --set AlignAfterOpenBracket=Align --set PenaltyBreakAssignment=0 --target P7
```

It prints baseline vs patched counts, `+fixed / −broken / muted-would-pass`, and
each `--target`'s `baseline → patched` status. `--set` overrides apply on top of
the **live** config (cpp only); `--config-file` tries a full config as-is.

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

Read / write (download / change / upload) the formatter config. `put-config`
records a new version and re-materializes the file formatting uses, so the change
takes effect immediately for the playground, test runs, and the matrix:
```bash
fq.py get-config cpp                                  # default version's config
fq.py get-config cpp --clang-version 22.1.8           # a specific version's config
fq.py get-config cpp > my.clang-format && $EDITOR my.clang-format
fq.py put-config cpp -i my.clang-format               # upload to the default version
fq.py put-config cpp --clang-version 22.1.8 -i my.clang-format   # to one version
fq.py get-config python                               # python (single, no version)
```

> The config history lives in a **named volume** (`config_data`) and is
> re-materialized on startup, so a `put-config` on prod **survives deploys**
> (a `git reset --hard` of `backend/configs/` is overwritten by the stored
> current on boot). Roll an accidental break back with `config-rollback`. To
> also change the repo's seed (what a brand-new volume starts from), commit
> `backend/configs/`.

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
`POST /api/tests/whatif` (`{language, clang_version?, patch?, config?, targets?}`
→ `{summary{baseline,patched}, flips{now_pass,now_fail,muted_would_pass}, results, targets?}`) ·
`POST /api/tests/matrix` (`{language}` → `{versions, tests:[{id,name,muted,cells{ver:{status,passed}},muted_passes_somewhere}]}`) ·
`GET/POST /api/clang-versions` · `DELETE /api/clang-versions/{version}` ·
`GET/PUT /api/config/{lang}` (cpp: `?version=X.Y.Z` on GET / `version` in the PUT
body selects a clang-format version's config — default version if omitted; PUT
records a version, body may add `author`/`message`) ·
`GET /api/config/{lang}/history?version=` · `GET /api/config/{lang}/history/{seq}?version=` ·
`POST /api/config/{lang}/rollback` (`{seq, version?, author?, message?}`) ·
`GET /clang-format` · `GET /ruff.toml`.
Each installed clang-format version has its own config (cloned once from the
default version when added); other versions must be installed via
`POST /api/clang-versions` first (slow — pip-installs into a venv).
