---
name: clang-format-tuning
description: Find the clang-format style option(s) that fix a formatting problem, by reading the version-matched docs and empirically toggling options against the format-quorum test suite while watching for regressions. Use when asked to fix/solve a clang-format formatting problem or a numbered problem from the LOGS-5799 table, to tune the .clang-format config, to figure out which option controls some C++ formatting behavior, or "why does clang-format format X this way". Everything runs through the format-quorum HTTP API against ad-hoc configs — the stored config is never changed; the outcome is a config recommendation or a proof that no option achieves it.
allowed-tools: Bash, Read, WebFetch, WebSearch
---

# clang-format option tuning

Goal: given a formatting problem (a format-quorum test whose ACTUAL ≠ DESIRED),
find the clang-format option(s) that make the test pass **without breaking other
tests** — or prove that no option does. You hand the user a config recommendation;
the stored config is never modified.

A solution means: **a `.clang-format` option (or combination) that the target
version supports, that makes the target test pass with zero regressions.** That
is the only thing that counts as solving it.

The engine is `scripts/cfprobe.py`. It runs **entirely through the format-quorum
HTTP API** (`$FQ_BASE`, default `http://localhost:3000`): it formats and runs the
suite against an **ad-hoc config** passed in the request body, so the saved
config is never touched. Do not install or run clang-format locally and do not
edit config files on disk — drive everything via cfprobe / the API.

## Hard rules

- **One version only.** Tune for the single clang-format version you were given
  (ask the user; default = the instance's `default` from `GET /api/clang-versions`).
  Do **not** test or recommend any other version. An option that exists only in a
  newer clang-format does **not** count as a solution for this version — treat it
  as "no option available".
- **`// clang-format off` / `on` is not a solution.** It's the obvious universal
  escape hatch and goes without saying — never propose it as the outcome and don't
  spend the user's words on it. If no real config option works, say the config
  cannot do it (and why), full stop.

## Method (follow in order)

### 1. Pin the version — ask first
Option names, values, and behavior change a lot across clang-format releases.
Ask the user which version to target; default to the instance default:
```bash
cfprobe.py versions                       # installed versions + default
cfprobe.py ensure --version X.Y.Z         # install it in the instance if missing (via API)
```

### 2. Pull the version-matched docs — mandatory
```bash
cfprobe.py docs --version X.Y.Z           # prints the releases.llvm.org URL
```
WebFetch that exact-version URL (not trunk, not another version) and keep it to
grep for keywords.

### 3. See the current state and the problem
```bash
cfprobe.py baseline --version X.Y.Z              # which tests fail now
cfprobe.py show --target P5 --version X.Y.Z      # BEFORE / current ACTUAL / DESIRED
```
Write down precisely what differs (indent level? break after a bracket? trailing
comma? alignment vs block-indent?) — that phrasing drives the keyword search.

### 4. Research options in the docs
Grep the fetched docs for keywords tied to the diff. By symptom:
- indentation amount → `IndentWidth`, `ContinuationIndentWidth`, `*IndentWidth`
- break after `(`/`{` → `AlignAfterOpenBracket`, `BreakAfter*`, `*BracedList*`
- one-per-line → `BinPack*`, `AllowAllArgumentsOnNextLine`
- braces/spacing → `Cpp11BracedListStyle`, `BraceWrapping`, `SpaceInEmptyBlock`
- alignment → `Align*`   ·   trailing commas → `InsertTrailingCommas`
For each candidate note its **values** and the **version it was introduced**. If
it postdates your target version, skip it (it won't exist there — with
`--Wno-error=unknown` it's silently ignored, which masquerades as "no effect").

### 5. Experiment — one or a few options at a time
```bash
cfprobe.py try --target P5 --version X.Y.Z --set Cpp11BracedListStyle=false --show
cfprobe.py try --target P5 --version X.Y.Z --set AlignAfterOpenBracket=BlockIndent --set InsertTrailingCommas=Wrapped
```
After every run read two lines:
- **TARGET … PASS / still fails** — did it fix the problem?
- **REGRESSIONS** — tests that were green and are now broken. If any, this option
  is **not** an acceptable fix; **report the regression to the user** and move on
  (or look for a narrower option). `--show` prints the actual output to reason
  about the next toggle.

`--set` handles **top-level** keys. For nested keys (e.g.
`BraceWrapping.AfterFunction`): `cfprobe.py show`-less — fetch the config
(`curl $FQ_BASE/api/config/cpp`), edit a copy, and pass it whole with
`--config-file PATH`.

### 6. If docs + experiments don't crack it → search the web
WebSearch the exact behavior (e.g. "clang-format nested braced initializer not
breaking after open brace"). Read llvm-project GitHub issues, LLVM Discourse,
Stack Overflow. Re-test anything you find with `cfprobe try` **on the pinned
version only** — if the fix is "added in a later release", it does not apply.

### 7. Conclude
The stored config was never changed, so there's nothing to revert. Report one of:
- **Clean fix:** target passes, zero regressions → give the exact `.clang-format`
  line(s) to add, and offer to apply + commit them.
- **Trade-off only:** an option fixes the target but regresses other tests →
  present the regression list and let the user decide.
- **No config option:** nothing in the target version achieves it (the needed
  knob doesn't exist, or every option that helps also drives an unrelated
  construct and regresses agreed styles). State that plainly and explain the
  conflict — that a single option governs several constructs at once, so you
  can't fix this one without breaking the others. (Don't mention the off/on
  escape hatch.)

## Notes
- The bench mirrors format-quorum exactly (it *is* the API): same flags, same
  normalization. A green `try` ⇒ the test is green in the UI too.
- Clang-format configs apply only to cpp; cfprobe always scopes runs to cpp.
  Python/ruff tuning is out of scope for this skill.
