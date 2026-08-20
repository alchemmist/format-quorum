# Format Quorum

Format Quorum is a playground and regression test bench for shared formatter
configs. Turn formatting disputes into executable examples, compare formatter
versions, and see which decisions a config change fixes or breaks.

![](demo.png)

## Features

- **Formatting playground** with syntax highlighting and a line-level diff.
- **Golden tests** that record input and expected output, run individually or as
  a suite, and distinguish accepted compromises from regressions.
- **Version matrix** that runs the same cases through every installed formatter
  version and shows the exact output of each cell.
- **Config impact preview** that reports which tests a draft fixes, breaks, or
  makes pass despite being muted.
- **Shadow configs** for comparing alternative configurations on the same
  formatter binary without changing the shared config.
- **Local drafts and publishing** so config and test edits can be reviewed before
  they reach the shared instance.
- **Append-only config history** with diffs and rollback.
- **Multiple formatter versions**, including uploaded patched binaries on trusted
  deployments.
- **13 languages and 14 built-in formatters**, including clang-format, Ruff,
  Black, Prettier, rustfmt, shfmt, Taplo, and google-java-format.
- **Open API and agent skills** for automated experiments and formatter tuning.

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration and persistence](docs/configuration.md)
- [API reference](docs/api.md)
- [Agent integrations](docs/agent-integrations.md)
- [Test system design](docs/test-system-design.md)
- [Deployment](deploy/README.md)

Licensed under the [MIT License](LICENSE).
