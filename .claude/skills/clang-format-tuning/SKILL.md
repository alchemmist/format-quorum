---
name: clang-format-tuning
description: Find the clang-format style option(s) that fix a formatting problem, by reading the version-matched docs and empirically toggling options against the format-quorum test suite while watching for regressions. Use when asked to fix/solve a clang-format formatting problem or a numbered problem from the LOGS-5799 table, to tune the .clang-format config, to figure out which option controls some C++ formatting behavior, or "why does clang-format format X this way". Experiments run on an isolated binary — the real config is never changed; the outcome is a recommendation (option to add, or a manual workaround).
allowed-tools: Bash, Read, WebFetch, WebSearch, Write, Edit
---

# clang-format option tuning

Goal: given a formatting problem (a format-quorum test whose ACTUAL ≠ DESIRED),
find the clang-format option(s) that fix it **without breaking other tests** —
or prove it can't be done and give the manual workaround. The real config stays
untouched; you hand the user a recommendation.

The engine is `scripts/cfprobe.py`: it pulls the test suite + current config
from a running format-quorum (`$FQ_BASE`, default `http://localhost:3000`),
installs the exact clang-format version into a cached throw-away venv, and runs
config variants against one target test **and the whole suite** so regressions
surface immediately. It never writes to the live config.

## Method (follow in order)

### 1. Pin the version — ask first
Option names, values, and even behavior change a lot across clang-format
releases, so everything hinges on the version. **Ask the user which
clang-format version** to target. Default = format-quorum's current default —
get it from `GET $FQ_BASE/api/clang-versions` (`default` field). Confirm before
proceeding; the docs and the bench must both use that exact `X.Y.Z`.

### 2. Pull the version-matched docs — mandatory
```bash
cfprobe.py docs --version X.Y.Z      # prints the releases.llvm.org URL
```
WebFetch that URL (it is version-specific — do **not** use a different
version's docs or the trunk docs). Keep it handy; you'll grep it for keywords.

### 3. Set up the bench
```bash
FQ_BASE=http://localhost:3000 cfprobe.py setup --version X.Y.Z
cfprobe.py baseline --version X.Y.Z          # confirm which tests fail now
```
> Use a **local** format-quorum (`FQ_BASE=http://localhost:3000`), not prod —
> prod's config is live and git-backed. cfprobe only reads it anyway.

### 4. Understand the problem precisely
```bash
cfprobe.py show --target P5 --version X.Y.Z  # BEFORE / current ACTUAL / DESIRED
```
Write down exactly what differs (indent level? break after a bracket? trailing
comma? alignment vs block-indent?). That phrasing drives the keyword search.

### 5. Research options in the docs
Grep the fetched docs for keywords tied to the diff. Examples by symptom:
- indentation amount → `IndentWidth`, `ContinuationIndentWidth`, `*IndentWidth`
- break after `(`/`{` → `AlignAfterOpenBracket`, `BreakAfter*`, `*BracedList*`
- one-per-line → `BinPack*`, `AllowAllArgumentsOnNextLine`
- braces/spacing → `Cpp11BracedListStyle`, `BraceWrapping`, `SpaceInEmptyBlock`
- alignment → `Align*`
- trailing commas → `InsertTrailingCommas`
For each candidate note its **values** and the **version it was introduced** —
an option from a newer release won't exist in the target version (with
`--Wno-error=unknown` it's silently ignored, which looks like "no effect").

### 6. Experiment — one or a few options at a time
```bash
cfprobe.py try --target P5 --version X.Y.Z --set Cpp11BracedListStyle=false --show
cfprobe.py try --target P5 --version X.Y.Z --set AlignAfterOpenBracket=BlockIndent --set InsertTrailingCommas=Wrapped
```
After every run read two things:
- **TARGET … PASS/fail** — did it fix the problem?
- **REGRESSIONS** — tests that were green and are now broken. If any, this
  option is **not** an acceptable fix; **report the regression to the user** and
  move on (or look for a narrower option). Use `--show` to see the actual output
  and reason about the next toggle.

`--set` handles **top-level** keys only. For nested keys (e.g.
`BraceWrapping.AfterFunction`) edit the cached base config by hand:
`~/.cache/cfprobe/X.Y.Z/base.clang-format`, then re-run `try` with no `--set`.

### 7. If docs + experiments don't crack it → search the web
WebSearch the exact behavior (e.g. "clang-format nested braced initializer not
breaking after open brace"). Read llvm-project GitHub issues, the LLVM Discourse,
and Stack Overflow. Often the answer is "fixed by option X in version N" or "known
limitation, see issue #…". Re-test anything you find with `cfprobe try`.

### 8. Conclude — config stays unchanged
cfprobe never modifies the real config, so there's nothing to revert; still,
sanity-check (`git status backend/configs/`). Report to the user one of:
- **Clean fix:** target passes, zero regressions → give the exact lines to add
  to `.clang-format` (and offer to apply + commit them).
- **Trade-off only:** the option fixes it but regresses other tests → present the
  regression list and let the user decide.
- **Not achievable in this version:** the needed option is newer, or it's a known
  clang-format limitation → say so (cite the version/issue) and give the manual
  workaround: wrap the snippet in `// clang-format off` … `// clang-format on`
  (clang-format leaves it verbatim — verify with cfprobe by formatting the
  hand-laid-out block).

## Notes
- The bench mirrors format-quorum exactly: same flags
  (`--Wno-error=unknown --assume-filename=input.cpp --style=file:…`) and the same
  normalization (CRLF→LF, trailing newlines stripped). A green `try` ⇒ the test
  goes green in the UI too.
- Per-version install is one-time (cached under `~/.cache/cfprobe/`). Re-run
  `setup` after the suite or config changes to refresh the snapshot.
- Python/ruff problems are out of scope here (this bench drives clang-format).
