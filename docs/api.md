# API reference

The API supports the web UI, scripts, and agent integrations. Format and test
run requests may include an ad hoc `config` string, allowing an experiment to run
without changing stored state.

`POST /api/tests/whatif` accepts either a complete config or a top-level
clang-format patch. It compares the candidate with the live config and returns
tests that become passing, failing, or passing despite being muted.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/formatters` | List formatters and deployment capabilities |
| `POST` | `/api/format` | Format code with a selected formatter, version, and config |
| `GET`, `POST` | `/api/formatters/{id}/versions` | List or install formatter versions |
| `DELETE` | `/api/formatters/{id}/versions/{version}` | Remove a formatter version |
| `GET`, `POST` | `/api/custom-formatters` | List or upload custom formatter binaries |
| `DELETE` | `/api/custom-formatters/{id}` | Remove a custom formatter |
| `GET` | `/api/custom-formatters/{id}/versions/{version}/binary` | Download an uploaded binary |
| `POST` | `/api/shadow-configs` | Create a shadow config |
| `DELETE` | `/api/shadow-configs/{id}` | Remove a shadow config |
| `GET`, `POST`, `PUT`, `DELETE` | `/api/tests` | Manage golden tests |
| `POST` | `/api/tests/run` | Run a test suite |
| `POST` | `/api/tests/{id}/run` | Run one test |
| `POST` | `/api/tests/whatif` | Compare a candidate config with the live config |
| `POST` | `/api/tests/matrix` | Run tests across formatter versions and shadows |
| `GET`, `PUT` | `/api/config/{formatter}` | Read or publish a formatter config |
| `GET` | `/api/config/{formatter}/history` | List config versions and patches |
| `GET` | `/api/config/{formatter}/history/{seq}` | Read a historical config |
| `POST` | `/api/config/{formatter}/rollback` | Restore a historical config as a new version |
| `GET` | `/clang-format`, `/ruff.toml` | Read selected raw config files |

The legacy `/api/clang-versions` routes remain available for clang-format.

The API has no built-in authentication. Binary upload executes user-supplied
programs on the server and must only be enabled in a trusted environment.
Publishing and binary uploads are controlled independently by deployment
settings.
