# Agent integrations

The repository contains two skills under `.claude/skills/`.

## format-quorum-api

`format-quorum-api` drives an instance over HTTP. It can list, create, update,
delete, and run tests, and read or publish formatter configs.

## clang-format-tuning

`clang-format-tuning` provides a repeatable loop for solving a formatting case:

1. Pin one clang-format version.
2. Load documentation that matches that version.
3. Sweep candidate option combinations against a target test.
4. Re-run the full suite and report regressions.
5. Return a candidate only when the target actually passes.

Its `cfprobe.py` helper uses per-request config overrides, so experiments do not
overwrite the shared config.
