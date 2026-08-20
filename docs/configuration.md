# Configuration and persistence

## Formatter configs

Base formatter configs live in `backend/configs/`. They seed a new instance;
the active version is served by the API and shown in the config drawer.

Versioned formatters keep a separate config for each installed version. A newly
installed version starts with a copy of the default version's config. Requests
without an explicit version use the formatter default.

A shadow config is a named alternative that reuses an installed formatter
binary. It behaves like a version in the playground, tests, impact preview, and
matrix, but carries its own configuration and history.

## Drafts and publishing

Edits to configs, tests, and shadow configs first enter a browser-local draft.
The shared server remains unchanged until the draft is published. The impact
preview runs the live and draft configs against the suite and reports tests that
change status.

## Config history

Published config changes are append-only. The repository config is version 0;
every publication stores the full content, a patch, author, and message. A
rollback appends another version that restores old content, so rollback itself
can be undone.

The current content is materialized to the formatter config path used by the
runtime. History endpoints and rollback are documented in the
[API reference](api.md).

## Persistent data

The production Compose file stores mutable state in named volumes:

- `config_data` contains config history, shadow configs, and custom formatter
  metadata;
- `tests_data` contains tests created or edited through the UI;
- `clang_versions` contains installed formatter versions and uploaded binaries.

On a fresh instance, tests are copied from the image snapshot in
`backend/tests/`. Base configs are seeded from `backend/configs/`. Existing
volume data is not overwritten during deployment.

The local Compose file uses equivalent `format-quorum-local_*` volumes and bind
mounts `backend/configs/` so config materialization is visible in the checkout.
